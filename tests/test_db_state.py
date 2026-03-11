"""Tests for db.py state commands: status, research-update, var-set/get, findings."""

from db_test_helpers import run_db, create_artifact_file


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_after_init(workdir):
    rc, out = run_db("status", "--workdir", str(workdir))
    assert rc == 0
    assert out["research"]["ticker"] == "TEST"
    assert out["research"]["status"] == "not started"
    assert out["tasks"]["total"] > 0
    assert out["tasks"]["pending"] > 0
    assert out["tasks"]["complete"] == 0
    assert out["artifacts"]["total"] == 0


def test_status_task_details_present(workdir):
    rc, out = run_db("status", "--workdir", str(workdir))
    assert rc == 0
    assert isinstance(out["task_details"], list)
    assert len(out["task_details"]) == out["tasks"]["total"]
    ids = {t["id"] for t in out["task_details"]}
    assert "profile" in ids


def test_status_reflects_updates(workdir):
    create_artifact_file(workdir, "artifacts/profile.json")
    run_db("task-update", "--workdir", str(workdir), "--task-id", "profile", "--status", "complete")
    run_db("artifact-add", "--workdir", str(workdir), "--task-id", "profile",
           "--name", "profile", "--path", "artifacts/profile.json", "--format", "json")

    rc, out = run_db("status", "--workdir", str(workdir))
    assert rc == 0
    assert out["tasks"]["complete"] == 1
    assert out["tasks"]["pending"] == out["tasks"]["total"] - 1
    assert out["artifacts"]["total"] == 1


# ---------------------------------------------------------------------------
# research-update
# ---------------------------------------------------------------------------


def test_research_update_valid(workdir):
    rc, out = run_db("research-update", "--workdir", str(workdir), "--status", "running")
    assert rc == 0
    assert out["new_status"] == "running"
    _, status = run_db("status", "--workdir", str(workdir))
    assert status["research"]["status"] == "running"


def test_research_update_all_statuses(workdir):
    for status in ("not started", "running", "complete", "failed"):
        rc, out = run_db("research-update", "--workdir", str(workdir), "--status", status)
        assert rc == 0, f"failed for status={status}: {out}"
        assert out["new_status"] == status


# ---------------------------------------------------------------------------
# var-set / var-get
# ---------------------------------------------------------------------------


def test_var_set_and_get(workdir):
    rc, out = run_db("var-set", "--workdir", str(workdir),
                     "--name", "symbol", "--value", "AAPL", "--source-task", "profile")
    assert rc == 0
    assert out["status"] == "ok"
    assert out["name"] == "symbol"
    assert out["value"] == "AAPL"

    rc, out = run_db("var-get", "--workdir", str(workdir), "--name", "symbol")
    assert rc == 0
    assert out["name"] == "symbol"
    assert out["value"] == "AAPL"
    assert out["source_task"] == "profile"


def test_var_get_all(workdir):
    run_db("var-set", "--workdir", str(workdir),
           "--name", "symbol", "--value", "AAPL", "--source-task", "profile")
    run_db("var-set", "--workdir", str(workdir),
           "--name", "company_name", "--value", "Apple Inc.", "--source-task", "profile")

    rc, out = run_db("var-get", "--workdir", str(workdir))
    assert rc == 0
    assert out == {"company_name": "Apple Inc.", "symbol": "AAPL"}


def test_var_get_empty(workdir):
    rc, out = run_db("var-get", "--workdir", str(workdir))
    assert rc == 0
    assert out == {}


def test_var_get_missing_name(workdir):
    rc, out = run_db("var-get", "--workdir", str(workdir), "--name", "nonexistent")
    assert rc == 1
    assert out["status"] == "error"


def test_var_set_upserts(workdir):
    """Setting the same variable twice updates the value."""
    run_db("var-set", "--workdir", str(workdir),
           "--name", "symbol", "--value", "OLD", "--source-task", "profile")
    run_db("var-set", "--workdir", str(workdir),
           "--name", "symbol", "--value", "NEW", "--source-task", "profile")

    rc, out = run_db("var-get", "--workdir", str(workdir), "--name", "symbol")
    assert rc == 0
    assert out["value"] == "NEW"


def test_var_set_stored_in_task_params(workdir):
    """Profile task params should include sets_vars from the YAML."""
    rc, out = run_db("task-get", "--workdir", str(workdir), "--task-id", "profile")
    assert rc == 0
    params = out["params"]
    assert "sets_vars" in params
    assert "symbol" in params["sets_vars"]
    assert params["sets_vars"]["symbol"]["key"] == "symbol"
    assert "company_name" in params["sets_vars"]
    assert params["sets_vars"]["company_name"]["key"] == "company_name"


# ---------------------------------------------------------------------------
# finding-add / finding-list
# ---------------------------------------------------------------------------


def test_finding_add(workdir):
    rc, out = run_db(
        "finding-add", "--workdir", str(workdir),
        "--task-id", "profile",
        "--content", "NVDA competes with AMD and Intel in discrete GPUs.",
        "--source", "artifacts/sec_10k_item1.md",
        "--tags", "competitive", "supply_chain",
    )
    assert rc == 0
    assert out["status"] == "ok"
    assert "id" in out


def test_finding_list_all(workdir):
    run_db("finding-add", "--workdir", str(workdir),
           "--task-id", "profile",
           "--content", "NVDA dominates GPU market.",
           "--source", "10-K", "--tags", "competitive")
    run_db("finding-add", "--workdir", str(workdir),
           "--task-id", "fundamental",
           "--content", "NVDA revenue grew 120% YoY.",
           "--source", "income_statement.csv", "--tags", "financial")
    rc, out = run_db("finding-list", "--workdir", str(workdir))
    assert rc == 0
    assert len(out) == 2


def test_finding_list_filter_by_tags(workdir):
    run_db("finding-add", "--workdir", str(workdir),
           "--task-id", "profile",
           "--content", "AMD is gaining share in data center.",
           "--source", "10-K", "--tags", "competitive", "financial")
    run_db("finding-add", "--workdir", str(workdir),
           "--task-id", "fundamental",
           "--content", "Gross margin expanded to 73%.",
           "--source", "income_statement.csv", "--tags", "financial")
    rc, out = run_db("finding-list", "--workdir", str(workdir), "--tags", "competitive")
    assert rc == 0
    assert len(out) == 1
    assert "AMD" in out[0]["content"]


def test_finding_add_requires_task_id(workdir):
    rc, out = run_db(
        "finding-add", "--workdir", str(workdir),
        "--content", "some content",
        "--tags", "competitive",
    )
    assert rc != 0
