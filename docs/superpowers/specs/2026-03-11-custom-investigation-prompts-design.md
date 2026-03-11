# Custom Investigation Prompts

**Date:** 2026-03-11

## Overview

Add user-directed investigation prompts to the equity research pipeline. Before the DAG launches, the user can enter free-form research questions. These are executed in parallel as Claude subprocesses in wave 2, auto-tagged for section relevance, and flow through the existing chunk/index pipeline to be available to research agents and writers.

## 1. Prompt Collection (pre-flight in `research.py`)

Before DAG init, the orchestrator enters an interactive loop via stdin:

```
Custom investigation prompts for AAPL (enter empty line to finish):
[1]> What is Apple's strategy for AI integration across its product line?
[2]> How exposed is Apple to China tariff risk?
[3]>
Saved 2 custom prompts to work/AAPL_20260311/custom_prompts.json
```

Format of `custom_prompts.json`:
```json
[
  {"id": "custom_1", "prompt": "What is Apple's strategy for AI..."},
  {"id": "custom_2", "prompt": "How exposed is Apple to China tariff risk?"}
]
```

If the user enters no prompts, the file is an empty array and the DAG task becomes a no-op.

Workdir must be created before prompt collection (move `mkdir` before the interactive loop). The prompts file is written to `{workdir}/custom_prompts.json`.

## 2. DAG Task: `custom_research`

- **type**: `python`
- **depends_on**: `[profile, peers]`
- **sort_order**: 8
- **script**: `skills/custom_research/custom_research.py`

### Script behavior

1. Read `{workdir}/custom_prompts.json` — if missing or empty array, exit successfully with empty artifact list
2. For each prompt, spawn `claude -p` in parallel (asyncio) with:
   - System prompt: "You are researching {company_name} ({symbol}). Answer the following question thoroughly with sources."
   - The user's prompt text
   - MCP config from `{workdir}/mcp-research.json` (if it exists)
3. Save each response to `artifacts/custom_research_{N}.md`
4. Auto-tag: for each response, ask Claude to classify into relevant sections from: `profile`, `business_model`, `competitive`, `supply_chain`, `financial`, `valuation`, `risk_news`
5. Write tag metadata to `artifacts/custom_research_tags.json`:
   ```json
   [
     {"id": "custom_1", "file": "artifacts/custom_research_1.md", "tags": ["competitive", "business_model"]},
     {"id": "custom_2", "file": "artifacts/custom_research_2.md", "tags": ["risk_news", "supply_chain"]}
   ]
   ```
6. Output standard JSON manifest to stdout

### Standard conventions

- `#!/usr/bin/env python3` shebang
- `pathlib.Path` for paths
- `logger = setup_logging(__name__)` for output
- Type hints, specific exception handling
- JSON manifest to stdout: `{"status": "complete", "artifacts": [...], "error": null}`

## 3. Downstream Changes

### `chunk_documents` dependency update

Add `custom_research` to the `depends_on` list in `dags/sra.yaml`:

```yaml
chunk_documents:
  depends_on: [technical, fundamental, detailed_profile, fetch_edgar, wikipedia, custom_research]
```

### No other changes needed

- `chunk_documents.py` already processes all `.md` files in `artifacts/` — custom research files are picked up automatically
- `tag_chunks` re-tags everything regardless
- `build_index`, research agents, and writers work via the index — no changes needed

## 4. Files to Create/Modify

| File | Action |
|------|--------|
| `skills/custom_research/custom_research.py` | Create — main script |
| `skills/custom_research/__init__.py` | Create — empty |
| `research.py` | Modify — add interactive prompt collection before DAG init |
| `dags/sra.yaml` | Modify — add `custom_research` task, update `chunk_documents` deps |
| `CLAUDE.md` | Modify — document new task in architecture section |
