---
description: SQLite CLI for DAG pipeline state management — init, validate, task-ready, task-get, task-update, task-context, artifact-add, artifact-list, status, research-update
---

# db.py — Pipeline Database CLI

**Arguments:** $ARGUMENTS (subcommand + args)

```bash
uv run python ./skills/db.py $ARGUMENTS
```

Execute the command above. Report the JSON output, any errors, and what changed.

---

## Commands

### `init` — Create database from DAG YAML
```
init --workdir WORKDIR --dag DAG_YAML --ticker SYMBOL [--date YYYYMMDD]
```
Creates `research.db` in WORKDIR, parses the DAG YAML, populates tasks and dependencies.
Returns `{"status": "ok", "tasks": N, "workdir": "..."}`.

### `validate` — Validate a DAG YAML without touching the database
```
validate [--dag dags/sra.yaml] [--ticker SYMBOL] [--date YYYYMMDD]
```
Parses and validates the YAML schema without creating anything.
Returns `{"status": "ok", "version": 2, "tasks": N, "task_types": [...]}`.

### `task-ready` — List tasks ready to run
```
task-ready --workdir WORKDIR
```
Returns a JSON array of tasks in `pending` status whose dependencies are all `complete` or `skipped`.
Each entry has `id`, `skill`, `description`, `params`.

### `task-get` — Get full task details
```
task-get --workdir WORKDIR --task-id TASK_ID
```
Returns all task fields: `id`, `skill`, `description`, `params`, `status`, `depends_on`, `artifact_count`, `summary`, `error`.

### `task-update` — Update task state
```
task-update --workdir WORKDIR --task-id TASK_ID [--status STATUS] [--summary TEXT] [--error TEXT]
```
`--status` choices: `pending`, `running`, `complete`, `failed`, `skipped`.
Auto-sets `started_at` on `running`, `completed_at` on `complete`/`failed`/`skipped`.
Returns `{"status": "ok", "task": "...", "new_status": "..."}`.

### `artifact-add` — Register an artifact
```
artifact-add --workdir WORKDIR --task-id TASK_ID --name NAME --path PATH --format FORMAT [--source SOURCE] [--summary TEXT]
```
`--path` is relative to WORKDIR. `--format`: `json`, `csv`, `md`, `png`, `txt`.
Upserts: if the same `(task_id, name)` already exists, updates it.
Returns `{"status": "ok", "artifact_id": N, "task": "...", "name": "..."}`.

### `artifact-list` — List registered artifacts
```
artifact-list --workdir WORKDIR [--task TASK_ID]
```
Returns a JSON array of all artifacts, optionally filtered by task.
Each entry has `id`, `task_id`, `name`, `path`, `format`, `source`, `summary`, `size_bytes`.

### `status` — Pipeline overview
```
status --workdir WORKDIR
```
Returns research metadata, task counts by status, per-task details, and total artifact count.

### `research-update` — Update research run status
```
research-update --workdir WORKDIR --status STATUS
```
`--status` choices: `not started`, `running`, `complete`, `failed`.
Returns `{"status": "ok", "new_status": "..."}`.

### `task-context` — Resolve reads_from to artifact paths
```
task-context --workdir WORKDIR --task-id TASK_ID
```
Reads the task's `reads_from` list and returns all registered artifacts from those source tasks.
Returns `{"task_id": "...", "artifacts": [{from_task, name, path, format, summary}, ...]}`.

---

## Example workflow
```bash
# Initialize
uv run python ./skills/db.py init --workdir work/AAPL_20260225 --dag dags/sra.yaml --ticker AAPL

# Check what's ready
uv run python ./skills/db.py task-ready --workdir work/AAPL_20260225

# Mark a task running, then complete
uv run python ./skills/db.py task-update --workdir work/AAPL_20260225 --task-id profile --status running
uv run python ./skills/db.py task-update --workdir work/AAPL_20260225 --task-id profile --status complete --summary "Fetched AAPL profile"

# Register its output artifact
uv run python ./skills/db.py artifact-add --workdir work/AAPL_20260225 --task-id profile --name profile --path artifacts/profile.json --format json

# Check overall status
uv run python ./skills/db.py status --workdir work/AAPL_20260225
```
