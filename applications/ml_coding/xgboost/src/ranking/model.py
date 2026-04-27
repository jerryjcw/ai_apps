"""Learning-to-rank model: build / train / evaluate / inference.

Uses ``xgboost.XGBRanker`` with the ``rank:ndcg`` (LambdaRank) objective.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd
import xgboost as xgb

from . import config


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _dcg(gains: np.ndarray, k: int) -> float:
    """Discounted cumulative gain at rank ``k`` with log2 discount.

    DCG@k = Σ_{i=1..k}  gain_i / log2(i + 1)     (1-indexed)
    """
    gains = gains[:k]
    if gains.size == 0:
        return 0.0
    discounts = 1.0 / np.log2(np.arange(2, gains.size + 2))
    return float((gains * discounts).sum())


def ndcg_at_k(y_true: np.ndarray, y_score: np.ndarray, k: int) -> float:
    """NDCG@k for a single query.

    ``y_true`` = graded relevance labels (ints), ``y_score`` = model scores.
    Uses gain = y_true (linear); XGBoost's internal metric uses 2^rel − 1,
    so our values will be slightly different but correlate perfectly with XGB's.
    """
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score)

    order_pred = np.argsort(-y_score, kind="stable")
    dcg = _dcg(y_true[order_pred], k)

    order_ideal = np.argsort(-y_true, kind="stable")
    idcg = _dcg(y_true[order_ideal], k)

    return 0.0 if idcg == 0.0 else dcg / idcg


def map_at_k(y_true: np.ndarray, y_score: np.ndarray, k: int, rel_threshold: int = 4) -> float:
    """Mean Average Precision at k for a single query.

    Graded labels are binarised via ``rel_threshold`` (MovieLens: rating ≥ 4
    → relevant). Returns 0 if no relevant items exist.
    """
    y_true = (np.asarray(y_true) >= rel_threshold).astype(np.int32)
    y_score = np.asarray(y_score)
    if y_true.sum() == 0:
        return 0.0

    order = np.argsort(-y_score, kind="stable")[:k]
    hits = y_true[order]
    if hits.sum() == 0:
        return 0.0

    precisions = np.cumsum(hits) / np.arange(1, hits.size + 1)
    # Standard MAP divides by min(#relevant, k); using #relevant-in-topk
    # matches what librec / RankEval call MAP@k.
    return float((precisions * hits).sum() / hits.sum())


def mrr(y_true: np.ndarray, y_score: np.ndarray, rel_threshold: int = 4) -> float:
    """Mean Reciprocal Rank for a single query."""
    y_true = (np.asarray(y_true) >= rel_threshold).astype(np.int32)
    y_score = np.asarray(y_score)
    if y_true.sum() == 0:
        return 0.0
    order = np.argsort(-y_score, kind="stable")
    for rank, idx in enumerate(order, start=1):
        if y_true[idx]:
            return 1.0 / rank
    return 0.0


def _iter_groups(qid: np.ndarray):
    """Yield (start, end) index pairs for each contiguous qid run."""
    n = len(qid)
    if n == 0:
        return
    start = 0
    for i in range(1, n):
        if qid[i] != qid[i - 1]:
            yield start, i
            start = i
    yield start, n


@dataclass(frozen=True)
class RankingReport:
    """Held-out metrics averaged over queries (users)."""
    ndcg: dict  # {k: mean NDCG@k}
    map_at_10: float
    mrr: float
    n_queries: int

    def to_dict(self) -> dict:
        return {
            "ndcg": self.ndcg,
            "map@10": self.map_at_10,
            "mrr": self.mrr,
            "n_queries": self.n_queries,
        }


# ---------------------------------------------------------------------------
# Model lifecycle
# ---------------------------------------------------------------------------

def build_ranker(params: Mapping[str, Any] | None = None) -> xgb.XGBRanker:
    """Return an ``XGBRanker`` seeded with our default hyperparameters."""
    merged = dict(config.DEFAULT_XGB_PARAMS)
    if params:
        merged.update(params)
    merged.setdefault("early_stopping_rounds", config.EARLY_STOPPING_ROUNDS)
    return xgb.XGBRanker(**merged)


def train(
    model: xgb.XGBRanker,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    qid_train: np.ndarray,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    qid_val: np.ndarray,
    verbose: bool | int = False,
) -> xgb.XGBRanker:
    """Fit ``model`` with early stopping driven by the val query set."""
    model.fit(
        X_train, y_train,
        qid=qid_train,
        eval_set=[(X_val, y_val)],
        eval_qid=[qid_val],
        verbose=verbose,
    )
    return model


def evaluate(
    model: xgb.XGBRanker,
    X: pd.DataFrame,
    y: pd.Series,
    qid: np.ndarray,
    k_list: tuple[int, ...] = config.NDCG_K_LIST,
    rel_threshold: int = 4,
) -> RankingReport:
    """Compute NDCG@k (for each k), MAP@10, and MRR averaged across queries."""
    scores = model.predict(X)
    y_arr = np.asarray(y)

    per_query_ndcg = {k: [] for k in k_list}
    per_query_map = []
    per_query_mrr = []

    for start, end in _iter_groups(qid):
        yt = y_arr[start:end]
        ys = scores[start:end]
        for k in k_list:
            per_query_ndcg[k].append(ndcg_at_k(yt, ys, k))
        per_query_map.append(map_at_k(yt, ys, 10, rel_threshold=rel_threshold))
        per_query_mrr.append(mrr(yt, ys, rel_threshold=rel_threshold))

    n_queries = len(per_query_mrr)
    return RankingReport(
        ndcg={k: float(np.mean(per_query_ndcg[k])) for k in k_list},
        map_at_10=float(np.mean(per_query_map)),
        mrr=float(np.mean(per_query_mrr)),
        n_queries=n_queries,
    )


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------

def score_candidates(
    model: xgb.XGBRanker,
    candidates: pd.DataFrame,
    feature_columns: tuple[str, ...] | list[str],
) -> np.ndarray:
    """Return raw ranking scores for a candidate DataFrame."""
    return model.predict(candidates[list(feature_columns)].astype(np.float32))


def rank_candidates(
    model: xgb.XGBRanker,
    candidates: pd.DataFrame,
    feature_columns: tuple[str, ...] | list[str],
    top_k: int | None = None,
    id_column: str | None = None,
) -> pd.DataFrame:
    """Rank a set of candidate items for **one** query.

    The caller is responsible for making sure every row in ``candidates``
    belongs to the same query (same user, same search request, etc.).
    Returns a new DataFrame sorted by score descending, with ``rank`` and
    ``score`` columns appended.
    """
    scores = score_candidates(model, candidates, feature_columns)
    out = candidates.copy()
    out["score"] = scores
    out = out.sort_values("score", ascending=False, kind="stable").reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    cols = ["rank", "score", *([id_column] if id_column else []),
            *[c for c in out.columns if c not in {"rank", "score", id_column}]]
    out = out[[c for c in cols if c in out.columns]]
    if top_k is not None:
        out = out.head(top_k)
    return out


def feature_importance_table(
    model: xgb.XGBRanker,
    feature_names: list[str] | None = None,
    importance_type: str = "gain",
    top_k: int | None = None,
) -> pd.DataFrame:
    """Feature importances sorted descending (same as the classification helper)."""
    booster = model.get_booster()
    raw = booster.get_score(importance_type=importance_type)
    if feature_names is not None:
        name_of = {f"f{i}": name for i, name in enumerate(feature_names)}
        raw = {name_of.get(k, k): v for k, v in raw.items()}
    if not raw:
        return pd.DataFrame(columns=["feature", importance_type])
    table = (
        pd.DataFrame({"feature": list(raw.keys()), importance_type: list(raw.values())})
        .sort_values(importance_type, ascending=False)
        .reset_index(drop=True)
    )
    return table.head(top_k) if top_k else table
