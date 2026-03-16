# Wikipedia Research Skill Spec — `fetch_wikipedia.py`

## Overview

New skill that fetches the Wikipedia summary and full article for a company. No source equivalent exists in the original project — this was previously done inline by the orchestrator or skipped entirely. Simple script: resolve company name, fetch Wikipedia page, extract summary + full content, save both.

## Goals

1. Resolve the Wikipedia page for a given stock ticker's company
2. Extract the introductory summary (lead section) as clean text
3. Extract the full Wikipedia article content
4. Save both to text files for downstream writer subagents
5. Output JSON manifest to stdout

## Non-Goals
- Parsing infoboxes or structured data (just prose)
- Historical Wikipedia revisions
- Multiple Wikipedia pages per company

## Dependencies

### Python packages
```
wikipedia-api    # or wikipedia — lightweight Wikipedia access
yfinance         # fallback for company name resolution
```

### Environment Variables

None. Wikipedia API is public and free.

> Scripts call `load_environment()` from `utils.py` at startup to load the project root `.env` file. Scripts that need env vars MUST call this before accessing them. The `.env` file is not committed to version control.

## Output Structure

```
work/SYMBOL_YYYYMMDD/artifacts/
├── wikipedia_summary.txt
└── wikipedia_full.txt
```

## Functions

### `get_company_name(symbol, workdir) -> str`

Resolve company name for Wikipedia lookup. Priority:
1. Read from `{workdir}/artifacts/profile.json` (`company_name` field)
2. Fallback: yfinance `ticker.info['longName']`
3. Fallback: use the symbol itself

### `fetch_wikipedia_summary(company_name, symbol) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]`

Search Wikipedia for the company and extract the lead section and full content.

**Strategy:**
1. Search Wikipedia for `"{company_name}"` — take the first result
2. If no result, try `"{company_name} company"`
3. If no result, try `"{symbol} stock"`
4. Extract the page summary (lead section before the table of contents) and full page content
5. Return the summary text and full content

**Edge cases:**
- Disambiguation pages: if the page is a disambiguation, try appending " (company)" to the search
- Very short summaries (< 100 chars): likely wrong page, try alternative search terms

### `main() -> int`

Entry point. CLI interface:

```
./skills/fetch_wikipedia/fetch_wikipedia.py SYMBOL --workdir DIR
```

| Argument | Required | Purpose |
|----------|----------|---------|
| `SYMBOL` | Yes | Stock ticker symbol |
| `--workdir` | Yes | Work directory path |

**Execution:**
1. Resolve company name from profile.json or yfinance
2. Fetch Wikipedia summary and full page content
3. Save summary to `{workdir}/artifacts/wikipedia_summary.txt` with header (symbol, company name, timestamp)
4. Save full article to `{workdir}/artifacts/wikipedia_full.txt` with header (symbol, company name, page title, timestamp)
5. Print JSON manifest to stdout

**Exit codes:** 0 (success), 1 (partial — summary very short or possibly wrong page), 2 (failure — no Wikipedia page found)

## Manifest Output

```json
{
  "status": "complete",
  "artifacts": [
    {
      "name": "wikipedia_summary",
      "path": "artifacts/wikipedia_summary.txt",
      "format": "txt",
      "source": "wikipedia",
      "summary": "Tesla, Inc. — 2,214 chars, covers founding, products, services"
    },
    {
      "name": "wikipedia_full",
      "path": "artifacts/wikipedia_full.txt",
      "format": "txt",
      "source": "wikipedia",
      "summary": "Tesla, Inc. — full Wikipedia article, 92,170 chars"
    }
  ],
  "error": null
}
```

## Error Handling

- Wikipedia API timeout: retry once after 5s, then fail
- Company not found on Wikipedia: exit 2, note in manifest error field
- Disambiguation page: try `"{company_name} (company)"` before failing
- Network errors: standard retry, fail gracefully

## DAG Entry

```yaml
wikipedia:
  skill: script
  params:
    script: skills/fetch_wikipedia/fetch_wikipedia.py
    args: {ticker: "${ticker}", workdir: "${workdir}"}
  depends_on: [profile]
  outputs:
    wikipedia_summary: {path: "artifacts/wikipedia_summary.txt", format: txt}
    wikipedia_full: {path: "artifacts/wikipedia_full.txt", format: txt}
```

Depends on `profile` (needs company name for accurate Wikipedia search).
