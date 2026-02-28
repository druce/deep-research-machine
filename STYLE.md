# Profile Section Writer - Style guide for all sections

## Source Reliability Hierarchy (most to least authoritative)

1. `sec_10k_item1_business.md` — authoritative language for business description, segment breakdowns, revenue percentages
2. `profile.json` — market cap, enterprise value, current price, sector, industry, employee count, founding year
3. `perplexity_business_profile.md` — current narrative, revenue figures, FY context
4. `perplexity_executive_profiles.md` — CEO/CFO/COO names, tenures, backgrounds
5. `perplexity_analysis_competitive.md` — market share %, competitive positioning, moats
6. `key_ratios.csv` — peer comparison table; includes DHI and named peers with valuation/profitability metrics
7. `peers_list.json` — canonical peer names and tickers
8. `wikipedia_summary.txt` — founding history, brand names, Fortune 500 ranking
9. `income_statement.csv` — multi-year revenue and net income for trend context

## Key Data Points by Source

- **Revenue (FY)**: Use SEC 10-K figure; cross-check with `perplexity_business_profile.md`
- **Homes closed / avg price**: SEC 10-K Item 1 is most precise
- **Employee count**: `profile.json` is most current
- **Market cap**: `profile.json` or `key_ratios.csv` (consistent)
- **Gross margin / net margin**: `key_ratios.csv` (TTM)
- **Peer group**: `peers_list.json` — filtered and curated; use these names exactly
- **CEO/CFO tenure**: `perplexity_executive_profiles.md`
- **Market share %**: `perplexity_analysis_competitive.md`
- **Brand names**: `wikipedia_summary.txt` (D.R. Horton, Express Homes, Emerald Homes, Freedom Homes)

## Formatting Conventions

- First reference in final report: full legal name + ticker in parens, e.g., "D.R. Horton, Inc. (NYSE: DHI)"
- Subsequent references in final report: "D.R. Horton" or "the company"
- Revenue: always label fiscal year, e.g., "fiscal year 2025 (ended September 30, 2025)"
- Large numbers: "$34.3 billion" not "$34,300,000,000"
- Employee count from `profile.json`, formatted with comma separator
- Fiscal year end for DHI: September 30
