# XGBoost Practice

Two hands-on examples sharing one project:

1. **Classification** — UCI Adult Income (binary classification on tabular data)
2. **Ranking** — MovieLens-100K (learning-to-rank for recommendation)

Each sub-package is small enough to read top-to-bottom and covers every step a
Kaggle-style workflow needs: download, preprocess, train with early stopping,
evaluate, and inspect feature importance.

---

## Project layout

```
xgboost/
├── README.md              ← you are here
├── learning_note.md       ← interview-prep cheat sheet (bilingual)
├── requirements.txt       ← extra Python deps (on top of the shared .venv)
├── data/                  ← dataset cache (auto-populated on first run)
├── models/                ← saved boosters (created by run.py)
├── reports/               ← JSON evaluation reports (created by run.py)
├── notebooks/             ← your scratchpad; empty by default
└── src/
    ├── classification/    ← UCI Adult — binary classification
    │   ├── config.py
    │   ├── data.py
    │   ├── model.py
    │   └── run.py
    └── ranking/           ← MovieLens-100K — learning-to-rank
        ├── config.py
        ├── data.py
        ├── model.py
        └── run.py
```

Unit tests live under the repo-wide tests folder at `tests/xgboost/`
(per the project convention in `CLAUDE.md`).

---

## Quick start

The nearest virtual environment is at `applications/ml_coding/.venv`.

```bash
# 1. From the repo root, install the XGBoost + sklearn stack into the venv
applications/ml_coding/.venv/bin/pip install -r applications/ml_coding/xgboost/requirements.txt

# 2. macOS only: XGBoost's dylib needs libomp
brew install libomp

# 3. Run the classification pipeline (download → train → evaluate → save)
cd applications/ml_coding/xgboost
../.venv/bin/python -m src.classification.run

# 4. Run the ranking pipeline
../.venv/bin/python -m src.ranking.run
```

---

# Example 1 — Classification (UCI Adult Income)

## Why this dataset

The **UCI Adult / Census Income** dataset (Kohavi, 1996) is a binary
classification problem: predict whether an adult earns more than US$50K/yr
from 14 demographic features.

1. **Used as a benchmark in the XGBoost paper** (Chen & Guestrin, KDD 2016).
2. **Mixed feature types** (numeric + categorical) — exercises XGBoost's
   native categorical support (`enable_categorical=True`).
3. **Missing values** encoded as `?` — showcases sparsity-aware split finding.
4. **Tiny** (~4 MB, ~49K rows). Trains in seconds.

## Expected results

| Metric   | Value  |
|----------|--------|
| Accuracy | ~0.877 |
| ROC-AUC  | ~0.930 |
| PR-AUC   | ~0.833 |
| F1       | ~0.718 |
| Log loss | ~0.275 |

## Overriding hyperparameters from the CLI

```bash
../.venv/bin/python -m src.classification.run \
    --max-depth 8 --learning-rate 0.03 --n-estimators 1000
```

---

# Example 2 — Ranking (MovieLens-100K)

## Why this dataset

**MovieLens-100K** (Harper & Konstan, 2015) is the de-facto "hello-world" for
recommender systems: 100,000 ratings on a 1–5 scale from 943 users across
1,682 movies. It maps cleanly onto the **learning-to-rank (LTR)** formulation:

- **Each user = one query.** Their rated movies form the candidate set.
- **Ratings 1–5 = graded relevance labels.** Perfect for `rank:ndcg`.
- **Real, small (~5 MB), stable URL** from GroupLens — no auth, no fuss.

The same code path generalises to real search ranking (MSLR-WEB10K, Yahoo!
LTR, LETOR) — only the data loader changes.

## Features

Each (user, movie) row is described by 25 features, **all computed from the
training fold only** to avoid target leakage:

| Group | Features |
|---|---|
| User-level | `u_mean`, `u_count`, `u_std` (rating distribution) |
| Movie-level | `m_mean`, `m_count`, `year` |
| Genre one-hots | 19 flags: `Action`, `Comedy`, `Drama`, `Thriller`, … |

Cold-start users / movies fall back to the global mean + zero count.

## Expected results

Default hyperparameters, CPU, ~5 seconds total:

| Metric     | Validation | Test  |
|------------|------------|-------|
| NDCG@5     | ~0.896     | ~0.886 |
| NDCG@10    | ~0.919     | ~0.909 |
| NDCG@20    | ~0.938     | ~0.930 |
| MAP@10     | ~0.806     | ~0.806 |
| MRR        | ~0.866     | ~0.872 |

(Binary relevance threshold for MAP/MRR = rating ≥ 4.)

Saved artefacts:

- `models/movielens_xgbranker.json` — booster in portable JSON format
- `reports/movielens_report.json` — metrics + top features + params

## Overriding hyperparameters from the CLI

```bash
../.venv/bin/python -m src.ranking.run \
    --objective rank:pairwise \
    --lambdarank-pair-method mean \
    --max-depth 8 --learning-rate 0.03 --n-estimators 1500
```

## Inference: rank candidates for one user

```python
from src.ranking.data import load_ranking_splits
from src.ranking.model import build_ranker, train, rank_candidates
import xgboost as xgb

splits = load_ranking_splits()
model = xgb.XGBRanker()
model.load_model("models/movielens_xgbranker.json")

# Pick candidates for a single user (all rows in X_test for that qid).
user_id = int(splits.qid_test[0])
mask = splits.qid_test == user_id
candidates = splits.X_test.loc[mask].copy()

top10 = rank_candidates(
    model, candidates,
    feature_columns=splits.feature_columns,
    top_k=10,
)
print(top10)
```

---

## A 5-minute mental model of learning-to-rank

### Pointwise vs pairwise vs listwise

- **Pointwise** (`objective="reg:squarederror"`): treat each (query, doc) as an
  independent regression sample. Simple, but ignores the per-query ranking.
- **Pairwise** (`rank:pairwise`, RankNet-style): for each query, sample
  (positive, negative) pairs and train the model to score positives higher.
- **Listwise** (`rank:ndcg`, `rank:map` — both LambdaRank): directly optimise
  a surrogate of a list-based metric (NDCG or MAP). **Usually best on graded
  relevance data.**

### LambdaRank in one line

LambdaRank re-weights each pair by **how much NDCG would change if you
swapped them**: `ΔNDCG_{ij}`. Pairs near the top (small rank → big NDCG swing)
get larger gradients, so the model focuses its effort on the head of the
ranking — exactly where users care.

### Metrics glossary

| Metric | What it rewards | Needs |
|---|---|---|
| **DCG@k** | Placing high-relevance items near the top, with log-discount | Graded labels |
| **NDCG@k** | DCG@k / ideal DCG@k — normalises across queries | Graded labels |
| **MAP@k** | Mean average precision over relevant items | Binary labels |
| **MRR** | 1 / rank of the first relevant item | Binary labels |
| **Precision@k / Recall@k** | Classic binary top-k metrics | Binary labels |

### XGBoost ranking-specific hyperparameters

| Knob | What it does |
|---|---|
| `objective` | `rank:ndcg` (default, graded), `rank:pairwise`, `rank:map` (binary) |
| `lambdarank_pair_method` | `"topk"` (focus on head), `"mean"` (sample uniformly) |
| `lambdarank_num_pair_per_sample` | How many (pos, neg) pairs per query per round |
| `lambdarank_unbiased` | Correct for position bias (e.g., click data) — off by default |
| `eval_metric` | List of `ndcg@k`, `pre@k`, `map@k`, … |

Non-ranking knobs (`max_depth`, `learning_rate`, `subsample`, …) behave
exactly like the classifier — see the tuning section below.

---

## Tuning strategy (applies to both examples)

```
固定 lr=0.1 + early stopping                         (classification & ranking)
  → 調 (max_depth, min_child_weight)                 ← biggest effect
  → 調 gamma                                          ← pruning
  → 調 (subsample, colsample_bytree)                 ← anti-overfit
  → 調 (reg_alpha, reg_lambda)                       ← fine-tune
  → 最後 lr 調小，n_estimators 放大                   ← polish
```

**Ranking-specific additions**

- **Pair method**: if NDCG@k is the business metric, keep `lambdarank_pair_method="topk"`.
  Switch to `"mean"` if the whole list matters (e.g. pagination far below the fold).
- **Pairs per sample**: 1 (default) is fast; 8–16 gives smoother gradients.
  Trade-off is training time.
- **Binarise labels?** If you only care about "relevant / not relevant", use
  `rank:map` and collapse labels; if you have graded data, keep it graded and
  use `rank:ndcg`.

Use **group-aware CV**: split by query (user), not by row, to avoid leaking a
user across folds. sklearn's `GroupKFold(n_splits=5).split(X, y, groups=qid)`
is the canonical tool.

### Example Optuna objective for ranking

```python
import optuna, xgboost as xgb
from sklearn.metrics import ndcg_score
from src.ranking.data import load_ranking_splits

splits = load_ranking_splits()

def objective(trial):
    params = {
        "objective":        "rank:ndcg",
        "eval_metric":      ["ndcg@10"],
        "tree_method":      "hist",
        "max_depth":        trial.suggest_int("max_depth", 3, 10),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
        "learning_rate":    0.1,
        "n_estimators":     1500,
        "subsample":        trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        "reg_lambda":       trial.suggest_float("reg_lambda", 0.1, 10, log=True),
        "lambdarank_pair_method":        trial.suggest_categorical("pair_method", ["topk", "mean"]),
        "lambdarank_num_pair_per_sample": trial.suggest_int("pairs", 1, 16),
        "early_stopping_rounds": 50,
    }
    m = xgb.XGBRanker(**params)
    m.fit(splits.X_train, splits.y_train, qid=splits.qid_train,
          eval_set=[(splits.X_val, splits.y_val)], eval_qid=[splits.qid_val],
          verbose=False)
    # Use our own per-query NDCG@10 on val as the search objective.
    from src.ranking.model import evaluate
    return evaluate(m, splits.X_val, splits.y_val, splits.qid_val, k_list=(10,)).ndcg[10]

study = optuna.create_study(direction="maximize")
study.optimize(objective, n_trials=40)
```

---

## Running the tests

```bash
# From the repo root
applications/ml_coding/.venv/bin/python -m pytest tests/xgboost -v
```

35 unit tests: 14 for classification (preprocessing, model contract, metrics)
and 21 for ranking (data splits, NDCG / MAP / MRR correctness, train / eval /
inference contracts).

---

## What to try next

### For classification
1. **Tune** with Optuna or `RandomizedSearchCV`.
2. **Compare** against LightGBM and CatBoost on the same splits.
3. **Swap datasets** — Higgs Boson, credit default, Otto.
4. **Explain** with `shap.TreeExplainer(model)`.

### For ranking
1. **Scale up the dataset** — MovieLens-1M, MovieLens-25M, or MSLR-WEB10K.
2. **Add content features** — TF-IDF over movie titles, embeddings from a
   pretrained model.
3. **Click-log debiasing** — set `lambdarank_unbiased=True` if your labels are
   derived from clicks.
4. **Two-stage retrieval** — use an approximate-nearest-neighbour retriever
   (FAISS) to produce candidate sets, then rerank with XGBRanker.

---

## A 5-minute mental model of XGBoost (applies to both examples)

XGBoost is **gradient boosting on decision trees**:

1. **Additive trees.** `ŷ = Σ_k f_k(x)`. Add one tree at a time.
2. **Regularised objective.**

   ```
   Obj = Σ_i  L(y_i, ŷ_i)  +  Σ_k  Ω(f_k)
                                    └─ Ω(f) = γ·T + ½·λ·||w||²
   ```
3. **Second-order split gain.**

   ```
   gain = ½·[ G_L²/(H_L+λ) + G_R²/(H_R+λ) − (G_L+G_R)²/(H_L+H_R+λ) ] − γ
   ```

For the interview-prep deep dive see `learning_note.md`.

---

## References

**Original papers**

- Chen & Guestrin (2016). *XGBoost: A Scalable Tree Boosting System*. KDD.
  <https://www.kdd.org/kdd2016/papers/files/rfp0697-chenAemb.pdf>
- Chen & He (2014). *Higgs Boson Discovery with Boosted Trees*. JMLR W&CP 42.
  <https://proceedings.mlr.press/v42/chen14.pdf>
- Burges (2010). *From RankNet to LambdaRank to LambdaMART: An Overview*.
  Microsoft Research TR-2010-82.

**Official docs**

- Python intro: <https://xgboost.readthedocs.io/en/stable/python/python_intro.html>
- Parameter reference: <https://xgboost.readthedocs.io/en/stable/parameter.html>
- Categorical support: <https://xgboost.readthedocs.io/en/stable/tutorials/categorical.html>
- Learning-to-rank tutorial: <https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html>

**Datasets**

- UCI Adult: <https://archive.ics.uci.edu/ml/datasets/Adult> (via OpenML
  <https://www.openml.org/d/1590>)
- MovieLens: <https://grouplens.org/datasets/movielens/> —
  Harper & Konstan (2015), *The MovieLens Datasets: History and Context*.
- Real LTR benchmarks to graduate to: **MSLR-WEB10K / WEB30K** from Microsoft,
  **Yahoo! Learning-to-Rank Challenge** (set 1 & 2), **LETOR 4.0**.

**Kaggle-style tutorials**

- Alexis Cook — *XGBoost* (Kaggle Intermediate ML):
  <https://www.kaggle.com/code/alexisbcook/xgboost>
- Luca Massaron — *XGBoost for tabular data*:
  <https://www.kaggle.com/code/lucamassaron/xgboost-for-tabular-data>
