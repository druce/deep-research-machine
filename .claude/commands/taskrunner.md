---
description: Execute a single DAG task — dispatches python or claude task types through the full lifecycle
---

# Task Runner

**Arguments:** $ARGUMENTS (expects: TASK_ID --workdir WORKDIR)

Parse TASK_ID and WORKDIR from the arguments. Then execute the task lifecycle below.

---

## Step 1: Get task config

```bash
uv run python ./skills/db.py task-get --workdir WORKDIR --task-id TASK_ID
```

Parse the JSON output. Extract `type` (JSON field `skill`), `params`, and `status`. If status is not `pending`, stop and report.

## Step 2: Mark running

```bash
uv run python ./skills/db.py task-update --workdir WORKDIR --task-id TASK_ID --status running
```

## Step 3: Get runtime variables

```bash
uv run python ./skills/db.py var-get --workdir WORKDIR
```

If there are variables, substitute any `${var_name}` placeholders in the task params before dispatching.

## Step 4: Dispatch by task type

### If type is `python`

**Build the command** from `params.script` and `params.args`:
- `ticker` arg is positional (first argument)
- All other args become `--key value` flags (underscores → hyphens: `peers_file` → `--peers-file`)

```bash
uv run python {script} {ticker} --workdir WORKDIR [--key value ...] 2>WORKDIR/{task_id}_stderr.log
```

**Parse stdout** as a JSON manifest:
```json
{"status": "complete|partial|failed", "artifacts": [...], "error": null}
```

**Map exit code + manifest status to task status:**
- Exit 0 + "complete" or "partial" → task status `complete`
- Exit 2+ or "failed" → task status `failed`

### If type is `claude`

**Get dependency context** to include in the prompt:
```bash
uv run python ./skills/db.py task-context --workdir WORKDIR --task-id TASK_ID
```

**Build the subagent prompt** with three parts:

**Part 1 — System context** (from `params.system`):
```
{params.system}
```

**Part 2 — Artifact context** (from task-context results):
```
Available research data in WORKDIR/artifacts/:

From task "{from_task}" — {name} ({format}): {description}
  Summary: {summary}
  File: WORKDIR/{path}

[... for each artifact from task-context ...]
```

**Part 3 — The original prompt** (from `params.prompt`):
```
---

{original prompt from params}
```

**Part 4 — Save instructions.** For each output in `params.outputs`, if the prompt does not already mention the output path, append:
```
Save your output for "{output_name}" to WORKDIR/{output_path}
```

**Tool restrictions** (advisory, included in prompt):
- `"all"` → no restriction text needed
- `["read", "write"]` → prepend: "For this task, only use Read and Write tools."
- `[]` (empty) → prepend: "Do not use any tools for this task. Respond with text only."

**Dispatch via Task subagent:**
```
Task(
  description="{task_id} for {ticker}",
  subagent_type="general-purpose",
  prompt=<constructed prompt above>
)
```

The subagent has access to all tools including Read, Write, Grep, Glob, Bash, and MCP servers (perplexity, yfinance, wikipedia, etc.).

**After completion**, verify the output files exist at the paths defined in `params.outputs`.

### If type is `shell`

```bash
cd WORKDIR && {params.command} 2>WORKDIR/{task_id}_stderr.log
```

## Step 5: Register artifacts

For each output in `params.outputs`:

```bash
uv run python ./skills/db.py artifact-add --workdir WORKDIR \
  --task-id TASK_ID --name NAME --path PATH --format FORMAT \
  [--source SOURCE] [--summary "brief description of what was produced"]
```

The `--description` auto-fills from the YAML definition. Add `--summary` with a brief runtime description of what was actually produced (file size, key findings, etc.).

For `python` tasks, the manifest provides source and summary for each artifact. Use those.

For `claude` tasks, inspect the output file briefly and write a short summary.

## Step 6: Extract sets_vars

If `params.sets_vars` exists, for each variable:

1. Read the artifact file at `WORKDIR/{sets_vars[var_name].artifact}`
2. Parse as JSON and extract the value at `sets_vars[var_name].key`
3. Register:

```bash
uv run python ./skills/db.py var-set --workdir WORKDIR \
  --name VAR_NAME --value "EXTRACTED_VALUE" --source-task TASK_ID
```

Skip this step if the task failed (no variables produced).

## Step 7: Mark terminal status

```bash
uv run python ./skills/db.py task-update --workdir WORKDIR \
  --task-id TASK_ID --status complete \
  --summary "brief summary of results"
```

Or if failed:

```bash
uv run python ./skills/db.py task-update --workdir WORKDIR \
  --task-id TASK_ID --status failed \
  --error "what went wrong"
```

## Step 8: Report

Print a summary:
- Task ID, type, final status
- Number of artifacts registered
- Key findings or error message
- Runtime (if notable)
