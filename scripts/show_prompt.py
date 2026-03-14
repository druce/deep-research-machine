#!/usr/bin/env python3
"""Show the full prompt that would be sent to Claude for a given task.

Usage:
    ./scripts/show_prompt.py work/FIGR_20260311 write_profile
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

from claude_runner import _build_prompt


def main() -> int:
    parser = argparse.ArgumentParser(description="Show the full Claude prompt for a task")
    parser.add_argument("workdir", help="Work directory (e.g. work/FIGR_20260311)")
    parser.add_argument("task_id", help="Task ID (e.g. write_profile)")
    args = parser.parse_args()

    workdir = Path(args.workdir)
    db_path = workdir / "research.db"
    if not db_path.exists():
        print(f"ERROR: No database at {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (args.task_id,)).fetchone()
    if not row:
        available = [r["id"] for r in conn.execute("SELECT id FROM tasks ORDER BY sort_order").fetchall()]
        conn.close()
        print(f"ERROR: Task '{args.task_id}' not found", file=sys.stderr)
        print(f"Available tasks: {', '.join(available)}", file=sys.stderr)
        return 1

    if row["skill"] != "claude":
        conn.close()
        print(f"ERROR: Task '{args.task_id}' is type '{row['skill']}', not 'claude'", file=sys.stderr)
        return 1

    conn.close()

    params = json.loads(row["params"])
    outputs = params.get("outputs", {})

    # For tasks with critic loop, initial write goes to drafts/
    n_iterations = params.get("n_iterations", 0)
    has_critic_loop = n_iterations > 0 and params.get("critic_prompt") and outputs
    if has_critic_loop:
        primary_name = next(iter(outputs.keys()))
        primary_output = outputs[primary_name]
        stem = Path(primary_output["path"]).stem
        suffix = Path(primary_output["path"]).suffix
        write_outputs = dict(outputs)
        write_outputs[primary_name] = {**primary_output, "path": f"drafts/{stem}{suffix}"}
    else:
        write_outputs = outputs

    full_prompt = _build_prompt(
        prompt=params["prompt"],
        workdir=workdir,
        label=args.task_id,
        system=params.get("system"),
        artifacts_inline=params.get("artifacts_inline"),
        expected_outputs=write_outputs if write_outputs else None,
        output_file=None,
    )

    print(full_prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
