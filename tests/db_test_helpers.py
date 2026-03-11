"""Shared helpers for db.py test modules."""

import json
import subprocess
from pathlib import Path

_CWD = str(Path(__file__).parent.parent)
_DB_PY = ["uv", "run", "python", "skills/db.py"]
DB_DAG = "dags/sra.yaml"
DB_TICKER = "TEST"


def run_db(*args):
    """Run db.py with the given args; return (returncode, parsed_json)."""
    result = subprocess.run(
        _DB_PY + list(args),
        capture_output=True,
        text=True,
        cwd=_CWD,
    )
    try:
        return result.returncode, json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.returncode, result.stdout


def create_artifact_file(workdir, rel_path, content="{}"):
    """Create a file at workdir/rel_path so artifact-add validation passes."""
    p = Path(workdir) / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
