"""Shared fixtures for auto_research tests."""

import sys
from pathlib import Path

import pytest

# Make helpers importable
HELPERS_DIR = Path(__file__).resolve().parent.parent.parent / "applications" / "auto_research"
if str(HELPERS_DIR) not in sys.path:
    sys.path.insert(0, str(HELPERS_DIR))


@pytest.fixture
def workspace(tmp_path):
    """Provide a temp workspace with proposal_space initialized."""
    from helpers.state_manager import init_workspace

    init_workspace(tmp_path)
    return tmp_path
