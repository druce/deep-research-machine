"""Tests for db.py init and validate commands."""

from db_test_helpers import run_db, DB_DAG, DB_TICKER


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_init_creates_db(tmp_path):
    wd = tmp_path / "run"
    rc, out = run_db("init", "--workdir", str(wd), "--dag", DB_DAG, "--ticker", DB_TICKER)
    assert rc == 0
    assert out["status"] == "ok"
    assert out["tasks"] > 0
    assert (wd / "research.db").exists()


def test_init_idempotent_workdir(tmp_path):
    """init creates the workdir if it doesn't exist."""
    wd = tmp_path / "nested" / "run"
    rc, out = run_db("init", "--workdir", str(wd), "--dag", DB_DAG, "--ticker", DB_TICKER)
    assert rc == 0
    assert wd.exists()


def test_init_missing_dag(tmp_path):
    wd = tmp_path / "run"
    rc, out = run_db("init", "--workdir", str(wd), "--dag", "nonexistent.yaml", "--ticker", DB_TICKER)
    assert rc == 1
    assert out["status"] == "error"


def test_init_stores_drafts_dir(workdir):
    """init stores drafts_dir from DAG header in research table."""
    import sqlite3
    conn = sqlite3.connect(str(workdir / "research.db"))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT drafts_dir FROM research LIMIT 1").fetchone()
    conn.close()
    assert row["drafts_dir"] == "drafts"


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def test_validate_valid_dag():
    rc, out = run_db("validate", "--dag", DB_DAG, "--ticker", DB_TICKER)
    assert rc == 0
    assert out["status"] == "ok"
    assert out["tasks"] > 0
    assert "python" in out["task_types"]


def test_validate_invalid_dag(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "dag:\n  version: 2\n  name: Bad\ntasks:\n"
        "  broken:\n    description: Missing type\n    config:\n      command: echo hi\n"
    )
    rc, out = run_db("validate", "--dag", str(bad))
    assert rc == 1
    assert out["status"] == "error"


def test_validate_missing_file(tmp_path):
    rc, out = run_db("validate", "--dag", str(tmp_path / "nope.yaml"))
    assert rc == 1
    assert out["status"] == "error"
