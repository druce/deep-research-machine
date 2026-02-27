# research.py Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a single-file async Python orchestrator (`research.py`) that replaces the `/research` and `/taskrunner` Claude Code skills for running the equity research DAG pipeline.

**Architecture:** `research.py` reads the DAG YAML, initializes SQLite via `db.py` subprocess calls, then runs waves of tasks as async subprocesses. Python tasks run via `uv run python`, Claude tasks via `claude --dangerously-skip-permissions -p`. All DB writes are centralized in the orchestrator after each wave completes. A `manifest.json` file is maintained as an artifact index for Claude tasks to read.

**Tech Stack:** Python 3.12+, asyncio, subprocess, YAML, JSON. Existing `db.py` for state, `schema.py` for validation.

**Design doc:** `docs/plans/2026-02-27-research-py-design.md`

---

### Task 1: Update DAG YAML — Replace `tools` with `disallowed_tools`

**Files:**
- Modify: `dags/sra.yaml:121,195,213,243,271`

**Step 1: Update write_body task (currently `tools: all`)**

Change line 121 from:
```yaml
      tools: all
```
to:
```yaml
      disallowed_tools: []
```

This means full access — no tools blocked.

**Step 2: Update write_conclusion task (currently `tools: [read, write]`)**

Change line 195 from:
```yaml
      tools: [read, write]
```
to:
```yaml
      disallowed_tools: [yfinance, alphavantage, brave-search, perplexity-ask, wikipedia, playwright, fetch, filesystem]
```

These tasks only need to read/write local files — block all MCP servers.

**Step 3: Repeat for write_intro (line 213), critique_body_final (line 243), polish_body_final (line 271)**

Same change as Step 2 for each.

**Step 4: Validate the DAG**

Run: `uv run python ./skills/db.py validate --dag dags/sra.yaml --ticker TEST`

Expected: `{"status": "ok", "version": 2, ...}`

**Step 5: Commit**

```bash
git add dags/sra.yaml
git commit -m "Replace tools with disallowed_tools in DAG claude task configs"
```

---

### Task 2: Write research.py — CLI and Initialization

**Files:**
- Create: `research.py`

**Step 1: Write the CLI skeleton with argparse and init logic**

```python
#!/usr/bin/env python3
"""
research.py — Async DAG orchestrator for equity research pipeline.

Reads DAG YAML, initializes SQLite via db.py, runs waves of tasks as
async subprocesses. Python tasks via `uv run python`, Claude tasks via
`claude --dangerously-skip-permissions -p`.

Usage:
    ./research.py TICKER [--dag dags/sra.yaml] [--date YYYYMMDD]
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

DB_PY = Path(__file__).parent / "skills" / "db.py"


def log(msg: str) -> None:
    """Print timestamped message to stderr."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr)


async def run_db(*args: str) -> dict:
    """Call db.py with args, return parsed JSON stdout."""
    cmd = ["uv", "run", "python", str(DB_PY)] + list(args)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode().strip() or stdout.decode().strip()
        raise RuntimeError(f"db.py {args[0]} failed (rc={proc.returncode}): {err}")
    return json.loads(stdout.decode())


async def init_pipeline(ticker: str, dag: str, date: str) -> Path:
    """Validate DAG, create workdir, initialize DB. Return workdir Path."""
    # Validate
    result = await run_db("validate", "--dag", dag, "--ticker", ticker)
    log(f"DAG validated: {result['tasks']} tasks")

    # Init
    workdir = Path("work") / f"{ticker}_{date}"
    result = await run_db(
        "init", "--workdir", str(workdir), "--dag", dag,
        "--ticker", ticker, "--date", date,
    )
    log(f"DB initialized: {result['workdir']}")

    # Mark running
    await run_db("research-update", "--workdir", str(workdir), "--status", "running")

    return workdir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run equity research DAG pipeline")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g. AAPL)")
    parser.add_argument("--dag", default="dags/sra.yaml", help="DAG YAML file")
    parser.add_argument(
        "--date", default=datetime.now().strftime("%Y%m%d"),
        help="Date string YYYYMMDD (default: today)",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    ticker = args.ticker.upper()

    log(f"Starting research pipeline for {ticker}")

    try:
        workdir = await init_pipeline(ticker, args.dag, args.date)
    except RuntimeError as e:
        log(f"Initialization failed: {e}")
        return 1

    log(f"Workdir: {workdir}")

    # TODO: wave loop (Task 3)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

**Step 2: Make executable and test init**

Run:
```bash
chmod +x research.py
```

Run a dry test (will create a test workdir):
```bash
uv run python research.py TEST --dag dags/sra.yaml --date 99990101
```

Expected: prints "Starting research pipeline for TEST", "DAG validated: N tasks", "DB initialized: work/TEST_99990101", then exits 0.

**Step 3: Clean up test workdir**

```bash
rm -rf work/TEST_99990101
```

**Step 4: Commit**

```bash
git add research.py
git commit -m "Add research.py skeleton with CLI and DB init"
```

---

### Task 3: Write manifest.json Builder

**Files:**
- Modify: `research.py`

**Step 1: Add the write_manifest function**

Add after the `run_db` function:

```python
async def write_manifest(workdir: Path) -> None:
    """Query all artifacts from DB, write manifest.json for existing files only."""
    artifacts = await run_db("artifact-list", "--workdir", str(workdir))
    manifest = []
    for a in artifacts:
        file_path = workdir / a["path"]
        if file_path.exists():
            manifest.append({
                "description": a.get("description") or "",
                "format": a.get("format", ""),
                "summary": a.get("summary"),
                "file": a["path"],
            })
    manifest_path = workdir / "artifacts" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    log(f"Manifest updated: {len(manifest)} artifacts")
```

**Step 2: Commit**

```bash
git add research.py
git commit -m "Add manifest.json builder to research.py"
```

---

### Task 4: Write Task Dispatchers (Python + Claude)

**Files:**
- Modify: `research.py`

**Step 1: Add the Python task dispatcher**

Add after `write_manifest`:

```python
async def run_python_task(task: dict, workdir: Path, ticker: str) -> dict:
    """Run a python task as subprocess. Return result dict."""
    params = task["params"]
    script = params["script"]
    args_dict = params.get("args", {})

    # Build command: uv run python {script} {ticker} --key value ...
    cmd = ["uv", "run", "python", script]

    # ticker is positional if present in args
    if "ticker" in args_dict:
        cmd.append(args_dict["ticker"])

    # Remaining args as --key value (underscore → hyphen)
    for key, val in args_dict.items():
        if key == "ticker":
            continue
        flag = f"--{key.replace('_', '-')}"
        cmd.append(flag)
        cmd.append(str(val))

    stderr_log = workdir / f"{task['id']}_stderr.log"

    log(f"  [{task['id']}] Running: {' '.join(cmd)}")

    with open(stderr_log, "w") as err_f:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=err_f,
        )
        stdout_bytes, _ = await proc.communicate()

    stdout = stdout_bytes.decode().strip()

    # Parse JSON manifest from stdout
    try:
        manifest = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "task_id": task["id"],
            "status": "failed",
            "error": f"Invalid JSON stdout (rc={proc.returncode}): {stdout[:200]}",
            "artifacts": [],
            "manifest": None,
        }

    if proc.returncode >= 2 or manifest.get("status") == "failed":
        return {
            "task_id": task["id"],
            "status": "failed",
            "error": manifest.get("error") or f"Exit code {proc.returncode}",
            "artifacts": manifest.get("artifacts", []),
            "manifest": manifest,
        }

    return {
        "task_id": task["id"],
        "status": "complete",
        "error": None,
        "artifacts": manifest.get("artifacts", []),
        "manifest": manifest,
    }
```

**Step 2: Add the Claude task dispatcher**

```python
async def run_claude_task(task: dict, workdir: Path) -> dict:
    """Run a claude task via claude CLI. Return result dict."""
    params = task["params"]
    abs_workdir = str(workdir.resolve())

    # Build prompt
    parts = []
    if params.get("system"):
        parts.append(params["system"])
        parts.append("")

    parts.append(f"Working directory: {abs_workdir}")
    parts.append("All research data is in the artifacts/ subdirectory.")
    parts.append("Read artifacts/manifest.json for a description of all available files.")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(params["prompt"])

    # Add save instructions for each output
    outputs = params.get("outputs", {})
    for out_name, out_def in outputs.items():
        out_path = out_def["path"]
        if out_path not in params["prompt"]:
            parts.append("")
            parts.append(f"Save your output for \"{out_name}\" to {abs_workdir}/{out_path}")

    prompt = "\n".join(parts)

    # Build claude command
    cmd = ["claude", "--dangerously-skip-permissions", "--verbose", "-p"]

    disallowed = params.get("disallowed_tools", [])
    if disallowed:
        cmd.extend(["--disallowed-tools"] + disallowed)

    if params.get("model"):
        cmd.extend(["--model", params["model"]])

    log(f"  [{task['id']}] Running claude task")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate(input=prompt.encode())

    # Check if expected output files were produced
    missing = []
    for out_name, out_def in outputs.items():
        out_path = workdir / out_def["path"]
        if not out_path.exists():
            missing.append(out_def["path"])

    if missing:
        return {
            "task_id": task["id"],
            "status": "failed",
            "error": f"Missing output files: {', '.join(missing)}",
            "artifacts": [],
            "manifest": None,
        }

    return {
        "task_id": task["id"],
        "status": "complete",
        "error": None,
        "artifacts": [
            {"name": name, "path": odef["path"], "format": odef["format"]}
            for name, odef in outputs.items()
        ],
        "manifest": None,
    }
```

**Step 3: Add the unified dispatch function**

```python
async def dispatch_task(task: dict, workdir: Path, ticker: str) -> dict:
    """Dispatch a task based on its type."""
    task_type = task["skill"]
    if task_type == "python":
        return await run_python_task(task, workdir, ticker)
    elif task_type == "claude":
        return await run_claude_task(task, workdir)
    else:
        return {
            "task_id": task["id"],
            "status": "failed",
            "error": f"Unknown task type: {task_type}",
            "artifacts": [],
            "manifest": None,
        }
```

**Step 4: Commit**

```bash
git add research.py
git commit -m "Add python and claude task dispatchers to research.py"
```

---

### Task 5: Write the Wave Loop and Post-Wave DB Updates

**Files:**
- Modify: `research.py`

**Step 1: Add post-wave processing function**

```python
async def process_results(results: list[dict], workdir: Path, tasks: list[dict]) -> tuple[int, int]:
    """Process wave results: register artifacts, extract vars, update DB. Return (completed, failed) counts."""
    completed = 0
    failed = 0

    # Build task lookup for sets_vars
    task_lookup = {t["id"]: t for t in tasks}

    for result in results:
        task_id = result["task_id"]
        task_def = task_lookup.get(task_id, {})
        params = task_def.get("params", {})

        if result["status"] == "complete":
            completed += 1

            # Register artifacts
            for artifact in result["artifacts"]:
                try:
                    add_args = [
                        "artifact-add", "--workdir", str(workdir),
                        "--task-id", task_id,
                        "--name", artifact.get("name", "output"),
                        "--path", artifact["path"],
                        "--format", artifact.get("format", "unknown"),
                    ]
                    if artifact.get("source"):
                        add_args.extend(["--source", artifact["source"]])
                    if artifact.get("summary"):
                        add_args.extend(["--summary", artifact["summary"]])
                    await run_db(*add_args)
                except RuntimeError as e:
                    log(f"  Warning: artifact-add failed for {task_id}/{artifact.get('name')}: {e}")

            # Extract sets_vars
            sets_vars = params.get("sets_vars", {})
            for var_name, var_def in sets_vars.items():
                try:
                    artifact_path = workdir / var_def["artifact"]
                    data = json.loads(artifact_path.read_text())
                    value = str(data[var_def["key"]])
                    await run_db(
                        "var-set", "--workdir", str(workdir),
                        "--name", var_name, "--value", value,
                        "--source-task", task_id,
                    )
                    log(f"  [{task_id}] Set var {var_name}={value}")
                except Exception as e:
                    log(f"  Warning: var-set failed for {var_name}: {e}")

            # Mark complete
            await run_db(
                "task-update", "--workdir", str(workdir),
                "--task-id", task_id, "--status", "complete",
            )

        else:
            failed += 1
            error = result.get("error", "Unknown error")
            log(f"  [{task_id}] FAILED: {error}")
            await run_db(
                "task-update", "--workdir", str(workdir),
                "--task-id", task_id, "--status", "failed",
                "--error", error,
            )

    return completed, failed
```

**Step 2: Replace the TODO in `main()` with the wave loop**

Replace `# TODO: wave loop (Task 3)` with:

```python
    wave = 0
    total_completed = 0
    total_failed = 0

    while True:
        # Get ready tasks
        ready = await run_db("task-ready", "--workdir", str(workdir))
        if not ready:
            break

        wave += 1
        task_ids = [t["id"] for t in ready]
        log(f"\n{'='*60}")
        log(f"Wave {wave}: dispatching {len(ready)} tasks: {', '.join(task_ids)}")
        log(f"{'='*60}")

        # Mark all as running
        for t in ready:
            await run_db(
                "task-update", "--workdir", str(workdir),
                "--task-id", t["id"], "--status", "running",
            )

        # Update manifest before launching (Claude tasks read it)
        await write_manifest(workdir)

        # Dispatch all tasks in parallel
        coros = [dispatch_task(t, workdir, ticker) for t in ready]
        results = await asyncio.gather(*coros)

        # Process results (centralized DB writes)
        completed, failed = await process_results(results, workdir, ready)
        total_completed += completed
        total_failed += failed

        log(f"Wave {wave} done: {completed} completed, {failed} failed")

        # Safety: if nothing happened, abort
        if completed == 0 and failed == 0:
            log("ERROR: No progress in this wave — aborting")
            break

    # Finalize
    final_status = "complete" if total_failed == 0 else "complete"
    await run_db("research-update", "--workdir", str(workdir), "--status", final_status)

    # Print final status
    status = await run_db("status", "--workdir", str(workdir))
    log(f"\nPipeline finished: {total_completed} completed, {total_failed} failed")
    print(json.dumps(status, indent=2))
```

**Step 3: Test with a quick dry run**

Run:
```bash
uv run python research.py TEST --dag dags/sra.yaml --date 99990101
```

Expected: Initializes, enters wave loop, attempts wave 1 (profile + technical will fail since TEST isn't a real ticker), marks them failed, continues waves until no more ready tasks. Exits with status output.

**Step 4: Clean up and commit**

```bash
rm -rf work/TEST_99990101
git add research.py
git commit -m "Add wave loop and post-wave DB updates to research.py"
```

---

### Task 6: End-to-End Test with Real Ticker

**Step 1: Run with a real ticker (small test)**

Pick a well-known ticker to test the full flow:

```bash
uv run python research.py AAPL --dag dags/sra.yaml
```

Watch the output. Verify:
- Wave 1 dispatches `profile` and `technical` (no deps)
- Wave 2 dispatches `fundamental`, `perplexity`, `fetch_edgar`, `wikipedia`, `perplexity_analysis`
- Wave 3 dispatches `write_body` (claude task)
- Subsequent waves handle conclusion, intro, assembly, critique, polish, final assembly
- `manifest.json` is written before each wave
- Artifacts are registered in DB
- Final status JSON printed to stdout

**Step 2: Verify outputs**

```bash
ls work/AAPL_*/artifacts/
uv run python ./skills/db.py status --workdir work/AAPL_*
cat work/AAPL_*/artifacts/manifest.json
```

**Step 3: Fix any issues found during the test**

Address failures, adjust timeouts, fix prompt construction, etc.

**Step 4: Commit final working version**

```bash
git add research.py
git commit -m "research.py: working end-to-end DAG orchestrator"
```
