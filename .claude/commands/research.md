---
description: "DEPRECATED: Use ./research.py instead. Run the full equity research pipeline for a ticker"
---

# Research Pipeline (DEPRECATED — use `./research.py SYMBOL` instead)

**Arguments:** $ARGUMENTS (expects: SYMBOL DATE, e.g. AAPL 20260225)

Parse SYMBOL and DATE from the arguments. If DATE is missing, use today's date in YYYYMMDD format.

---

## Step 1: Setup

Set the working variables:
- `WORKDIR` = `work/{SYMBOL}_{DATE}`
- `DAG` = `dags/sra.yaml`

## Step 2: Validate the DAG

```bash
uv run python ./skills/db.py validate --dag dags/sra.yaml --ticker SYMBOL
```

If validation fails, stop and report the error.

## Step 3: Initialize the database

```bash
uv run python ./skills/db.py init --workdir WORKDIR --dag dags/sra.yaml --ticker SYMBOL --date DATE
```

Parse the JSON output. Confirm the number of tasks created and the workdir path.

## Step 4: Mark research running

```bash
uv run python ./skills/db.py research-update --workdir WORKDIR --status running
```

## Step 5: Show the DAG and confirm

```bash
uv run python ./skills/db.py status --workdir WORKDIR
```

Display the task list to the user in a readable table:
- Task ID, type, dependencies, status

Ask the user: **"Ready to run the pipeline? (y/n)"**

If the user says no or wants changes, wait for instructions before proceeding.

## Step 6: Execute the DAG loop

Repeat until no tasks are ready and none are running:

### 6a: Query ready tasks

```bash
uv run python ./skills/db.py task-ready --workdir WORKDIR
```

Parse the JSON array. If empty, check status — if all tasks are complete or failed, the pipeline is done.

### 6b: Dispatch ready tasks

For each ready task, dispatch it via the `/taskrunner` skill:

```
/taskrunner TASK_ID --workdir WORKDIR
```

**Parallelism rules:**
- `python` tasks that are all ready at the same time: dispatch ALL in parallel using the Task tool with `subagent_type="general-purpose"` and `run_in_background=true`
- `claude` tasks that are all ready at the same time: dispatch ALL in parallel the same way
- Wait for all dispatched tasks to complete before querying `task-ready` again

### 6c: Check for failures

After each batch completes, check if any tasks failed:

```bash
uv run python ./skills/db.py status --workdir WORKDIR
```

If a task failed:
- Report the failure to the user (task ID, error message)
- Ask: **"Task {id} failed: {error}. Skip it and continue, retry, or stop?"**
  - **skip**: `uv run python ./skills/db.py task-update --workdir WORKDIR --task-id TASK_ID --status skipped`
  - **retry**: `uv run python ./skills/db.py task-update --workdir WORKDIR --task-id TASK_ID --status pending` then re-dispatch
  - **stop**: mark research failed and exit

### 6d: Progress update

After each batch, print a brief status line:
```
[batch N] completed: X/Y tasks | pending: P | failed: F
```

## Step 7: Finalize

When no tasks remain pending or running:

```bash
uv run python ./skills/db.py research-update --workdir WORKDIR --status complete
uv run python ./skills/db.py status --workdir WORKDIR
```

Display the final status with all task outcomes and artifact counts.

Report the location of the final output:
```
✓ Research complete: WORKDIR/artifacts/final_report.md
```
