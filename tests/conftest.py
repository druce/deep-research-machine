import sys
from pathlib import Path

import pytest

# Allow imports from skills/ and tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires real API keys and network access")


# ---------------------------------------------------------------------------
# Shared db.py fixture (helpers live in db_test_helpers.py)
# ---------------------------------------------------------------------------

from db_test_helpers import run_db, DB_DAG, DB_TICKER  # noqa: E402


@pytest.fixture
def workdir(tmp_path):
    """Initialize a fresh database and return its workdir path."""
    wd = tmp_path / "test_run"
    rc, out = run_db("init", "--workdir", str(wd), "--dag", DB_DAG, "--ticker", DB_TICKER)
    assert rc == 0, f"init failed: {out}"
    return wd
