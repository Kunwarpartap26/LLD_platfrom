"""Shared pytest setup.

- Adds backend/ to sys.path so tests import modules the same way uvicorn does.
- Points the app at a throwaway SQLite file so tests never touch lld_platform.db.
- Forces the heuristic evaluator so the API tests are deterministic, offline
  and free. test_evaluator.py can opt back into Gemini if a key is present.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

_tmp_db = Path(tempfile.gettempdir()) / "lld_platform_test.db"
if _tmp_db.exists():
    _tmp_db.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
os.environ.setdefault("FORCE_HEURISTIC_EVALUATOR", "1")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from main import app

    # `with` triggers the lifespan hook: create tables + seed problems.
    with TestClient(app) as test_client:
        yield test_client
