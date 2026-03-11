"""Tests for DAG schema cross-reference validation, variable substitution, and integration."""

import json
import subprocess
from pathlib import Path

import pytest
from schema import validate_dag, load_dag


# ---------------------------------------------------------------------------
# validate_dag — cross-reference checks
# ---------------------------------------------------------------------------


def test_validate_dag_valid():
    raw = {
        "dag": {"version": 2, "name": "Test"},
        "tasks": {
            "a": {"description": "A", "type": "shell", "config": {"command": "echo a"}},
            "b": {"description": "B", "type": "shell", "depends_on": ["a"], "config": {"command": "echo b"}},
        },
    }
    dag = validate_dag(raw)
    assert len(dag.tasks) == 2


def test_validate_dag_bad_dependency_ref():
    raw = {
        "dag": {"version": 2, "name": "Test"},
        "tasks": {
            "a": {"description": "A", "type": "shell", "depends_on": ["nonexistent"], "config": {"command": "echo a"}},
        },
    }
    with pytest.raises(ValueError, match="nonexistent"):
        validate_dag(raw)


def test_validate_dag_cycle():
    raw = {
        "dag": {"version": 2, "name": "Test"},
        "tasks": {
            "a": {"description": "A", "type": "shell", "depends_on": ["b"], "config": {"command": "echo a"}},
            "b": {"description": "B", "type": "shell", "depends_on": ["a"], "config": {"command": "echo b"}},
        },
    }
    with pytest.raises(ValueError, match="[Cc]ycle"):
        validate_dag(raw)


def test_validate_dag_duplicate_output_paths():
    raw = {
        "dag": {"version": 2, "name": "Test"},
        "tasks": {
            "a": {
                "description": "A",
                "type": "shell",
                "config": {"command": "echo a"},
                "outputs": {"out": {"path": "same.txt", "format": "txt"}},
            },
            "b": {
                "description": "B",
                "type": "shell",
                "config": {"command": "echo b"},
                "outputs": {"out": {"path": "same.txt", "format": "txt"}},
            },
        },
    }
    with pytest.raises(ValueError, match="same.txt"):
        validate_dag(raw)


# ---------------------------------------------------------------------------
# validate_dag — critic-optimizer config checks
# ---------------------------------------------------------------------------


def test_validate_dag_critic_missing_prompts():
    """n_iterations > 0 without both prompts should fail validation."""
    raw = {
        "dag": {"version": 2, "name": "Test"},
        "tasks": {
            "write": {
                "description": "Write",
                "type": "claude",
                "config": {
                    "prompt": "Write a section",
                    "n_iterations": 1,
                    "critic_prompt": "Critique it",
                    # rewrite_prompt missing
                },
                "outputs": {"section": {"path": "artifacts/section.md", "format": "md"}},
            },
        },
    }
    with pytest.raises(ValueError, match="rewrite_prompt"):
        validate_dag(raw)


def test_validate_dag_critic_missing_critic_prompt():
    """n_iterations > 0 without critic_prompt should fail."""
    raw = {
        "dag": {"version": 2, "name": "Test"},
        "tasks": {
            "write": {
                "description": "Write",
                "type": "claude",
                "config": {
                    "prompt": "Write a section",
                    "n_iterations": 1,
                    # critic_prompt missing
                    "rewrite_prompt": "Rewrite it",
                },
                "outputs": {"section": {"path": "artifacts/section.md", "format": "md"}},
            },
        },
    }
    with pytest.raises(ValueError, match="critic_prompt"):
        validate_dag(raw)


def test_validate_dag_critic_zero_iterations_ok():
    """n_iterations=0 with no prompts is fine (default)."""
    raw = {
        "dag": {"version": 2, "name": "Test"},
        "tasks": {
            "write": {
                "description": "Write",
                "type": "claude",
                "config": {"prompt": "Write a section"},
                "outputs": {"section": {"path": "artifacts/section.md", "format": "md"}},
            },
        },
    }
    dag = validate_dag(raw)
    assert dag.tasks["write"].config.n_iterations == 0


def test_validate_dag_critic_valid_config():
    """Complete critic config passes validation."""
    raw = {
        "dag": {"version": 2, "name": "Test"},
        "tasks": {
            "write": {
                "description": "Write",
                "type": "claude",
                "config": {
                    "prompt": "Write a section",
                    "n_iterations": 1,
                    "critic_prompt": "Critique at ${draft_path}",
                    "rewrite_prompt": "Rewrite based on ${critique_path}",
                    "critic_disallowed_tools": ["yfinance"],
                    "rewrite_disallowed_tools": ["yfinance"],
                },
                "outputs": {"section": {"path": "artifacts/section.md", "format": "md"}},
            },
        },
    }
    dag = validate_dag(raw)
    assert dag.tasks["write"].config.n_iterations == 1


# ---------------------------------------------------------------------------
# load_dag — variable substitution
# ---------------------------------------------------------------------------


def test_load_dag_substitutes_variables():
    raw = {
        "dag": {"version": 2, "name": "Test", "inputs": {"ticker": "${ticker}", "workdir": "${workdir}"}},
        "tasks": {
            "profile": {
                "description": "Get profile",
                "type": "python",
                "config": {"script": "skills/run.py", "args": {"ticker": "${ticker}", "workdir": "${workdir}"}},
                "outputs": {"profile": {"path": "artifacts/profile.json", "format": "json"}},
            },
        },
    }
    variables = {"ticker": "AAPL", "workdir": "work/AAPL_20260223"}
    dag = load_dag(raw, variables)
    task = dag.tasks["profile"]
    assert task.config.args["ticker"] == "AAPL"
    assert task.config.args["workdir"] == "work/AAPL_20260223"


def test_load_dag_substitutes_in_prompt():
    raw = {
        "dag": {"version": 2, "name": "Test"},
        "tasks": {
            "write": {
                "description": "Write",
                "type": "claude",
                "config": {
                    "prompt": "Analyze ${ticker} stock",
                },
            },
        },
    }
    variables = {"ticker": "MSFT"}
    dag = load_dag(raw, variables)
    assert dag.tasks["write"].config.prompt == "Analyze MSFT stock"


# ---------------------------------------------------------------------------
# Integration: validate actual project DAG file
# ---------------------------------------------------------------------------


def test_sra_yaml_validates():
    """The actual project DAG file passes v2 validation."""
    from pathlib import Path
    import yaml

    yaml_path = Path(__file__).parent.parent / "dags" / "sra.yaml"
    with yaml_path.open() as f:
        raw = yaml.safe_load(f)
    dag = validate_dag(raw)
    assert dag.dag.version == 2
    assert len(dag.tasks) > 0
    # Verify all task types are valid
    for task_id, task in dag.tasks.items():
        assert task.type in ("python", "claude", "shell"), f"Bad type in {task_id}"


def test_sra_yaml_critic_config():
    """Write tasks in the actual DAG have valid critic-optimizer config."""
    from pathlib import Path
    import yaml

    yaml_path = Path(__file__).parent.parent / "dags" / "sra.yaml"
    with yaml_path.open() as f:
        raw = yaml.safe_load(f)
    dag = validate_dag(raw)

    write_tasks = [tid for tid in dag.tasks if tid.startswith("write_")]
    # Exclude write_conclusion and write_intro — they don't need critic loops
    section_writers = [
        tid for tid in write_tasks
        if tid not in ("write_conclusion", "write_intro")
    ]
    assert len(section_writers) == 7

    for tid in section_writers:
        task = dag.tasks[tid]
        assert task.config.n_iterations >= 1, f"{tid} should have n_iterations >= 1"
        assert task.config.critic_prompt, f"{tid} missing critic_prompt"
        assert task.config.rewrite_prompt, f"{tid} missing rewrite_prompt"
        assert "${draft_path}" in task.config.critic_prompt, f"{tid} critic_prompt missing ${{draft_path}}"
        assert "${critique_path}" in task.config.critic_prompt, f"{tid} critic_prompt missing ${{critique_path}}"
        assert "${draft_path}" in task.config.rewrite_prompt, f"{tid} rewrite_prompt missing ${{draft_path}}"
        assert "${rewrite_path}" in task.config.rewrite_prompt, f"{tid} rewrite_prompt missing ${{rewrite_path}}"


# ---------------------------------------------------------------------------
# Integration: db.py init and validate with v2 YAML
# ---------------------------------------------------------------------------


def test_db_init_with_v2_yaml(tmp_path):
    """db.py init successfully loads the v2 YAML and populates the database."""
    workdir = tmp_path / "test_run"
    result = subprocess.run(
        [
            "uv", "run", "python", "skills/db.py", "init",
            "--workdir", str(workdir),
            "--dag", "dags/sra.yaml",
            "--ticker", "TEST",
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["tasks"] > 0


def test_db_validate_command_valid():
    """db.py validate succeeds on valid v2 YAML."""
    result = subprocess.run(
        [
            "uv", "run", "python", "skills/db.py", "validate",
            "--dag", "dags/sra.yaml",
            "--ticker", "TEST",
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    output = json.loads(result.stdout)
    assert output["status"] == "ok"


def test_db_validate_command_invalid(tmp_path):
    """db.py validate fails on invalid YAML with clear error."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("""
dag:
  version: 2
  name: Bad
tasks:
  broken:
    description: Missing type
    config:
      command: echo hi
""")
    result = subprocess.run(
        [
            "uv", "run", "python", "skills/db.py", "validate",
            "--dag", str(bad_yaml),
            "--ticker", "TEST",
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode == 1
