# Fundamental Analysis Skill Spec — `fetch_fundamental.py`

## Overview

Migrate `fetch_fundamental.py` from the source project. Remove `save_company_overview()` (moved to `fetch_profile.py`). Add JSON manifest output. Add explicit `--peers-file` flag instead of hardcoded path discovery.

## Goals

1. Fetch financial statements (income statement, balance sheet, cash flow) from yfinance as CSV
2. Generate income statement Sankey chart (HTML + PNG)
3. Compute key financial ratios for the ticker and its peers, saved as CSV
4. Fetch analyst recommendations as JSON
5. Fetch recent news articles as JSON
6. Output JSON manifest to stdout

## Non-Goals

- Company overview/profile (moved to `fetch_profile.py`)
- Peer detection (that's `fetch_profile.py` — this script receives peers via `--peers-file`)

## Dependencies

### Python packages
```
yfinance
pandas
plotly
jinja2
python-dotenv
```

### Environment Variables

None required for core functionality. OpenBB PAT only needed if using OpenBB data sources (currently not used in fundamental).

> Scripts call `load_environment()` from `utils.py` at startup to load the project root `.env` file. Scripts that need env vars MUST call this before accessing them. The `.env` file is not committed to version control.

## Source

**Migrate from:** `../stock_research_agent/skills/fetch_fundamental.py`

**Functions to keep:**
- `save_financial_statements()` — income statement, balance sheet, cash flow as CSV
- `save_income_statement_sankey()` — Sankey visualization
- `get_financial_ratios()` — compute ratios for a single symbol
- `save_key_ratios()` — ratios for ticker + peers, saved as CSV
- `save_analyst_recommendations()` — analyst ratings as JSON
- `save_news()` — recent news as JSON

**Functions to remove:**
- `save_company_overview()` — moved to `fetch_profile.py`

## Changes from Source

1. **Remove `save_company_overview()`** — profile task handles this
2. **Add `--peers-file` flag** — explicit path to peers_list.json (default: `{workdir}/artifacts/peers_list.json`)
3. **Normalize CLI:** `SYMBOL --workdir PATH` (not `--work-dir`)
4. **Add JSON manifest to stdout**
5. **Standardize exit codes:** 0 (all 5 tasks succeed), 1 (partial), 2 (nothing produced)
6. **All progress output to stderr**
7. **Read company name from `profile.json`** instead of fetching from yfinance (for Sankey chart title, etc.)

## Output Structure

```
work/SYMBOL_YYYYMMDD/artifacts/
├── income_statement.csv
├── income_statement_sankey.html
├── income_statement_sankey.png
├── balance_sheet.csv
├── cash_flow.csv
├── key_ratios.csv
├── analyst_recommendations.json
└── news.json
```

## CLI Interface

```
./skills/fetch_fundamental/fetch_fundamental.py SYMBOL --workdir DIR [--peers-file PATH]
```

| Argument | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SYMBOL` | Yes | — | Stock ticker symbol |
| `--workdir` | Yes | — | Work directory path |
| `--peers-file` | No | `{workdir}/artifacts/peers_list.json` | Path to peers list JSON |

## Manifest Output

```json
{
  "status": "complete",
  "artifacts": [
    {"name": "income_statement", "path": "artifacts/income_statement.csv", "format": "csv", "source": "yfinance", "summary": "4 years of annual income data"},
    {"name": "income_statement_sankey", "path": "artifacts/income_statement_sankey.png", "format": "png", "source": "yfinance+plotly", "summary": "Revenue flow to net income"},
    {"name": "balance_sheet", "path": "artifacts/balance_sheet.csv", "format": "csv", "source": "yfinance", "summary": "4 years of annual balance sheet data"},
    {"name": "cash_flow", "path": "artifacts/cash_flow.csv", "format": "csv", "source": "yfinance", "summary": "4 years of annual cash flow data"},
    {"name": "key_ratios", "path": "artifacts/key_ratios.csv", "format": "csv", "source": "yfinance", "summary": "28 ratios for TSLA + 5 peers"},
    {"name": "analyst_recommendations", "path": "artifacts/analyst_recommendations.json", "format": "json", "source": "yfinance", "summary": "20 recent analyst actions"},
    {"name": "news", "path": "artifacts/news.json", "format": "json", "source": "yfinance", "summary": "10 recent news articles"}
  ],
  "error": null
}
```

## DAG Entry

```yaml
fundamental:
  skill: script
  params:
    script: skills/fetch_fundamental/fetch_fundamental.py
    args: {ticker: "${ticker}", workdir: "${workdir}", peers_file: "artifacts/peers_list.json"}
  depends_on: [profile]
  outputs:
    income_statement:        {path: "artifacts/income_statement.csv", format: csv}
    balance_sheet:           {path: "artifacts/balance_sheet.csv", format: csv}
    cash_flow:               {path: "artifacts/cash_flow.csv", format: csv}
    key_ratios:              {path: "artifacts/key_ratios.csv", format: csv}
    analyst_recommendations: {path: "artifacts/analyst_recommendations.json", format: json}
```

Depends on `profile` (needs peers_list.json for ratio comparison). Previously depended on `technical` which included peers — now depends on `profile` instead.
