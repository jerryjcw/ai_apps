"""Put the torch_trainval_reco app on sys.path for tests (matches xgboost sibling).

The app's package entry point is `src.*`, so we add the project directory —
not the `src/` itself — to sys.path.
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = (
    Path(__file__).resolve().parents[3]
    / "applications"
    / "ml_coding"
    / "torch_trainval_reco"
)
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
