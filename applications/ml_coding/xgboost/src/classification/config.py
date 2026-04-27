"""Shared constants and settings for the XGBoost Adult-Income example.

Per the project's coding-style rule, all application-wide settings live in one
module so they are easy to find and change.
"""

from __future__ import annotations

from pathlib import Path

# Paths -----------------------------------------------------------------------

APP_ROOT = Path(__file__).resolve().parents[2]  # .../xgboost/
DATA_DIR = APP_ROOT / "data"
MODEL_DIR = APP_ROOT / "models"
REPORT_DIR = APP_ROOT / "reports"

# Dataset ---------------------------------------------------------------------

OPENML_NAME = "adult"
OPENML_VERSION = 2  # tidy version with proper dtypes

TARGET_COLUMN = "class"  # OpenML's Adult target column
POSITIVE_LABEL = ">50K"  # label mapped to 1

# Categorical columns in the Adult dataset. Listed explicitly so the
# preprocessing logic is deterministic even if OpenML metadata shifts.
CATEGORICAL_COLUMNS = (
    "workclass",
    "education",
    "marital-status",
    "occupation",
    "relationship",
    "race",
    "sex",
    "native-country",
)

# Split / reproducibility ------------------------------------------------------

RANDOM_STATE = 42
TEST_SIZE = 0.2
VAL_SIZE = 0.2  # fraction of the training split reserved for early stopping

# Default XGBoost hyperparameters ---------------------------------------------
# These are a sensible starting point for binary classification on tabular data.
# Every knob has a short note so you can read the file top-to-bottom as a tutorial.

DEFAULT_XGB_PARAMS: dict = {
    # ----- Objective -----
    "objective": "binary:logistic",      # binary classification with logistic loss
    "eval_metric": "auc",                # ROC-AUC watched during training
    # ----- Tree / boosting -----
    "tree_method": "hist",                # histogram-based splits; fast + low memory
    "n_estimators": 600,                  # max boosting rounds (early stopping cuts in early)
    "learning_rate": 0.05,                # shrinkage ("eta"); smaller = more rounds needed
    "max_depth": 6,                       # tree depth; main driver of bias/variance
    "min_child_weight": 1.0,              # min sum of instance Hessians per leaf; >1 regularises
    "gamma": 0.0,                         # min loss reduction required to split (pruning)
    # ----- Stochastic regularisation -----
    "subsample": 0.9,                     # row subsample per tree
    "colsample_bytree": 0.9,              # column subsample per tree
    # ----- L1 / L2 penalties on leaf weights -----
    "reg_alpha": 0.0,                     # L1 on leaf weights
    "reg_lambda": 1.0,                    # L2 on leaf weights (XGBoost's main regulariser)
    # ----- Misc -----
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
    "enable_categorical": True,          # let XGBoost consume pandas "category" columns natively
}

# Early stopping rounds used during .fit()
EARLY_STOPPING_ROUNDS = 30
