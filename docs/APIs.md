# API Sources & Data Gaps

Current state of external data sources used by the research pipeline, identified gaps, and pricing for upgrade paths. Last updated 2026-03-15.

## Current APIs in Use

| API | Library / Access | Auth | Used In | Data Produced |
|-----|-----------------|------|---------|---------------|
| **yfinance** | `yfinance` PyPI | None | `fetch_profile`, `fetch_technical`, `fetch_fundamental` | Profile, OHLCV, financials, ratios, analyst recs, news |
| **SEC EDGAR** | `edgartools` PyPI | SEC_FIRM + SEC_USER (identity, not key) | `fetch_edgar` | 10-K/10-Q items, 8-K filings, financial statements |
| **Wikipedia** | `wikipedia` PyPI | None | `fetch_wikipedia` | Company summary + full article |
| **OpenAI** | `openai` PyPI | OPENAI_API_KEY | `chunk_documents`, `chunk_research` | Embeddings (text-embedding-3-small) |
| **FMP** | MCP server (claude.ai) | FMP_API_KEY | MCP proxy for research agents | Company data, financials, news, grades, etc. |
| **Finnhub** | `finnhub` PyPI | FINNHUB_API_KEY | `identify_peers` | Peer company lists |
| **Claude** | `claude` CLI subprocess | None (Claude Code auth) | Writing tasks, research agents, detailed_profile | Narrative analysis, web search results |
| **TA-Lib** | `TA-Lib` C library | None | `fetch_technical` | Technical indicators (SMA, RSI, MACD, etc.) |
| **Plotly** | `plotly` PyPI | None | `fetch_technical`, `fetch_fundamental` | Charts (PNG), Sankey diagrams |
| **LanceDB** | `lancedb` PyPI | None | `build_index`, `search_index` | Hybrid vector + BM25 search index |

## FMP Subscription (Current: Starter or Premium)

### Endpoints That Work

| Endpoint | Data | Quality |
|----------|------|---------|
| `insider-trade-statistics` | Quarterly buy/sell ratios, volumes by symbol | Rich — back to 1999, CIK included |
| `search-insider-trades` | Individual Form 4 transactions | Names, titles, prices, shares, SEC links |
| `latest-insider-trade` | Cross-market latest insider filings | Good for screening |
| `acquisition-ownership` | Schedule 13D/13G beneficial ownership | Major holders (BlackRock, Fidelity, etc.) |
| `quote`, `profile-symbol`, `key-metrics`, etc. | Standard financial data | Used via MCP proxy |

### Endpoints Paywalled (402 — Requires Ultimate $149/mo)

| Endpoint | Data | Value for Pipeline |
|----------|------|--------------------|
| `transcripts-dates-by-symbol` | Earnings call transcript dates | **High** — would identify available quarters |
| `search-transcripts` | Full earnings call transcript text | **High** — management tone, forward guidance, analyst Q&A |
| `positions-summary` | Institutional ownership summary by symbol | **High** — investor count, share changes, ownership % |
| `form-13f-filings-dates` | 13F filing dates by institution | Medium — filing schedule |
| `filings-extract` | Detailed 13F holdings data | **High** — per-position shares, value, changes |
| `filings-extract-with-analytics-by-holder` | 13F + analytics per holder | **High** — portfolio strategy, position changes |
| `holder-performance-summary` | Institutional holder performance | Medium — benchmark comparison |

### FMP Plan Tiers

| Plan | Price | Rate Limit | Key Additions |
|------|-------|-----------|---------------|
| **Basic** | Free | 250/day | EOD data, 5yr history, 150+ endpoints |
| **Starter** | $22/mo | 300/min | US fundamentals, ratios, news, crypto/forex |
| **Premium** | $59/mo | 750/min | US/UK/CA, 30yr history, intraday, technicals |
| **Ultimate** | $149/mo | 3000/min | Global, **earnings transcripts, 13F holdings, positions-summary** |

Source: [FMP Pricing](https://site.financialmodelingprep.com/pricing-plans)

## Finnhub Subscription (Current: Free)

### Endpoints That Work

| Endpoint | Data |
|----------|------|
| `company_peers` | Peer company symbols |
| `stock_insider_transactions` | Form 4 transactions (729 records for NVDA, back years) |
| `stock_insider_sentiment` | Monthly MSPR (net purchase ratio) |

### Endpoints Paywalled (403)

| Endpoint | Data | Required Tier |
|----------|------|---------------|
| `transcripts_list` | Available transcript dates | Unknown — Finnhub pricing is opaque |
| `transcripts` | Full transcript text by ID | Unknown |

### Finnhub Pricing (modular, not tiered)

| Add-on | Price/mo | Includes |
|--------|----------|----------|
| Fundamental Tier 1 | $50 | Core fundamentals |
| Fundamental Tier 2 | $200 | Extended fundamentals |
| Estimate Tier 1 | $75 | Consensus estimates |
| Market Data Basic | $49.99 | Real-time quotes |
| All Tier 1 | $3,000 | Everything |

Transcript access tier is undocumented. Likely requires Fundamental Tier 2 ($200/mo) or higher.

Source: [Finnhub Pricing](https://finnhub.io/pricing)

## Earnings Call Transcripts — All Sources Evaluated

Transcripts are **not SEC filings**. Companies hold public calls but aren't required to file the transcript. Every broad-coverage source is paywalled.

| Source | Status | Coverage | Cost |
|--------|--------|----------|------|
| **FMP** | 402 | Broad | Ultimate $149/mo |
| **Finnhub** | 403 | Unknown | Likely $200/mo |
| **earningscall.biz** | Works but free = AAPL + MSFT only | 8,000+ companies paid | Unknown (key signup required) |
| **API Ninjas** | Endpoint works, needs free key | Broad (claims 8,000+ back to 2005). Returns transcript, participants, summary, sentiment | Free key (limited), $39/mo commercial |
| **Seeking Alpha** | Web scraping only | 4,500+ companies | Free to read, no API |
| **SEC EDGAR** | N/A | Some companies file as 8-K Item 7.01 exhibit, but inconsistent | Free |

### earningscall.biz Python Library

```python
from earningscall import get_company
transcript = get_company('AAPL').get_transcript(year=2024, quarter=4)
# → 45,513 chars, has .text, .prepared_remarks, .questions_and_answers, .speakers, .event
```

Best data model (speaker segmentation, Q&A split, event metadata), but free tier is demo-only.

### API Ninjas

```
GET https://api.api-ninjas.com/v1/earningstranscript?ticker=NVDA&year=2025&quarter=4
X-Api-Key: YOUR_KEY
```

Returns transcript text, participants (name/role/company), summary, and sentiment score. Free key signup (no credit card). Commercial use requires $39/mo.

### Recommendation

**Best value**: FMP Ultimate ($149/mo) — gets transcripts AND 13F institutional data in one upgrade. If budget-constrained, API Ninjas ($39/mo) is the cheapest path to broad transcript coverage.

## Insider Trading — Free via SEC EDGAR

Insider transactions (Form 3/4/5) are SEC filings. **No paid API needed.**

### edgartools (already in use)

```python
from edgar import Company
company = Company("NVDA")
form4s = company.get_filings(form="4")
form4 = form4s[0].obj()
# → reporting_owner_name, transaction_date, shares, price_per_share, transaction_code
# → get_net_shares_traded(), to_dataframe()
```

Supports date range filtering, DataFrame conversion, insider name filtering. Free, no API key, no rate limit beyond SEC's 10 req/sec.

### FMP (also works on current plan)

`insider-trade-statistics` and `search-insider-trades` both work. Provides pre-aggregated quarterly stats and individual transactions. Useful as a supplement/cross-check to edgartools.

### Finnhub (also works on free tier)

`stock_insider_transactions` returns 729 records for NVDA with transaction codes, prices, and share counts. `stock_insider_sentiment` gives monthly MSPR (net purchase ratio).

### Recommendation

**Primary**: Build `fetch_insider_trades.py` using edgartools Form 4 (free, already a dependency, richest data model with `to_dataframe()`). **Secondary**: Cross-reference with FMP `insider-trade-statistics` for quarterly aggregates.

## Institutional Ownership (13F) — Free but Complex

13F filings are SEC filings, but filed by the *institution* not the company. To answer "who owns NVDA" requires either:

1. **Aggregated API** (FMP `positions-summary`, paywalled at $149/mo) — easiest
2. **SEC bulk data** at `data.sec.gov/submissions/CIK##########.json` — free but requires CUSIP-based lookup across all institutional filers
3. **edgartools** — can retrieve 13F filings but requires knowing the filer CIK, not the held company

### What's Available Now (Free)

| Source | Endpoint | Data |
|--------|----------|------|
| FMP | `acquisition-ownership` | Schedule 13D/13G only (>5% holders) — BlackRock, FMR, etc. |
| SEC EDGAR | `data.sec.gov` JSON API | Raw 13F filings by filer CIK |
| edgartools | `get_filings(form="13F-HR")` | Raw 13F filings, need per-filer parsing |

### Recommendation

**Short-term**: Use FMP `acquisition-ownership` (works now) for major holders (>5%). **Long-term**: Upgrade to FMP Ultimate for `positions-summary` which gives the full institutional ownership picture pre-aggregated, or build a CUSIP-based 13F parser against SEC bulk data.

## Data Gaps Summary

| Gap | Priority | Free Path | Paid Path |
|-----|----------|-----------|-----------|
| **Insider trades** (Form 3/4/5) | **High** | edgartools — ready to build | Already have FMP + Finnhub |
| **Earnings transcripts** | **High** | API Ninjas free key (test) | FMP Ultimate $149/mo or API Ninjas $39/mo |
| **Institutional ownership** | **Medium** | FMP `acquisition-ownership` (>5% holders only) | FMP Ultimate $149/mo |
| **Revenue segmentation** | Low | FMP `revenue-geographic-segments` / `revenue-product-segmentation` (test if available) | — |
| **Price targets / grades** | Low | FMP `grades`, `price-target-consensus` (test if available) | — |
| **Congressional trading** | Low | FMP `senate-trading`, `house-trading` (test if available) | — |
| **ESG ratings** | Low | FMP `esg-ratings` (test if available) | — |

## Next Steps

1. **Build `fetch_insider_trades.py`** — edgartools Form 4, zero cost
2. **Sign up for API Ninjas free key** — test transcript coverage for NVDA
3. **Evaluate FMP Ultimate** ($149/mo) — single upgrade unlocks transcripts + 13F + all paywalled endpoints
