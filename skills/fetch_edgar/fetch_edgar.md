---
name: fetch_edgar
description: Fetch SEC filings (10-K, 10-Q, 8-K) via edgartools
type: python
---

# fetch_edgar

Retrieves and extracts structured data from SEC EDGAR filings using the edgartools library. Produces filing indexes, 10-K/10-Q item extractions, financial statements, and 8-K summaries.

## Usage

```bash
./skills/fetch_edgar/fetch_edgar.py SYMBOL --workdir DIR [--skip-financials] [--skip-8k]
```

## Outputs

- `artifacts/sec_filings_index.json` — Index of recent filings
- `artifacts/sec_10k_*.md` — Extracted 10-K items (business, risk factors, MD&A, etc.)
- `artifacts/sec_10q_*.md` — Extracted 10-Q items
- `artifacts/sec_*.csv` — Financial statement CSVs (income, balance, cashflow)
- `artifacts/sec_8k_summary.json` — Recent 8-K filing summaries
