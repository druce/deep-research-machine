# Technical Analysis Skill Spec — `fetch_technical.py`

## Overview

Migrate `fetch_technical.py` from the source project with two key changes: (1) remove all peer-related functions (moved to `fetch_profile.py`), and (2) add JSON manifest output to stdout.

After migration, this script does exactly two things: generate a stock chart and compute technical indicators.

## Goals

1. Generate a multi-panel weekly stock chart (candlestick + volume + relative strength vs S&P 500)
2. Compute technical indicators (SMAs, RSI, MACD, ATR, Bollinger Bands) and save as JSON
3. Output JSON manifest to stdout per script contract

## Non-Goals

- Peer detection or filtering (moved to `fetch_profile.py`)
- Company profile data (moved to `fetch_profile.py`)
- Fundamental data (that's `fetch_fundamental.py`)

## Dependencies

### Python packages
```
yfinance
pandas
numpy
plotly
ta-lib
```

### Environment Variables

None required. This script uses only public yfinance data.

> Scripts call `load_environment()` from `utils.py` at startup to load the project root `.env` file. Scripts that need env vars MUST call this before accessing them. The `.env` file is not committed to version control.

## Source

**Migrate from:** `../stock_research_agent/skills/fetch_technical.py`

**Functions to keep:**
- `save_chart()` — generate weekly candlestick chart with MAs, volume, relative strength
- `save_technical_analysis()` — compute and save technical indicators as JSON

**Functions to remove:**
- `get_peers_finnhub()` — moved to `fetch_profile.py`
- `get_peers_openbb()` — moved to `fetch_profile.py`
- `get_peers_with_fallback()` — moved to `fetch_profile.py`
- `filter_peers_by_industry()` — moved to `fetch_profile.py`
- `save_peers_list()` — moved to `fetch_profile.py`

**CLI flags to remove:**
- `--peers` — moved to `fetch_profile.py`
- `--no-filter-peers` — moved to `fetch_profile.py`

## Changes from Source

1. **Remove all peer code** — ~400 lines removed
2. **Normalize CLI:** `SYMBOL --workdir PATH` (not `--work-dir`)
3. **Add JSON manifest to stdout**
4. **Standardize exit codes:** 0 (success), 1 (partial), 2 (failure)
5. **All progress output to stderr** (not stdout — manifest goes to stdout)
6. **main() returns exit code based on success count:** both tasks = 0, one task = 1, zero = 2

## Output Structure

```
work/SYMBOL_YYYYMMDD/artifacts/
├── chart.png                    # Weekly candlestick chart
└── technical_analysis.json      # Technical indicators
```

## CLI Interface

```
./skills/fetch_technical/fetch_technical.py SYMBOL --workdir DIR
```

| Argument | Required | Purpose |
|----------|----------|---------|
| `SYMBOL` | Yes | Stock ticker symbol |
| `--workdir` | Yes | Work directory path |

## Manifest Output

```json
{
  "status": "complete",
  "artifacts": [
    {
      "name": "chart",
      "path": "artifacts/chart.png",
      "format": "png",
      "source": "yfinance+plotly",
      "summary": "4yr weekly candlestick, MA13/MA52, relative strength vs SPX"
    },
    {
      "name": "technical_analysis",
      "path": "artifacts/technical_analysis.json",
      "format": "json",
      "source": "yfinance+talib",
      "summary": "RSI 45.2, MACD bearish, above 200SMA, ATR $12.30"
    }
  ],
  "error": null
}
```

## DAG Entry

```yaml
technical:
  skill: script
  params:
    script: skills/fetch_technical/fetch_technical.py
    args: {ticker: "${ticker}", workdir: "${workdir}"}
  outputs:
    chart:              {path: "artifacts/chart.png", format: png}
    technical_analysis: {path: "artifacts/technical_analysis.json", format: json}
```

No dependencies — runs in the first DAG iteration alongside `profile`.
