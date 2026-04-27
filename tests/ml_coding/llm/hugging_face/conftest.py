"""Add applications/ml_coding/llm/hugging_face/ to sys.path so the
scorer modules can be imported directly in tests without turning the
app into an installed package."""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = (
    Path(__file__).resolve().parents[4]
    / "applications"
    / "ml_coding"
    / "llm"
    / "hugging_face"
)
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
