---
name: fetch_wikipedia
description: Fetch Wikipedia company summary
type: python
---

# fetch_wikipedia

Searches Wikipedia for the given stock symbol's company and extracts the lead-section summary. Falls back to yfinance for company name resolution.

## Usage

```bash
./skills/fetch_wikipedia/fetch_wikipedia.py SYMBOL --workdir DIR
```

## Outputs

- `artifacts/wikipedia_summary.txt` — Wikipedia lead-section summary text
