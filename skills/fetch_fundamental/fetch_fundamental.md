---
name: fetch_fundamental
description: Fetch financial statements, ratios, and analyst data via yfinance
type: python
---

# fetch_fundamental

Fetches fundamental data from yfinance including income statements, balance sheets, cash flow, key ratios, analyst recommendations, and news. Optionally compares metrics to peers.

## Usage

```bash
./skills/fetch_fundamental/fetch_fundamental.py SYMBOL --workdir DIR [--peers-file PATH]
```

## Outputs

- `artifacts/income_statement.csv` — Income statement data
- `artifacts/income_statement_sankey.html` — Interactive Sankey chart (income flow)
- `artifacts/income_statement_sankey.png` — Static Sankey chart (income flow)
- `artifacts/balance_sheet.csv` — Balance sheet data
- `artifacts/cash_flow.csv` — Cash flow statement
- `artifacts/key_ratios.csv` — Key financial ratios
- `artifacts/analyst_recommendations.json` — Analyst consensus and recommendations
- `artifacts/news.json` — Recent news articles
