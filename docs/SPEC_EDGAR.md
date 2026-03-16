# SEC Filings Skill Spec — `fetch_edgar.py`

## Overview

Extracts structured data from SEC EDGAR filings using the `edgartools` library. Produces filing indexes, 10-K/10-Q item extractions, financial statements (as CSV), and 8-K summaries.

## Goals

1. Download and catalog the last year of important SEC filings (10-K, 10-Q, 8-K) for a given ticker
2. Extract specific 10-K items (Item 1 Business, Item 1A Risk Factors, Item 7 MD&A, etc.) as clean text
3. Extract specific 10-Q items (MD&A, etc.) from the latest quarterly report
4. Extract financial statements (income statement, balance sheet, cash flow) from the latest annual and quarterly filings as CSV
5. Produce a JSON manifest on stdout summarizing all artifacts

## Non-Goals

- Parsing proxy statements (DEF 14A), 13F, or S-1 filings
- Multi-year financial statement history (just latest annual + latest quarterly)
- Historical analysis beyond 1 year of filings
- Real-time filing alerts
- Replacing yfinance fundamental data (this supplements it with authoritative SEC source data)

## Dependencies

```pip
edgartools
```

### Environment Variables

| Variable     | Required | Purpose                                        |
|--------------|----------|------------------------------------------------|
| `SEC_FIRM`   | Yes      | Company name for SEC EDGAR User-Agent header   |
| `SEC_USER`   | Yes      | Contact email for SEC EDGAR User-Agent header  |

**No API key required.** Edgartools uses the public SEC EDGAR API directly. SEC EDGAR requires a User-Agent header with a company name and email. Edgartools handles this via `edgar.set_identity()`.

> Scripts call `load_environment()` from `utils.py` at startup to load the project root `.env` file. Scripts that need env vars MUST call this before accessing them. The `.env` file is not committed to version control.

## Configuration (`config.py`)

```python
# SEC Filing Configuration (edgartools)
SEC_FILING_FORMS = ['10-K', '10-Q', '8-K']
SEC_LOOKBACK_DAYS = 365
SEC_10K_ITEMS = ['Item 1', 'Item 1A', 'Item 7']
SEC_10Q_ITEMS = ['Item 2']  # MD&A (Item 2 in 10-Q maps to Item 7 in 10-K)
```

## CLI

```bash
./skills/fetch_edgar/fetch_edgar.py SYMBOL --workdir DIR [--skip-financials] [--skip-8k]
```

**Exit codes:**

- `0` — all steps succeeded
- `1` — partial success (some artifacts produced)
- `2` — total failure (no artifacts produced)

**Stdout:** JSON manifest of produced artifacts.
**Stderr:** All progress/diagnostic logging.

## Output Structure

```bash
work/SYMBOL_YYYYMMDD/artifacts/
├── sec_filings_index.json
├── sec_10k_metadata.json
├── sec_10k_item1_business.md
├── sec_10k_item1a_risk_factors.md
├── sec_10k_item7_mda.md
├── sec_10q_metadata.json
├── sec_10q_item2_mda.md
├── sec_income_annual.csv
├── sec_income_quarterly.csv
├── sec_balance_annual.csv
├── sec_balance_quarterly.csv
├── sec_cashflow_annual.csv
├── sec_cashflow_quarterly.csv
└── sec_8k_summary.json
```

## Item Maps

The implementation supports a broad set of items via lookup maps. The default items extracted are controlled by `SEC_10K_ITEMS` and `SEC_10Q_ITEMS` in config.

**10-K items:**

| Key | Filename Suffix | Label |
| --- | --------------- | ----- |
| Item 1 | `item1_business` | Business |
| Item 1A | `item1a_risk_factors` | Risk Factors |
| Item 1B | `item1b_unresolved` | Unresolved Staff Comments |
| Item 2 | `item2_properties` | Properties |
| Item 3 | `item3_legal` | Legal Proceedings |
| Item 5 | `item5_market` | Market Information |
| Item 6 | `item6_financials` | Selected Financial Data |
| Item 7 | `item7_mda` | MD&A |
| Item 7A | `item7a_market_risk` | Market Risk Disclosures |
| Item 8 | `item8_financial_statements` | Financial Statements |
| Item 9 | `item9_disagreements` | Disagreements with Accountants |
| Item 9A | `item9a_controls` | Controls and Procedures |

**10-Q items:**

| Key | Filename Suffix | Label |
| --- | --------------- | ----- |
| Item 1 | `item1_financials` | Financial Statements |
| Item 2 | `item2_mda` | MD&A |
| Item 3 | `item3_market_risk` | Market Risk |
| Item 4 | `item4_controls` | Controls and Procedures |

Items not in these maps fall back to a sanitized key as suffix.

## Functions

### `_init_edgar() -> bool`

Sets SEC EDGAR identity from `SEC_FIRM` and `SEC_USER` environment variables via `edgar.set_identity()`. Returns `True` on success, `False` if env vars are missing or initialization fails.

### `_get_company(symbol) -> Company | None`

Creates an `edgar.Company` object for the given ticker. Returns `None` on failure.

### `get_filing_index(symbol, workdir, lookback_days=SEC_LOOKBACK_DAYS) -> Tuple[bool, Optional[List[Dict]], Optional[str]]`

Retrieves all 10-K, 10-Q, and 8-K filings within the lookback period. Returns a list of dicts sorted by filing date descending:

```json
[
  {
    "form": "10-K",
    "filing_date": "2025-02-25",
    "accession_number": "0000063908-25-000012",
    "description": "Annual Report"
  }
]
```

Saved to `sec_filings_index.json`.

### `get_10k_items(symbol, workdir, items=None) -> Tuple[bool, Optional[Dict[str, str]], Optional[str]]`

Extracts items from the latest 10-K filing. Defaults to `SEC_10K_ITEMS` from config.

Uses `filing.obj()` to get a `TenK` object, then accesses items via dict-style lookup: `tenk["Item 1"]`, `tenk["Item 1A"]`, `tenk["Item 7"]`.

Each item saved as a separate markdown file with `sec_10k_` prefix. Also saves `sec_10k_metadata.json` with filing metadata and extraction results.

### `get_10q_items(symbol, workdir) -> Tuple[bool, Optional[Dict[str, str]], Optional[str]]`

Extracts items from the latest 10-Q filing. Uses `SEC_10Q_ITEMS` from config.

Uses `filing.obj()` to get a `TenQ` object, then accesses items via dict-style lookup: `tenq["Item 2"]`.

Each item saved as a separate markdown file with `sec_10q_` prefix. Also saves `sec_10q_metadata.json`.

### `_save_financials_object(financials_obj, label, artifacts_dir) -> List[Dict]`

Extracts `income_statement`, `balance_sheet`, and `cash_flow_statement` from a financials object. Tries `.to_dataframe()`, `.to_pandas()`, or direct DataFrame detection. Falls back to saving as `.txt` if DataFrame conversion fails.

Returns a list of artifact metadata dicts for the manifest.

### `get_financials(symbol, workdir) -> Tuple[bool, Optional[Dict], Optional[str]]`

Extracts financial statements from the latest annual and quarterly filings. Tries `company.financials` / `company.get_financials()` for annual, and `company.quarterly_financials` / `company.get_quarterly_financials()` for quarterly.

Returns `(True, {"statements": [...]}, None)` on success, where statements is a list of artifact dicts.

### `get_recent_8k(symbol, workdir, lookback_days=SEC_LOOKBACK_DAYS) -> Tuple[bool, Optional[List[Dict]], Optional[str]]`

Summarizes recent 8-K filings within the lookback period. For each 8-K, captures filing date, accession number, description, and items reported (best-effort via `filing.obj()`).

Saved to `sec_8k_summary.json`.

### `_build_manifest(status, artifacts, error=None) -> Dict`

Builds the JSON manifest dict emitted to stdout with `status`, `artifacts` list, and optional `error`.

### `main() -> int`

CLI entry point. Runs steps in sequence:

1. `get_filing_index` — always runs
2. `get_10k_items` — extracts items from latest 10-K
3. `get_10q_items` — extracts items from latest 10-Q
4. `get_financials` — unless `--skip-financials`
5. `get_recent_8k` — unless `--skip-8k`

Emits JSON manifest to stdout. Returns exit code 0/1/2 based on success/partial/failure.

## Error Handling

- If edgartools can't find a company by ticker, log error and return early
- If a specific item extraction fails (e.g., Item 7 not parseable), log warning, continue with remaining items, save what succeeded
- If no 10-K exists, log warning, skip 10-K item extraction, still attempt 10-Q, financials, and 8-K
- If no 10-Q exists, log warning, skip 10-Q item extraction, continue with remaining steps
- SEC EDGAR rate limit (10 req/sec): edgartools handles this internally
- All public functions return `Tuple[bool, Optional[Data], Optional[str]]` per project convention

## Integration with Pipeline

Outputs go to the flat `artifacts/` directory with `sec_` prefix. The DAG runner dispatches this as a `python` task type via `dags/sra.yaml`. Identity is set via `SEC_FIRM` and `SEC_USER` env vars (no API key).

## Design Decisions

- **Item access**: Dict-style (`tenk["Item 1"]`) rather than attribute-based — more flexible and works with any item key string
- **10-Q items**: Extract MD&A (Item 2) from the latest 10-Q for quarterly context alongside annual 10-K data
- **Financial statement depth**: Latest only — no multi-year history. Just the most recent annual and most recent quarterly filing
- **8-K detail level**: Summary only — filing date, description, and items reported. No full text extraction
- **Output dir naming**: Flat `artifacts/` with `sec_` prefix to avoid collisions
- **Manifest output**: JSON manifest to stdout for pipeline consumption; all diagnostic logging to stderr
