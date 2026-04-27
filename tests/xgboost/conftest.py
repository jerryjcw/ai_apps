"""Put the Adult-Income XGBoost app's ``src`` on sys.path for tests.

The app directory is named ``xgboost/`` to match the request, which collides
with the pip-installed ``xgboost`` package. We therefore insert the app's
parent directory on sys.path rather than the app itself, and import as
``src.<module>``.
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "applications" / "ml_coding" / "xgboost"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
