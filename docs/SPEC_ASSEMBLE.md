# Assembly Skill Spec — `assemble.py`

## Overview

New script that reads completed section artifacts from the database and assembles them into a single report using a Jinja template. This replaces the complex `research_report.py` from the source project — since each section is already fully written by a writer subagent, assembly is just template rendering with pre-written content.

## Goals

1. Query the database for completed section artifacts (from `write_*` tasks)
2. Read each section's markdown content from disk
3. Read profile/metadata for report header (ticker, company name, date)
4. Render a Jinja template with sections in the correct order
5. Save assembled report as markdown
6. Output JSON manifest to stdout

## Non-Goals

- Writing or synthesizing any content (sections are pre-written by subagents)
- Format conversion (HTML, DOCX — that's a post-processing concern)
- Chart embedding (charts are referenced by path, not inlined)
- Critiquing or revising content (that's the `polish` task)

## Dependencies

### Python packages
```
jinja2
PyYAML       # for reading DAG to determine section order
```

Plus `sqlite3`, `json`, `argparse`, `pathlib` (stdlib).

## Output Structure

```
work/SYMBOL_YYYYMMDD/artifacts/
└── research_report.md       # Assembled report with all sections
```

## How Section Order is Determined

The Jinja template defines the section order explicitly. The script provides section content keyed by task_id. The template controls layout:

```jinja
# {{ ticker }} — Equity Research Report
**Date:** {{ date }}
**Company:** {{ company_name }}

---

{{ sections.write_executive_summary }}

{{ sections.write_fundamental_analysis }}

{{ sections.write_company_profile }}

{{ sections.write_business_model }}

{{ sections.write_competitive_landscape }}

{{ sections.write_supply_chain }}

{{ sections.write_leverage }}

{{ sections.write_valuation }}

{{ sections.write_news }}

{{ sections.write_risks }}

{{ sections.write_thesis }}

{{ sections.write_conclusion }}
```

Alternatively, the template can iterate over an ordered list if section order is defined in the DAG YAML.

## Functions

### `get_sections(workdir) -> Dict[str, str]`

Query the database for all artifacts from `write_*` tasks that have `name = "section"`. Sections are now at paths like `artifacts/01_fundamental_analysis.md`, `artifacts/02_company_profile.md`, etc. Read each file's content. Return a dict mapping task_id to content:

```python
{
    "write_executive_summary": "## Executive Summary\n\nTesla...",
    "write_fundamental_analysis": "## Fundamental Analysis\n\nRevenue...",
    ...
}
```

Missing sections (failed/skipped tasks) return a placeholder: `*[Section not available — {task_id} {status}]*`

### `get_report_metadata(workdir) -> Dict`

Read from `research` table and `profile.json`:
- `ticker`
- `date`
- `company_name` (from profile.json)
- `sector`, `industry` (from profile.json)
- `timestamp` (current)

### `assemble(workdir, template_path) -> str`

1. Load sections via `get_sections()`
2. Load metadata via `get_report_metadata()`
3. Set up Jinja environment
4. Render template with `sections` dict + metadata
5. Return rendered markdown string

### `main() -> int`

Entry point. CLI interface:

```
./skills/assemble.py --workdir DIR --template PATH
```

| Argument | Required | Default | Purpose |
|----------|----------|---------|---------|
| `--workdir` | Yes | — | Work directory path |
| `--template` | No | `templates/equity_research_report.md.j2` | Jinja template path |

**Execution:**
1. Assemble report
2. Save to `{workdir}/artifacts/research_report.md`
3. Print JSON manifest to stdout

**Exit codes:** 0 (success), 1 (partial — some sections missing), 2 (failure — template error or no sections)

## Manifest Output

```json
{
  "status": "complete",
  "artifacts": [
    {
      "name": "report",
      "path": "artifacts/research_report.md",
      "format": "md",
      "source": "jinja2",
      "summary": "Assembled report with 8/8 sections, 12,450 words"
    }
  ],
  "error": null
}
```

## Template Requirements

The simplified assembly template (`templates/equity_research_report.md.j2`) needs to be rewritten to work with the new `sections` dict format instead of the current raw-data template variables. It should:

1. Accept `sections` dict keyed by task_id
2. Accept metadata: `ticker`, `date`, `company_name`, `sector`, `industry`
3. Render sections in a fixed order
4. Handle missing sections with placeholder text
5. Include report header and footer

## DAG Entry

```yaml
assembly:
  skill: script:assemble
  params:
    script: skills/assemble.py
    args: {template: "templates/equity_research_report.md.j2", workdir: "${workdir}"}
  depends_on: [write_executive_summary, write_conclusion]
  outputs:
    report: {path: "artifacts/research_report.md", format: md}
```

## Design Decisions

- **Reads from db, not filesystem scanning:** Uses `artifact-list` to find section files, ensuring only registered artifacts are included.
- **Template controls order:** Rather than alphabetical or DAG-order, the Jinja template explicitly defines section sequence. This gives full control over report structure.
- **Minimal logic:** This script is intentionally simple — all intelligence is in the writer subagents and the template. Assembly is mechanical.
- **No database writes beyond artifact registration:** The script reads sections from db artifacts, renders template, saves file, registers its own artifact. It doesn't modify task states (that's the taskrunner's job).
