# Design: research.py — Python DAG Orchestrator

## Overview

Single-file async Python script that replaces `/research` + `/taskrunner` Claude Code skills. Reads the DAG YAML, initializes SQLite via `db.py`, then runs waves of tasks as subprocesses — Python tasks via `uv run python`, Claude tasks via `claude -p`. All DB writes are centralized in the orchestrator after each wave completes.

## CLI Interface

```
./research.py TICKER [--dag dags/sra.yaml] [--date YYYYMMDD]
```

Creates `work/{TICKER}_{DATE}/`, runs the full pipeline. Progress to stderr, final status to stdout.

## Core Loop (asyncio)

```
1. Validate DAG + init DB (via db.py subprocess)
2. Mark research running (via db.py)
3. Loop:
   a. Query task-ready (via db.py) → list of dispatchable tasks
   b. If empty → done
   c. Update manifest.json (all artifacts so far, verify files exist)
   d. Mark all ready tasks as "running" in DB
   e. Launch all as async subprocesses (asyncio.create_subprocess_exec)
   f. await asyncio.gather — collect results
   g. For each completed task:
      - Python: parse stdout JSON manifest
      - Claude: check output files exist at expected paths
      - Register artifacts via db.py artifact-add
      - Extract sets_vars if defined (read JSON artifact, extract key)
      - var-set via db.py
      - task-update via db.py (complete/failed)
   h. Print wave summary to stderr
4. Mark research complete (via db.py)
5. Print final status
```

## Python Task Dispatch

```bash
uv run python {script} {ticker} --workdir {workdir} [--key value ...] \
    2>{workdir}/{task_id}_stderr.log
```

- `ticker` is positional first arg
- Other args become `--key value` flags (underscores → hyphens)
- Stdout parsed as JSON manifest: `{"status": "complete|partial|failed", "artifacts": [...], "error": ...}`
- Exit 0 + status complete/partial → task complete
- Exit 2+ or status failed → task failed

## Claude Task Dispatch

```bash
claude --dangerously-skip-permissions --verbose \
    [--disallowed-tools tool1 tool2 ...] \
    [--model model_name] \
    -p << 'EOF'
{system prompt from config.system}

Working directory: {absolute_workdir}
All research data is in the artifacts/ subdirectory.
Read artifacts/manifest.json for a description of all available files.

---

{task prompt from config.prompt}

Save your output to {absolute_workdir}/{output_path}
EOF
```

- Prompt piped via stdin, stdout/stderr captured (stderr to `{task_id}_stderr.log`)
- Prompt also saved to `{task_id}_prompt.txt` for debugging
- `CLAUDECODE` env var cleared to allow invocation from within Claude Code sessions
- Success determined by: output files exist at expected paths
- If output files missing → task failed

## manifest.json

Written by orchestrator before each wave. Contains all artifacts produced by completed tasks so far:

```json
[
  {
    "description": "Technical indicators: SMA, EMA, RSI, MACD, Bollinger Bands, ATR, OBV",
    "format": "json",
    "summary": "RSI 62, MACD bullish crossover, above 200 SMA",
    "file": "artifacts/technical_analysis.json"
  },
  {
    "description": "1-year stock price chart with SMA-50, SMA-200, volume bars",
    "format": "png",
    "summary": null,
    "file": "artifacts/chart.png"
  }
]
```

Only includes entries where the file actually exists on disk.

## DB Interaction — Centralized in Orchestrator

Tasks never touch the database. Only research.py calls db.py:

| When | Command |
|------|---------|
| Startup | `db.py init` — create DB, parse DAG, populate tasks |
| Startup | `db.py research-update --status running` |
| Before wave | `db.py task-ready` — get dispatchable tasks |
| Before wave | `db.py task-update --status running` (each task) |
| After wave | `db.py artifact-add` (each artifact produced) |
| After wave | `db.py var-set` (each sets_vars extraction) |
| After wave | `db.py task-update --status complete/failed` (each task) |
| End | `db.py research-update --status complete` |

## Error Handling

- **Task failure**: Log error to stderr, mark as `failed` in DB, continue pipeline
- **Downstream of failed task**: `task-ready` SQL treats `failed` as resolved, so downstream tasks still become ready (they degrade gracefully with missing data)
- **No progress detection**: If a wave produces zero completions and zero failures, abort (something is broken)
- **Subprocess timeout**: Use asyncio timeout per task type (from config.py PHASE_TIMEOUTS)

## YAML Schema Change

Replace `tools: all | ["read", "write"]` with `disallowed_tools: ["yfinance", "alphavantage"]` in claude task configs:

- Default (empty list or omitted): full tool access
- Explicit list: those MCP tools are blocked via `--disallowed-tools` flag

The `ClaudeConfig` in `schema.py` already has the `disallowed_tools` field. We update the DAG YAML to use it instead of `tools`.

## What Stays the Same

- `skills/db.py` — unchanged
- `skills/schema.py` — unchanged (already has disallowed_tools)
- All `skills/fetch_*.py` scripts — unchanged
- `skills/render_template.py`, `skills/render_final.py` — unchanged
- `templates/*.md.j2` — unchanged
- `skills/config.py`, `skills/utils.py` — unchanged

## What Gets Replaced

- `.claude/commands/research.md` → `research.py` (the orchestrator loop)
- `.claude/commands/taskrunner.md` → dispatch logic inside `research.py`

## What Gets Modified

- `dags/sra.yaml` — replace `tools:` with `disallowed_tools:` in claude task configs
