"""Tests for db.py artifact commands: artifact-add, artifact-list."""

from db_test_helpers import run_db, create_artifact_file


# ---------------------------------------------------------------------------
# artifact-add
# ---------------------------------------------------------------------------


def test_artifact_add_valid(workdir):
    create_artifact_file(workdir, "artifacts/profile.json")
    rc, out = run_db(
        "artifact-add", "--workdir", str(workdir),
        "--task-id", "profile", "--name", "profile",
        "--path", "artifacts/profile.json", "--format", "json",
        "--summary", "Company profile data",
    )
    assert rc == 0
    assert out["status"] == "ok"
    assert out["name"] == "profile"
    assert out["task"] == "profile"
    assert "artifact_id" in out


def test_artifact_add_upserts(workdir):
    """Adding the same (task, name) twice updates, not duplicates."""
    create_artifact_file(workdir, "artifacts/profile.json")
    for _ in range(2):
        run_db(
            "artifact-add", "--workdir", str(workdir),
            "--task-id", "profile", "--name", "profile",
            "--path", "artifacts/profile.json", "--format", "json",
        )
    _, artifacts = run_db("artifact-list", "--workdir", str(workdir), "--task", "profile")
    assert len([a for a in artifacts if a["name"] == "profile"]) == 1


def test_artifact_add_missing_task(workdir):
    rc, out = run_db(
        "artifact-add", "--workdir", str(workdir),
        "--task-id", "nonexistent", "--name", "out",
        "--path", "artifacts/out.json", "--format", "json",
    )
    assert rc == 1
    assert out["status"] == "error"


# ---------------------------------------------------------------------------
# artifact-list
# ---------------------------------------------------------------------------


def test_artifact_list_empty(workdir):
    rc, out = run_db("artifact-list", "--workdir", str(workdir))
    assert rc == 0
    assert out == []


def test_artifact_list_all(workdir):
    create_artifact_file(workdir, "artifacts/profile.json")
    create_artifact_file(workdir, "artifacts/chart.png", content="fake png")
    run_db("artifact-add", "--workdir", str(workdir), "--task-id", "profile",
           "--name", "profile", "--path", "artifacts/profile.json", "--format", "json")
    run_db("artifact-add", "--workdir", str(workdir), "--task-id", "technical",
           "--name", "chart", "--path", "artifacts/chart.png", "--format", "png")

    rc, out = run_db("artifact-list", "--workdir", str(workdir))
    assert rc == 0
    assert len(out) == 2
    names = {a["name"] for a in out}
    assert names == {"profile", "chart"}


def test_artifact_list_filter_by_task(workdir):
    create_artifact_file(workdir, "artifacts/profile.json")
    create_artifact_file(workdir, "artifacts/chart.png", content="fake png")
    run_db("artifact-add", "--workdir", str(workdir), "--task-id", "profile",
           "--name", "profile", "--path", "artifacts/profile.json", "--format", "json")
    run_db("artifact-add", "--workdir", str(workdir), "--task-id", "technical",
           "--name", "chart", "--path", "artifacts/chart.png", "--format", "png")

    rc, out = run_db("artifact-list", "--workdir", str(workdir), "--task", "profile")
    assert rc == 0
    assert len(out) == 1
    assert out[0]["name"] == "profile"
    assert out[0]["task_id"] == "profile"


def test_artifact_list_fields(workdir):
    create_artifact_file(workdir, "artifacts/profile.json")
    run_db("artifact-add", "--workdir", str(workdir), "--task-id", "profile",
           "--name", "profile", "--path", "artifacts/profile.json", "--format", "json",
           "--description", "Company identity and valuation snapshot",
           "--source", "yfinance", "--summary", "Profile data")
    _, out = run_db("artifact-list", "--workdir", str(workdir))
    a = out[0]
    assert a["task_id"] == "profile"
    assert a["name"] == "profile"
    assert a["path"] == "artifacts/profile.json"
    assert a["format"] == "json"
    assert a["description"] == "Company identity and valuation snapshot"
    assert a["source"] == "yfinance"
    assert a["summary"] == "Profile data"


def test_artifact_description_in_list(workdir):
    """artifact-list includes description field for all artifacts."""
    create_artifact_file(workdir, "artifacts/profile.json")
    create_artifact_file(workdir, "artifacts/chart.png", content="fake png")
    run_db("artifact-add", "--workdir", str(workdir), "--task-id", "profile",
           "--name", "profile", "--path", "artifacts/profile.json", "--format", "json",
           "--description", "Company profile data")
    run_db("artifact-add", "--workdir", str(workdir), "--task-id", "technical",
           "--name", "chart", "--path", "artifacts/chart.png", "--format", "png")

    rc, out = run_db("artifact-list", "--workdir", str(workdir))
    assert rc == 0
    for a in out:
        assert "description" in a
    # Explicit description is preserved; YAML fallback populates the other
    descs = {a["name"]: a["description"] for a in out}
    assert descs["profile"] == "Company profile data"
    # chart gets its description from the YAML output definition
    assert descs["chart"] is not None
    assert len(descs["chart"]) > 0


def test_output_descriptions_in_task_params(workdir):
    """Output descriptions from YAML are stored in task params."""
    rc, out = run_db("task-get", "--workdir", str(workdir), "--task-id", "profile")
    assert rc == 0
    outputs = out["params"]["outputs"]
    assert "description" in outputs["profile"]
    assert len(outputs["profile"]["description"]) > 0
    # peers_list is defined in the 'peers' task, not 'profile'
    rc2, out2 = run_db("task-get", "--workdir", str(workdir), "--task-id", "peers")
    assert rc2 == 0
    peers_outputs = out2["params"]["outputs"]
    assert "description" in peers_outputs["peers_list"]
    assert len(peers_outputs["peers_list"]["description"]) > 0
