# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Stock Research Agent — an async Python-orchestrated equity research pipeline. `research.py` reads a DAG defined in YAML, initializes a SQLite database, and runs waves of tasks as async subprocesses. Python data-gathering scripts run via `uv run python`, Claude writing tasks run via `claude --dangerously-skip-permissions -p`.

## Architecture

**Single orchestrator:** `research.py` (asyncio) handles the full lifecycle:
1. Validates DAG YAML and initializes SQLite via `db.py`
2. Loops: query `db.py task-ready` → dispatch all ready tasks in parallel → collect results → update DB → repeat
3. Python tasks: spawns `uv run python {script}`, parses JSON manifest from stdout
4. Claude tasks: spawns `claude -p` with prompt (system + artifact context + task prompt), checks output files
5. All DB writes centralized in orchestrator (tasks never touch the database)

**Artifact context:** `manifest.json` is written before each wave, listing all artifacts produced so far. Claude tasks read this file to discover available research data.

**Data layer:** SQLite + files hybrid. One database per run at `work/{SYMBOL}_{DATE}/research.db`. All components access shared state through `db.py` CLI only — no direct SQLite access elsewhere.

**DAG execution order** (driven by dependencies, not hardcoded stages):
1. `profile` (no deps)
2. `technical`, `fundamental`, `perplexity`, `fetch_edgar`, `wikipedia`, `perplexity_analysis` (depend on profile)
3. `write_body` (depends on all data-gathering tasks)
4. `write_conclusion` (depends on write_body), then `write_intro` (depends on both)
5. `assemble_text` (depends on all writers)
6. `critique_body_final` → `polish_body_final` → `final_assembly`

## Key Files

| File | Purpose |
|------|---------|
| `research.py` | Async DAG orchestrator — entry point for full pipeline |
| `skills/db.py` | Core SQLite CLI — init, validate, task-ready, task-get, task-update, artifact-add, artifact-list, status, research-update |
| `skills/schema.py` | Pydantic models for DAG YAML v2 schema validation |
| `skills/config.py` | Centralized constants (timeouts, API keys, indicator params, model settings) |
| `skills/utils.py` | Logging, formatting, directory helpers |
| `skills/fetch_profile/` | Company profile + peer identification |
| `skills/fetch_technical/` | Stock chart + technical indicators |
| `skills/fetch_fundamental/` | Financial statements, ratios, analyst data |
| `skills/fetch_perplexity/` | Perplexity AI research (news, profiles, executives) |
| `skills/fetch_edgar/` | SEC filings (10-K, 10-Q, 8-K) |
| `skills/fetch_wikipedia/` | Wikipedia company summary |
| `skills/fetch_perplexity_analysis/` | Business model, competitive, risk, thesis analysis via Perplexity |
| `dags/sra.yaml` | Default DAG (v2 schema) defining all tasks with typed configs and dependencies |
| `templates/*.md.j2` | Jinja2 report assembly templates |
| `docs/plans/` | Design docs and implementation plans |

## Commands

### Install dependencies
```bash
uv sync
# Also needs system deps:
# brew install pandoc ta-lib
# export TA_INCLUDE_PATH="$(brew --prefix ta-lib)/include"
# export TA_LIBRARY_PATH="$(brew --prefix ta-lib)/lib"
```

### Add a dependency
```bash
uv add <package>
```

### Run individual Python skills
```bash
# All scripts are executable and follow the same pattern:
./skills/fetch_profile/fetch_profile.py SYMBOL --workdir work/SYMBOL_DATE
./skills/fetch_technical/fetch_technical.py SYMBOL --workdir work/SYMBOL_DATE
./skills/fetch_fundamental/fetch_fundamental.py SYMBOL --workdir work/SYMBOL_DATE
./skills/fetch_perplexity/fetch_perplexity.py SYMBOL --workdir work/SYMBOL_DATE
./skills/fetch_edgar/fetch_edgar.py SYMBOL --workdir work/SYMBOL_DATE
./skills/fetch_wikipedia/fetch_wikipedia.py SYMBOL --workdir work/SYMBOL_DATE
./skills/fetch_analysis/fetch_analysis.py SYMBOL --workdir work/SYMBOL_DATE
```

### Database CLI
```bash
./skills/db.py init --workdir work/SYMBOL_DATE --dag dags/sra.yaml --ticker SYMBOL
./skills/db.py validate --dag dags/sra.yaml --ticker SYMBOL
./skills/db.py task-ready --workdir work/SYMBOL_DATE
./skills/db.py task-get --workdir work/SYMBOL_DATE --task-id TASK_ID
./skills/db.py task-update --workdir work/SYMBOL_DATE --task-id TASK_ID --status complete
./skills/db.py artifact-add --workdir work/SYMBOL_DATE --task-id TASK_ID --name NAME --path PATH --format FORMAT
./skills/db.py artifact-list --workdir work/SYMBOL_DATE
./skills/db.py status --workdir work/SYMBOL_DATE
```

### Full pipeline
```bash
./research.py SYMBOL [--dag dags/sra.yaml] [--date YYYYMMDD]
```

## Python Coding Conventions

- `#!/usr/bin/env python3` shebang (never hardcoded paths)
- Import constants from `config.py`, utilities from `utils.py`
- `pathlib.Path` for all path operations (not `os.path`)
- `logger = setup_logging(__name__)` for output (not `print()`)
- Type hints on all functions
- Specific exception handling (no bare `except:`)
- Return `(success: bool, data, error_msg)` tuples from data functions
- Return exit codes from `main()` (0 = success, nonzero = error)
- JSON manifest to stdout: `{"status": "complete", "artifacts": [...], "error": null}`

## Environment

Requires a `.env` file with API keys: `ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`, `SEC_FIRM`, `SEC_USER`, `FINNHUB_API_KEY`, and others.
