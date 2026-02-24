---
name: fetch_technical
description: Generate stock chart and compute technical indicators via yfinance and TA-Lib
type: python
---

# fetch_technical

Produces a weekly candlestick chart with moving averages and volume, plus a JSON file of daily technical indicators (RSI, MACD, ATR, Bollinger Bands, SMAs, trend signals).

## Usage

```bash
./skills/fetch_technical/fetch_technical.py SYMBOL --workdir DIR
```

## Outputs

- `artifacts/chart.png` — Weekly candlestick chart with MA13/MA52, volume, relative strength vs SPX
- `artifacts/technical_analysis.json` — RSI, MACD, ATR, Bollinger, SMAs, trend signals, narrative
