"""Unit tests for ``src.ranking.model``.

We test metric implementations with hand-computed values, then train a tiny
``XGBRanker`` on synthetic ranking data to exercise train / evaluate / rank.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
import xgboost as xgb

from src.ranking import config
from src.ranking.model import (
    RankingReport,
    build_ranker,
    evaluate,
    feature_importance_table,
    map_at_k,
    mrr,
    ndcg_at_k,
    rank_candidates,
    train,
)


# ---------------------------------------------------------------------------
# Metric correctness
# ---------------------------------------------------------------------------

def test_ndcg_perfect_ranking_is_one() -> None:
    y_true = np.array([3, 2, 1, 0])
    y_score = np.array([10.0, 5.0, 2.0, 0.0])  # perfectly aligned
    assert ndcg_at_k(y_true, y_score, 4) == pytest.approx(1.0)


def test_ndcg_reverse_ranking_is_less_than_one() -> None:
    y_true = np.array([3, 2, 1, 0])
    y_score = np.array([0.0, 1.0, 2.0, 10.0])  # completely reversed
    # With linear gain and log2 discount this is strictly below 1 but > 0.
    v = ndcg_at_k(y_true, y_score, 4)
    assert 0 < v < 1
    # Known closed-form: DCG = 0/log2(2)+1/log2(3)+2/log2(4)+3/log2(5)
    dcg = 0 / math.log2(2) + 1 / math.log2(3) + 2 / math.log2(4) + 3 / math.log2(5)
    idcg = 3 / math.log2(2) + 2 / math.log2(3) + 1 / math.log2(4) + 0 / math.log2(5)
    assert v == pytest.approx(dcg / idcg)


def test_ndcg_all_zero_relevance_returns_zero() -> None:
    assert ndcg_at_k(np.zeros(5), np.arange(5, dtype=float), 3) == 0.0


def test_map_at_k_hand_computed() -> None:
    # Binarised labels with threshold 4: 5→1, 4→1, 3→0, 5→1, 1→0.
    y_true = np.array([5, 4, 3, 5, 1])
    y_score = np.array([0.9, 0.8, 0.7, 0.6, 0.5])  # order matches input order
    # Top-5: hits = [1,1,0,1,0]; precisions = [1, 1, 2/3, 3/4, 3/5]
    # AP = (1*1 + 1*1 + 0 + 1*(3/4) + 0) / 3 = 2.75 / 3
    assert map_at_k(y_true, y_score, 5) == pytest.approx(2.75 / 3)


def test_map_at_k_returns_zero_when_no_relevant() -> None:
    y_true = np.array([1, 2, 3])
    y_score = np.array([0.9, 0.8, 0.7])
    assert map_at_k(y_true, y_score, 3, rel_threshold=4) == 0.0


def test_mrr_finds_first_relevant() -> None:
    y_true = np.array([2, 5, 1, 4])
    y_score = np.array([0.9, 0.8, 0.7, 0.6])
    # Order: idx 0 (rel 0), idx 1 (rel 1), ...  → first hit at rank 2.
    assert mrr(y_true, y_score, rel_threshold=4) == pytest.approx(1 / 2)


def test_mrr_zero_when_no_relevant() -> None:
    y_true = np.array([1, 2, 3])
    y_score = np.array([0.9, 0.8, 0.7])
    assert mrr(y_true, y_score, rel_threshold=4) == 0.0


# ---------------------------------------------------------------------------
# Model lifecycle on tiny synthetic ranking data
# ---------------------------------------------------------------------------

@pytest.fixture
def tiny_ltr() -> tuple[pd.DataFrame, pd.Series, np.ndarray,
                        pd.DataFrame, pd.Series, np.ndarray]:
    """200 queries × 8 docs each; label correlates with a single feature."""
    rng = np.random.default_rng(42)
    n_queries = 200
    docs_per_q = 8
    n_feats = 4

    rows = []
    for q in range(n_queries):
        feats = rng.normal(size=(docs_per_q, n_feats)).astype(np.float32)
        # label = binned version of feats[:, 0] + per-query offset
        signal = feats[:, 0] + rng.normal(scale=0.2)
        labels = np.digitize(signal, bins=[-1.0, -0.2, 0.5, 1.2]).astype(np.int32)
        for d in range(docs_per_q):
            rows.append((q, *feats[d].tolist(), int(labels[d])))

    cols = ["qid", "f0", "f1", "f2", "f3", "y"]
    df = pd.DataFrame(rows, columns=cols).sort_values("qid").reset_index(drop=True)

    split_q = n_queries * 3 // 4  # 150 train, 50 val
    train_df = df[df["qid"] < split_q]
    val_df = df[df["qid"] >= split_q]

    def xyq(d):
        X = d[["f0", "f1", "f2", "f3"]].reset_index(drop=True)
        y = d["y"].reset_index(drop=True)
        qid = d["qid"].to_numpy()
        return X, y, qid

    Xtr, ytr, qtr = xyq(train_df)
    Xvl, yvl, qvl = xyq(val_df)
    return Xtr, ytr, qtr, Xvl, yvl, qvl


def test_build_ranker_returns_xgbranker() -> None:
    model = build_ranker()
    assert isinstance(model, xgb.XGBRanker)
    assert model.get_params()["objective"] == config.DEFAULT_XGB_PARAMS["objective"]


def test_build_ranker_merges_overrides() -> None:
    model = build_ranker({"max_depth": 3, "learning_rate": 0.2})
    params = model.get_params()
    assert params["max_depth"] == 3
    assert params["learning_rate"] == 0.2
    assert params["n_estimators"] == config.DEFAULT_XGB_PARAMS["n_estimators"]


def test_train_runs_early_stopping(tiny_ltr) -> None:
    Xtr, ytr, qtr, Xvl, yvl, qvl = tiny_ltr
    model = build_ranker({"n_estimators": 150, "max_depth": 3, "learning_rate": 0.1})
    train(model, Xtr, ytr, qtr, Xvl, yvl, qvl, verbose=False)
    assert model.best_iteration is not None
    assert 0 <= model.best_iteration < 150


def test_evaluate_returns_sane_metrics(tiny_ltr) -> None:
    Xtr, ytr, qtr, Xvl, yvl, qvl = tiny_ltr
    model = build_ranker({"n_estimators": 80, "max_depth": 3, "learning_rate": 0.1})
    train(model, Xtr, ytr, qtr, Xvl, yvl, qvl)
    report = evaluate(model, Xvl, yvl, qvl, k_list=(3, 5), rel_threshold=3)

    assert isinstance(report, RankingReport)
    assert report.n_queries == len(set(qvl))
    for k, v in report.ndcg.items():
        assert 0.0 <= v <= 1.0
    assert 0.0 <= report.map_at_10 <= 1.0
    assert 0.0 <= report.mrr <= 1.0
    # Signal was strong; NDCG@3 should clearly beat random (0.7-ish lower bound).
    assert report.ndcg[3] > 0.7


def test_rank_candidates_returns_sorted_top_k(tiny_ltr) -> None:
    Xtr, ytr, qtr, Xvl, yvl, qvl = tiny_ltr
    model = build_ranker({"n_estimators": 50, "max_depth": 3, "learning_rate": 0.1})
    train(model, Xtr, ytr, qtr, Xvl, yvl, qvl)

    # Pick one query's candidates.
    first_q = qvl[0]
    mask = qvl == first_q
    candidates = Xvl.loc[mask].copy()
    candidates["doc_id"] = np.arange(len(candidates))

    ranked = rank_candidates(
        model, candidates,
        feature_columns=("f0", "f1", "f2", "f3"),
        top_k=3, id_column="doc_id",
    )
    assert list(ranked.columns)[:3] == ["rank", "score", "doc_id"]
    assert len(ranked) == 3
    # Scores are non-increasing.
    assert np.all(np.diff(ranked["score"].values) <= 0)
    # Ranks are 1..N consecutive.
    assert list(ranked["rank"]) == [1, 2, 3]


def test_feature_importance_is_sorted(tiny_ltr) -> None:
    Xtr, ytr, qtr, Xvl, yvl, qvl = tiny_ltr
    model = build_ranker({"n_estimators": 40, "max_depth": 3, "learning_rate": 0.1})
    train(model, Xtr, ytr, qtr, Xvl, yvl, qvl)
    table = feature_importance_table(model, feature_names=["f0", "f1", "f2", "f3"])
    assert list(table.columns) == ["feature", "gain"]
    assert np.all(np.diff(table["gain"].values) <= 0)
    # f0 was the signal feature — it should rank first.
    assert table["feature"].iloc[0] == "f0"
