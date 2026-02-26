# Stock Research Agent 2.0

An AI-orchestrated equity research pipeline that generates comprehensive analyst-style reports. Claude Code drives a DAG of data-gathering scripts and writing agents, producing a polished report from a single command.

## How It Works

```
/research AMD 20260225
```

This triggers a 14-task pipeline:

```
profile ─────┬── technical
             ├── fundamental
             ├── perplexity           ──┐
             ├── fetch_edgar              ├── write_body ── write_conclusion ── write_intro
             ├── wikipedia             ──┘           │
             └── perplexity_analysis                 │
                                                     ▼
                                              assemble_text
                                                     │
                                            critique_body_final
                                                     │
                                            polish_body_final
                                                     │
                                              final_assembly
                                                     │
                                                     ▼
                                         artifacts/final_report.md
```

**Phase 1 — Data gathering** (parallel): Profile, technicals, fundamentals, Perplexity research, SEC filings, Wikipedia, competitive analysis.

**Phase 2 — Writing** (sequential): A Claude subagent synthesizes all gathered data into a 7-section report body, then conclusion and intro are written.

**Phase 3 — Assembly & polish**: Sections are concatenated via Jinja2, critiqued by an editor agent, revised, then assembled into the final formatted report with charts and tables.

## Architecture

Two Claude Code skills orchestrate everything:

| Skill | Role |
|-------|------|
| `/research` | DAG runner — initializes the database, loops `task-ready → dispatch → wait`, handles failures |
| `/taskrunner` | Task dispatcher — runs a single task (`python` script or `claude` subagent), registers artifacts |

**State management**: One SQLite database per run (`work/{SYMBOL}_{DATE}/research.db`) tracks task status, dependencies, artifacts, and runtime variables. All components access state through `skills/db.py` — no direct SQL elsewhere.

**DAG definition**: `dags/sra.yaml` declares tasks, types, dependencies, configs, and expected outputs in a version-2 schema validated by Pydantic.

## Data Sources

| Source | What it provides |
|--------|-----------------|
| **yfinance** | Price history, fundamentals, analyst recommendations |
| **TA-Lib** | Technical indicators (SMA, RSI, MACD, ATR, Bollinger Bands) |
| **OpenBB / FMP** | Financial statements, key ratios, peer comparisons |
| **Finnhub** | Peer company detection |
| **Perplexity AI** | News, business profiles, executive bios, competitive/risk analysis |
| **SEC EDGAR** | 10-K, 10-Q, 8-K filings via edgartools |
| **Wikipedia** | Company history and background |
| **Claude subagents** | Report writing, critique, and revision |

## Output

Each run produces `work/{SYMBOL}_{DATE}/artifacts/` containing 40+ files:

- `final_report.md` — the complete formatted report
- `chart.png` — stock price chart with technical overlays
- `profile.json`, `technical_analysis.json` — structured data
- `income_statement.csv`, `balance_sheet.csv`, `cash_flow.csv`, `key_ratios.csv` — financials
- `draft_report_body.md`, `draft_report_conclusion.md`, `draft_intro.md` — draft sections
- `report_body.md`, `report_critique.md`, `report_body_final.md` — critique/revise cycle
- Perplexity research, SEC filing extracts, Wikipedia summaries

## Setup

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- System libraries: `pandoc`, `ta-lib`

### Install

```bash
# Install system dependencies (macOS)
brew install pandoc ta-lib
export TA_INCLUDE_PATH="$(brew --prefix ta-lib)/include"
export TA_LIBRARY_PATH="$(brew --prefix ta-lib)/lib"

# Install Python dependencies
uv sync
```

### Environment

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=...
PERPLEXITY_API_KEY=...
SEC_FIRM=...
SEC_USER=...
OPENBB_PAT=...
FINNHUB_API_KEY=...
```

## Usage

### Full pipeline

```
/research SYMBOL [DATE]
```

The `/research` command initializes the database, presents the task DAG for confirmation, then executes all tasks in dependency order with parallel dispatch.

### Individual data scripts

Each data-gathering script runs standalone:

```bash
uv run ./skills/fetch_profile/fetch_profile.py AMD --workdir work/AMD_20260225
uv run ./skills/fetch_technical/fetch_technical.py AMD --workdir work/AMD_20260225
uv run ./skills/fetch_fundamental/fetch_fundamental.py AMD --workdir work/AMD_20260225
uv run ./skills/fetch_perplexity/fetch_perplexity.py AMD --workdir work/AMD_20260225
uv run ./skills/fetch_edgar/fetch_edgar.py AMD --workdir work/AMD_20260225
uv run ./skills/fetch_wikipedia/fetch_wikipedia.py AMD --workdir work/AMD_20260225
uv run ./skills/fetch_perplexity_analysis/fetch_perplexity_analysis.py AMD --workdir work/AMD_20260225
```

### Database CLI

```bash
uv run ./skills/db.py init --workdir work/AMD_20260225 --dag dags/sra.yaml --ticker AMD
uv run ./skills/db.py task-ready --workdir work/AMD_20260225
uv run ./skills/db.py status --workdir work/AMD_20260225
```

### Template rendering

```bash
# Generic template renderer
./skills/render_template.py \
  --template templates/assemble_report.md.j2 \
  --output work/AMD_20260225/artifacts/report_body.md \
  --json work/AMD_20260225/artifacts/profile.json \
  --file intro=work/AMD_20260225/artifacts/draft_intro.md \
  --file body=work/AMD_20260225/artifacts/draft_report_body.md

# Final report assembly (loads all artifacts automatically)
./skills/render_final.py --workdir work/AMD_20260225
```

## Project Structure

```
├── dags/
│   └── sra.yaml                    # DAG definition (14 tasks, v2 schema)
├── skills/
│   ├── db.py                       # SQLite state management CLI
│   ├── schema.py                   # Pydantic DAG validation models
│   ├── config.py                   # Centralized constants
│   ├── utils.py                    # Shared utilities
│   ├── render_template.py          # Generic Jinja2 renderer
│   ├── render_final.py             # Final report assembly
│   ├── fetch_profile/              # Company profile + peers
│   ├── fetch_technical/            # Chart + technical indicators
│   ├── fetch_fundamental/          # Financials, ratios, analyst data
│   ├── fetch_perplexity/           # News, profiles, executives
│   ├── fetch_perplexity_analysis/  # Business model, competitive, risk
│   ├── fetch_edgar/                # SEC filings
│   └── fetch_wikipedia/            # Wikipedia summary
├── templates/
│   ├── assemble_report.md.j2       # Section concatenation
│   └── final_report.md.j2          # Final formatted report
├── .claude/commands/
│   ├── research.md                 # /research pipeline runner
│   ├── taskrunner.md               # /taskrunner task dispatcher
│   └── db.md                       # /db database CLI
├── tests/
│   ├── test_db.py
│   └── test_schema.py
└── work/                           # Output (one dir per run)
    └── {SYMBOL}_{DATE}/
        ├── research.db
        └── artifacts/
```

## Script Conventions

All Python scripts follow a consistent pattern:

- `#!/usr/bin/env python3` shebang
- Import constants from `config.py`, utilities from `utils.py`
- `pathlib.Path` for all path operations
- `logger = setup_logging(__name__)` for output (stderr only)
- JSON manifest to stdout: `{"status": "complete", "artifacts": [...], "error": null}`
- Exit codes: 0 = success, 1 = partial, 2 = failure
- Type hints on all functions, specific exception handling
