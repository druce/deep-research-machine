# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Stock Research Agent 2.0 — a Claude Code-orchestrated equity research pipeline. Claude Code is the orchestrator (no Python orchestration layer). A `/research` skill handles interactive setup, initializes a SQLite database, and runs a DAG defined in YAML. A `/taskrunner` skill dispatches individual tasks.

## Architecture

**Two-layer orchestration:**

1. **`/research` skill** (DAG runner): Takes a ticker, creates `work/{SYMBOL}_{DATE}/`, initializes `research.db` from `dags/sra.yaml`, presents DAG to user for confirmation/editing, then loops: query `db.py task-ready` → dispatch all ready tasks in parallel via `/taskrunner` → wait → repeat until done.

2. **`/taskrunner` skill** (task dispatcher): Reads task config from `research.db`, dispatches based on task type:
   - `python` → runs Python script with argparse-style args
   - `claude` → invokes Claude Code CLI with prompt, tools, and artifact context
   - `shell` → runs shell command
   - `perplexity` → calls Perplexity API with prompt
   - `openai` → calls OpenAI API with prompt

**Data layer:** SQLite + files hybrid. One database per run at `work/{SYMBOL}_{DATE}/research.db`. All components access shared state through `db.py` CLI only — no direct SQLite access elsewhere.

**DAG execution order** (driven by dependencies, not hardcoded stages):
1. `profile`, `technical` (no deps)
2. `fundamental`, `perplexity`, `sec_edgar`, `wikipedia`, `analysis` (depend on profile)
3. Body writer tasks (~10, depend on data-gathering tasks)
4. `write_executive_summary`, `write_conclusion` (depend on body writers)
5. `assembly` (depends on all writers)
6. `polish` (depends on assembly)

## Key Files

| File | Purpose |
|------|---------|
| `skills/db.py` | Core SQLite CLI — init, validate, task-ready, task-get, task-update, artifact-add, artifact-list, status, research-update |
| `skills/schema.py` | Pydantic models for DAG YAML v2 schema validation |
| `skills/config.py` | Centralized constants (timeouts, API keys, indicator params, model settings) |
| `skills/utils.py` | Logging, formatting, directory helpers |
| `skills/research_profile.py` | Company profile + peer identification |
| `skills/research_technical.py` | Stock chart + technical indicators |
| `skills/research_fundamental.py` | Financial statements, ratios, analyst data |
| `skills/research_perplexity.py` | Perplexity AI research (news, profiles, executives) |
| `skills/research_sec_edgar.py` | SEC filings (10-K, 10-Q, 8-K) |
| `skills/research_wikipedia.py` | Wikipedia company summary |
| `skills/research_analysis.py` | Business model, competitive, risk, thesis analysis via Perplexity |
| `dags/sra.yaml` | Default DAG (v2 schema) defining all tasks with typed configs and dependencies |
| `templates/*.md.j2` | Jinja2 report assembly templates |
| `DESIGN.md` | Full architecture and design decisions |
| `IMPLEMENTATION.md` | Step-by-step build plan (5 phases) |
| `SPEC_*.md` | Detailed specifications per component (DB, research, taskrunner, each skill) |

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
./skills/research_profile.py SYMBOL --workdir work/SYMBOL_DATE
./skills/research_technical.py SYMBOL --workdir work/SYMBOL_DATE
./skills/research_fundamental.py SYMBOL --workdir work/SYMBOL_DATE
./skills/research_perplexity.py SYMBOL --workdir work/SYMBOL_DATE
./skills/research_sec_edgar.py SYMBOL --workdir work/SYMBOL_DATE
./skills/research_wikipedia.py SYMBOL --workdir work/SYMBOL_DATE
./skills/research_analysis.py SYMBOL --workdir work/SYMBOL_DATE
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
```
/research SYMBOL
```

## Python Coding Conventions

When creating or modifying Python skills, always read and follow `SKILLS_BEST_PRACTICES_CHEATSHEET.md` — it is the authoritative reference for file headers, argument parsing, function signatures, exception handling, path operations, logging, and formatting patterns. Key points:

- `#!/usr/bin/env python3` shebang (never hardcoded paths)
- Import constants from `config.py`, utilities from `utils.py`
- `pathlib.Path` for all path operations (not `os.path`)
- `logger = setup_logging(__name__)` for output (not `print()`)
- Type hints on all functions
- Specific exception handling (no bare `except:`)
- Return `(success: bool, data, error_msg)` tuples from data functions
- Return exit codes from `main()` (0 = success, 1 = error)

## Environment

Requires a `.env` file with API keys: `ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`, `OPENAI_API_KEY`, `SEC_FIRM`, `SEC_USER`, and others. 
