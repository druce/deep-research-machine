---
name: identify_peers
description: Identify comparable peer companies using provider APIs and yfinance data
type: python
---

# identify_peers

Fetches candidate peers from Finnhub, OpenBB/FMP, and yfinance, enriches each
with fundamental data, filters out bad tickers (private, foreign, no data),
scores by comparability (scale, industry, margins), and selects the top N.

## Usage

```bash
./skills/identify_peers/identify_peers.py SYMBOL [--count 5] [--workdir DIR]
```

## Outputs

- `artifacts/peers_list.json` — column-oriented peer list with symbol, name, price, market_cap
