"""Constants and default hyperparameters for the MovieLens ranking example."""

from __future__ import annotations

from pathlib import Path

# Paths -----------------------------------------------------------------------

APP_ROOT = Path(__file__).resolve().parents[2]  # .../xgboost/
DATA_DIR = APP_ROOT / "data"
MODEL_DIR = APP_ROOT / "models"
REPORT_DIR = APP_ROOT / "reports"

# Dataset ---------------------------------------------------------------------

ML100K_URL = "https://files.grouplens.org/datasets/movielens/ml-100k.zip"
ML100K_DIR_NAME = "ml-100k"  # directory after unzipping

# Column schemas from the README that ships with ml-100k.
RATINGS_COLUMNS = ("user_id", "movie_id", "rating", "timestamp")
MOVIE_COLUMNS = (
    "movie_id", "title", "release_date", "video_release_date", "imdb_url",
    # 19 genre flags, in the order defined by u.genre
    "unknown", "Action", "Adventure", "Animation", "Childrens",
    "Comedy", "Crime", "Documentary", "Drama", "Fantasy",
    "Film-Noir", "Horror", "Musical", "Mystery", "Romance",
    "Sci-Fi", "Thriller", "War", "Western",
)
GENRE_COLUMNS = MOVIE_COLUMNS[5:]  # the 19 one-hot genre flags

# Only keep users with at least this many ratings. Tiny groups produce noisy
# NDCG estimates and can't be split meaningfully.
MIN_RATINGS_PER_USER = 20

# Split / reproducibility -----------------------------------------------------

RANDOM_STATE = 42
TEST_SIZE = 0.2
VAL_SIZE = 0.2  # fraction of the train split used for early stopping

# Default XGBRanker hyperparameters -------------------------------------------
# A sensible starting point for graded-relevance LTR on MovieLens.

DEFAULT_XGB_PARAMS: dict = {
    # ----- LTR objective -----
    # rank:ndcg  — LambdaRank with NDCG surrogate; best for graded labels (1–5).
    # rank:pairwise — classic RankNet pairwise.
    # rank:map   — LambdaRank with MAP; best when labels are 0/1.
    "objective": "rank:ndcg",
    # XGBoost's built-in "map@k" requires binary labels. We compute MAP
    # ourselves in Python against binarised relevance (see model.evaluate).
    "eval_metric": ["ndcg@5", "ndcg@10"],
    # ----- LambdaRank knobs (XGBoost >= 2.0) -----
    "lambdarank_pair_method": "topk",        # "mean" or "topk"; topk focuses on head
    "lambdarank_num_pair_per_sample": 8,      # how many (pos, neg) pairs sampled per query
    # ----- Tree / boosting -----
    "tree_method": "hist",
    "n_estimators": 600,
    "learning_rate": 0.05,
    "max_depth": 6,
    "min_child_weight": 1.0,
    "gamma": 0.0,
    # ----- Stochastic regularisation -----
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    # ----- L1 / L2 -----
    "reg_alpha": 0.0,
    "reg_lambda": 1.0,
    # ----- Misc -----
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}

EARLY_STOPPING_ROUNDS = 30

# NDCG cuts we report at evaluation time.
NDCG_K_LIST = (5, 10, 20)
