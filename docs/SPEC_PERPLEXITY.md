# Perplexity Research Skill Spec — `fetch_perplexity.py`

## Overview

Queries Perplexity AI (sonar-pro model) for qualitative research on a public company: major news stories, a 10-section business profile, and C-suite executive profiles. Saves Markdown artifacts and outputs a JSON manifest.

## Goals

1. Query Perplexity AI for major news stories (chronological, sourced, factual)
2. Query Perplexity AI for comprehensive 10-section business profile
3. Query Perplexity AI for C-suite executive profiles
4. Output JSON manifest to stdout

## Non-Goals

- Analysis or synthesis of Perplexity results (that's `fetch_analysis.py` and the writer subagents)
- Using Claude for any queries (Perplexity only)

## Dependencies

### Python packages
```
openai          # Perplexity uses OpenAI-compatible API
yfinance        # Fallback for company name lookup
python-dotenv
```

### Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `PERPLEXITY_API_KEY` | Yes | Perplexity API access |

> Scripts call `load_environment()` from `utils.py` at startup to load the project root `.env` file. Scripts that need env vars MUST call this before accessing them. The `.env` file is not committed to version control.

## Functions

- `get_company_name()` — resolve company name from profile.json, yfinance, or symbol fallback
- `query_perplexity()` — API call with exponential backoff retry
- `save_news_research()` — news stories query (NEWS_STORIES_COUNT stories since NEWS_STORIES_SINCE)
- `save_business_profile()` — 10-section business profile query
- `save_executive_profiles()` — C-suite profiles query with compensation data

## Config Constants

All sourced from `config.py`:

| Constant | Purpose |
|----------|---------|
| `PERPLEXITY_MODEL` | Model name (sonar-pro) |
| `PERPLEXITY_TEMPERATURE` | Sampling temperature |
| `PERPLEXITY_MAX_TOKENS` | Dict of per-section max token limits |
| `NEWS_STORIES_COUNT` | Number of news stories to request |
| `NEWS_STORIES_SINCE` | Lookback date for news |
| `MAX_RETRIES` | API retry attempts |
| `RETRY_DELAY_SECONDS` | Initial retry delay |
| `RETRY_BACKOFF_MULTIPLIER` | Exponential backoff multiplier |

## Output Structure

```
work/SYMBOL_YYYYMMDD/artifacts/
├── perplexity_news_stories.md          # Chronological news with sources
├── perplexity_business_profile.md      # 10-section business analysis
└── perplexity_executive_profiles.md    # C-suite profiles with compensation
```

## CLI Interface

```
./skills/fetch_perplexity/fetch_perplexity.py SYMBOL --workdir DIR
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
    {"name": "news_stories", "path": "artifacts/perplexity_news_stories.md", "format": "md", "source": "perplexity", "summary": "15 major news stories since 2024"},
    {"name": "business_profile", "path": "artifacts/perplexity_business_profile.md", "format": "md", "source": "perplexity", "summary": "10-section business profile"},
    {"name": "executive_profiles", "path": "artifacts/perplexity_executive_profiles.md", "format": "md", "source": "perplexity", "summary": "CEO, CFO, COO profiles with compensation"}
  ],
  "error": null
}
```

## DAG Entry

```yaml
perplexity:
  skill: script
  params:
    script: skills/fetch_perplexity/fetch_perplexity.py
    args: {ticker: "${ticker}", workdir: "${workdir}"}
  depends_on: [profile]
  outputs:
    news_stories:       {path: "artifacts/perplexity_news_stories.md", format: md}
    business_profile:   {path: "artifacts/perplexity_business_profile.md", format: md}
    executive_profiles: {path: "artifacts/perplexity_executive_profiles.md", format: md}
```

Depends on `profile` (needs company name for better Perplexity queries).
