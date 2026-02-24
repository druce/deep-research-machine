---
name: fetch_perplexity
description: Research news, business profile, and executives via Perplexity AI
type: python
---

# fetch_perplexity

Queries Perplexity's sonar-pro model for qualitative research on a public company: recent news stories, business profile narrative, and executive leadership profiles.

## Usage

```bash
./skills/fetch_perplexity/fetch_perplexity.py SYMBOL --workdir DIR
```

## Outputs

- `artifacts/perplexity_news_stories.md` — Recent news and market developments
- `artifacts/perplexity_business_profile.md` — Qualitative business profile
- `artifacts/perplexity_executive_profiles.md` — Key executive leadership profiles
