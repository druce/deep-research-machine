# Stock Research Agent: Claude Code Orchestrator Rewrite

**Date:** 2026-02-22
**Status:** Approved design

## Overview

Rewrite the stock research agent so that Claude Code is the orchestrator. A `/research` skill handles interactive setup, initializes a SQLite database, and runs a DAG defined in YAML. A `/taskrunner` skill dispatches individual tasks — calling the specified skill with params. A SQLite + files hybrid storage layer lets all subagents discover and share data without knowing about each other.

## Design Decisions

- **Claude Code as orchestrator** replaces `research_stock.py` — no Python orchestration layer
- **Generic DAG execution** — pipeline defined in YAML, no hardcoded stages
- **Unified `tasks` table** — data-gathering and writing are both just tasks with dependencies
- **Two skills**: `research` (owns the DAG loop) and `taskrunner` (dispatches a single task)
- **Python scripts stay** as data-fetching tools — reliable, tested, called by taskrunner via Bash
- **SQLite + files** for shared storage — SQLite is the index/metadata, files hold raw data
- **Critic-optimizer loop** for every report section — draft, critique, revise
- **Parallel everything** — runner dispatches all ready tasks in parallel
- **Perplexity for data gathering**, Claude Code supplements at write time with WebSearch
- **One stock per run** — scoped to single ticker, simple storage model

---

## 1. Pipeline Architecture

### Two Skills

**`/research` skill** — entry point and DAG runner:
1. Takes a ticker and optional dag_file (defaults to `dags/sra.yaml`)
2. Creates `work/{SYMBOL}_{DATE}/`, initializes `research.db` from the DAG
3. Presents the DAG to the user — they can confirm or edit
4. Runs the DAG loop: query for ready tasks, dispatch them all in parallel via `/taskrunner`, wait, repeat

**`/taskrunner` skill** — dispatches a single task:
1. Reads the task config from `research.db`
2. Based on `skill` type, dispatches appropriately:
   - `script` → runs Python script via Bash, captures manifest, registers artifacts
   - `subagent:writer` → runs critic-optimizer loop, writes section to file, registers artifact
   - `subagent:polish` → reads assembled report, critiques, rewrites
   - `script:assemble` → runs assemble.py with Jinja template
3. Updates task status and summary in `research.db`

### Execution Flow

```
/research TSLA
     │
     ▼
┌───────────────────┐
│  Stage 1: INTAKE  │  Interactive: ask ticker, present DAG, user confirms or edits
└────┬──────────────┘
     │
     ▼
┌──────────────────────────────────────────────────────────────┐
│  DAG RUNNER LOOP                                             │
│                                                              │
│  repeat:                                                     │
│    ready_tasks = db.py task-ready                            │
│    if none → done                                            │
│    dispatch all ready_tasks in parallel via /taskrunner      │
│    wait for completions                                      │
│    print status summary                                      │
│                                                              │
│  Iteration 1: profile, technical                             │
│  Iteration 2: fundamental, perplexity, sec_edgar, wikipedia, │
│               analysis  (all depend on profile)              │
│  Iteration 3: write_fundamental_analysis,                    │
│               write_company_profile, write_business_model,   │
│               write_competitive_landscape, write_supply_chain,│
│               write_leverage, write_valuation, write_news,   │
│               write_risks, write_thesis                      │
│  Iteration 4: write_executive_summary, write_conclusion      │
│               (depend on body writers)                        │
│  Iteration 5: assembly (depends on all writers)              │
│  Iteration 6: polish (depends on assembly)                   │
└──────────────────────────────────────────────────────────────┘

Output: work/TSLA_20260222/artifacts/final_report.{md,html,docx}
```

No hardcoded stages — the DAG dependencies produce the right execution order automatically.

---

## 2. Storage Layer

### SQLite Schema

One database per run at `work/{SYMBOL}_{DATE}/research.db`:

```sql
CREATE TABLE research (
    id            INTEGER PRIMARY KEY,
    ticker        TEXT NOT NULL,
    date          TEXT NOT NULL,
    dag_file      TEXT NOT NULL,           -- path to YAML DAG file defining task nodes
    template_dir  TEXT NOT NULL,           -- path to templates directory
    workdir       TEXT NOT NULL,           -- directory to store artifacts and final report
    status        TEXT DEFAULT 'not started',  -- not started|running|complete|failed
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT
);

CREATE TABLE tasks (
    id            TEXT PRIMARY KEY,        -- matches YAML task id: "technical", "write_risks"
    skill         TEXT NOT NULL,           -- "script", "subagent:writer", "subagent:polish", "script:assemble"
    description   TEXT,                    -- human-readable description from YAML
    params        TEXT NOT NULL,           -- JSON: skill-specific params (script path, args, guidelines, reads_from, title)
    concurrency   TEXT DEFAULT 'parallel', -- parallel|sequential|inherit
    status        TEXT DEFAULT 'pending',  -- pending|running|complete|failed|skipped
    started_at    TEXT,
    completed_at  TEXT,
    error         TEXT,
    summary       TEXT                     -- brief result summary for downstream tasks to scan
);

CREATE TABLE task_deps (
    task_id       TEXT NOT NULL REFERENCES tasks(id),
    depends_on    TEXT NOT NULL REFERENCES tasks(id),
    PRIMARY KEY (task_id, depends_on)
);

CREATE TABLE artifacts (
    id            INTEGER PRIMARY KEY,
    task_id       TEXT NOT NULL REFERENCES tasks(id),
    name          TEXT NOT NULL,           -- "chart", "peers_list", "section"
    path          TEXT NOT NULL,           -- relative to workdir
    format        TEXT NOT NULL,           -- json, csv, md, png, txt
    source        TEXT,                    -- yfinance, finnhub, perplexity, claude
    summary       TEXT,                    -- one-line description
    size_bytes    INTEGER,
    created_at    TEXT DEFAULT (datetime('now'))
);
```

### File Layout

```
work/TSLA_20260222/
├── research.db
└── artifacts/
    ├── profile.json
    ├── peers_list.json
    ├── chart.png
    ├── technical_analysis.json
    ├── income_statement.csv
    ├── balance_sheet.csv
    ├── cash_flow.csv
    ├── key_ratios.csv
    ├── analyst_recommendations.json
    ├── news_stories.md
    ├── business_profile.md
    ├── executive_profiles.md
    ├── sec_filings_index.json
    ├── sec_10k_metadata.json
    ├── sec_10k_item1_business.md
    ├── sec_10k_item1a_risk_factors.md
    ├── sec_10k_item7_mda.md
    ├── sec_10q_metadata.json
    ├── sec_10q_item2_mda.md
    ├── sec_10q_financial_tables.csv
    ├── sec_income_annual.csv
    ├── sec_income_quarterly.csv
    ├── sec_balance_annual.csv
    ├── sec_balance_quarterly.csv
    ├── sec_cashflow_annual.csv
    ├── sec_cashflow_quarterly.csv
    ├── sec_8k_summary.json
    ├── wikipedia_summary.txt
    ├── business_model_analysis.md
    ├── competitive_analysis.md
    ├── risk_analysis.md
    ├── investment_thesis.md
    ├── 00_executive_summary.md
    ├── 01_fundamental_analysis.md
    ├── 02_company_profile.md
    ├── 03_business_model.md
    ├── 04_competitive_landscape.md
    ├── 05_supply_chain.md
    ├── 06_leverage.md
    ├── 07_valuation.md
    ├── 08_news.md
    ├── 09_risks.md
    ├── 10_thesis.md
    ├── 11_conclusion.md
    ├── research_report.md
    └── final_report.md
```

Subagents never know about each other. They read from and write to the database. The DAG runner queries `task-ready` to know what to dispatch next.

---

## 3. DAG YAML Format

The DAG file is the single source of truth for the pipeline. It defines all tasks, their skills, params, dependencies, and expected outputs.

```yaml
# dags/sra.yaml
version: 1
name: Equity Research Report
inputs:
  ticker: ${ticker}
  workdir: ${workdir}
root_dir: ..
template_dir: ../templates

tasks:
  # --- Data gathering tasks ---
  profile:
    description: Get company profile data based on symbol
    type: skill
    command: profile
    args: {ticker: "${ticker}", workdir: "${workdir}"}
    outputs:
      profile:    {path: "artifacts/profile.json", format: json}
      peers_list: {path: "artifacts/peers_list.json", format: json}

  technical:
    description: Generate stock chart and technical indicators
    type: skill
    command: technical
    depends_on: [profile]
    params:
      script: skills/fetch_technical/fetch_technical.py
      args: {ticker: "${ticker}", workdir: "${workdir}"}
    outputs:
      chart:              {path: "artifacts/chart.png", format: png}
      technical_analysis: {path: "artifacts/technical_analysis.json", format: json}

  fundamental:
    description: Fetch financial statements, ratios, and analyst data
    type: skill
    command: fundamental
    depends_on: [profile]
    params:
      script: skills/fetch_fundamental/fetch_fundamental.py
      args: {ticker: "${ticker}", workdir: "${workdir}", peers_file: "artifacts/peers_list.json"}
    outputs:
      income_statement:        {path: "artifacts/income_statement.csv", format: csv}
      balance_sheet:           {path: "artifacts/balance_sheet.csv", format: csv}
      cash_flow:               {path: "artifacts/cash_flow.csv", format: csv}
      key_ratios:              {path: "artifacts/key_ratios.csv", format: csv}
      analyst_recommendations: {path: "artifacts/analyst_recommendations.json", format: json}

  perplexity:
    description: Research news, business profile, and executives via Perplexity AI
    type: skill
    command: perplexity
    depends_on: [profile]
    params:
      script: skills/fetch_perplexity/fetch_perplexity.py
      args: {ticker: "${ticker}", workdir: "${workdir}"}
    outputs:
      news_stories:       {path: "artifacts/news_stories.md", format: md}
      business_profile:   {path: "artifacts/business_profile.md", format: md}
      executive_profiles: {path: "artifacts/executive_profiles.md", format: md}

  sec_edgar:
    description: Fetch SEC filings (10-K, 10-Q, 8-K) via edgartools
    type: skill
    command: sec_edgar
    depends_on: [profile]
    params:
      script: skills/fetch_edgar/fetch_edgar.py
      args: {ticker: "${ticker}", workdir: "${workdir}"}
    outputs:
      filings_index:      {path: "artifacts/sec_filings_index.json", format: json}
      10k_metadata:       {path: "artifacts/sec_10k_metadata.json", format: json}
      10k_item1_business: {path: "artifacts/sec_10k_item1_business.md", format: md}
      10k_item1a_risk:    {path: "artifacts/sec_10k_item1a_risk_factors.md", format: md}
      10k_item7_mda:      {path: "artifacts/sec_10k_item7_mda.md", format: md}
      10q_metadata:       {path: "artifacts/sec_10q_metadata.json", format: json}
      10q_item2_mda:      {path: "artifacts/sec_10q_item2_mda.md", format: md}
      10q_fin_tables:     {path: "artifacts/sec_10q_financial_tables.csv", format: csv}
      income_annual:      {path: "artifacts/sec_income_annual.csv", format: csv}
      income_quarterly:   {path: "artifacts/sec_income_quarterly.csv", format: csv}
      balance_annual:     {path: "artifacts/sec_balance_annual.csv", format: csv}
      balance_quarterly:  {path: "artifacts/sec_balance_quarterly.csv", format: csv}
      cashflow_annual:    {path: "artifacts/sec_cashflow_annual.csv", format: csv}
      cashflow_quarterly: {path: "artifacts/sec_cashflow_quarterly.csv", format: csv}
      8k_summary:         {path: "artifacts/sec_8k_summary.json", format: json}

  wikipedia:
    description: Fetch Wikipedia company summary
    type: skill
    command: wikipedia
    depends_on: [profile]
    params:
      script: skills/fetch_wikipedia/fetch_wikipedia.py
      args: {ticker: "${ticker}", workdir: "${workdir}"}
    outputs:
      wikipedia_summary: {path: "artifacts/wikipedia_summary.txt", format: txt}

  analysis:
    description: Generate business model, competitive, risk, and investment analysis via Perplexity
    type: skill
    command: analysis
    depends_on: [profile]
    params:
      script: skills/fetch_analysis/fetch_analysis.py
      args: {ticker: "${ticker}", workdir: "${workdir}"}
    outputs:
      business_model: {path: "artifacts/business_model_analysis.md", format: md}
      competitive:    {path: "artifacts/competitive_analysis.md", format: md}
      risk:           {path: "artifacts/risk_analysis.md", format: md}
      investment:     {path: "artifacts/investment_thesis.md", format: md}

  # --- Body writing tasks (Claude Code subagents with critic-optimizer) ---
  write_fundamental_analysis:
    skill: subagent:writer
    params:
      title: "Fundamental Analysis"
      guidelines: "Use tables for financials. Highlight YoY changes. Compare to peer medians."
      reads_from: [fundamental, technical]
    depends_on: [fundamental]
    outputs:
      section: {path: "artifacts/01_fundamental_analysis.md", format: md}

  write_company_profile:
    skill: subagent:writer
    depends_on: [perplexity, wikipedia, sec_edgar]
    params:
      title: "Company Profile"
      guidelines: "Focus on origin story, history, milestones, description of current operations"
      reads_from: [perplexity, wikipedia, sec_edgar]
    outputs:
      section: {path: "artifacts/02_company_profile.md", format: md}

  write_business_model:
    skill: subagent:writer
    depends_on: [perplexity, wikipedia, sec_edgar]
    params:
      title: "Business Model"
      guidelines: "Focus on what makes money and why. Revenue segments. Competitive moat."
      reads_from: [perplexity, wikipedia, sec_edgar]
    outputs:
      section: {path: "artifacts/03_business_model.md", format: md}

  write_competitive_landscape:
    skill: subagent:writer
    depends_on: [analysis, fundamental]
    params:
      title: "Competitive Landscape"
      guidelines: "Peer comparison table. Market share. Differentiation."
      reads_from: [analysis, fundamental]
    outputs:
      section: {path: "artifacts/04_competitive_landscape.md", format: md}

  write_supply_chain:
    skill: subagent:writer
    depends_on: [perplexity, wikipedia, sec_edgar]
    params:
      title: "Supply Chain"
      guidelines: "Key suppliers, dependencies, geographic exposure, logistics."
      reads_from: [perplexity, wikipedia, sec_edgar]
    outputs:
      section: {path: "artifacts/05_supply_chain.md", format: md}

  write_leverage:
    skill: subagent:writer
    depends_on: [fundamental, sec_edgar]
    params:
      title: "Financial and Operating Leverage"
      guidelines: "Sensitivity to changes in interest rates, economic operating environment, input/output prices"
      reads_from: [fundamental, sec_edgar]
    outputs:
      section: {path: "artifacts/06_leverage.md", format: md}

  write_valuation:
    skill: subagent:writer
    depends_on: [fundamental, analysis]
    params:
      title: "Valuation"
      guidelines: "Appropriate valuation methodologies, metrics under them, peer comparisons"
      reads_from: [fundamental, analysis]
    outputs:
      section: {path: "artifacts/07_valuation.md", format: md}

  write_news:
    skill: subagent:writer
    depends_on: [perplexity]
    params:
      title: "Recent Developments"
      guidelines: "Recent news and market developments, exec changes, rating changes"
      reads_from: [perplexity]
    outputs:
      section: {path: "artifacts/08_news.md", format: md}

  write_risks:
    skill: subagent:writer
    depends_on: [analysis, sec_edgar]
    params:
      title: "Risk Analysis"
      guidelines: "Be specific with numbers. Categorize: operational, financial, regulatory, market."
      reads_from: [analysis, sec_edgar]
    outputs:
      section: {path: "artifacts/09_risks.md", format: md}

  write_thesis:
    skill: subagent:writer
    depends_on: [analysis]
    params:
      title: "Investment Thesis & SWOT"
      guidelines: "Bull case, bear case, base case with price implications. SWOT table."
      reads_from: [analysis]
    outputs:
      section: {path: "artifacts/10_thesis.md", format: md}

  # --- Bookend writing tasks (depend on body sections) ---
  write_executive_summary:
    skill: subagent:writer
    params:
      title: "Executive Summary"
      guidelines: "Max 300 words. Investment stance in first sentence. Key metrics. Why now."
      reads_from: [profile, technical, fundamental, perplexity, analysis,
                   write_fundamental_analysis, write_company_profile,
                   write_business_model, write_competitive_landscape,
                   write_supply_chain, write_leverage, write_valuation,
                   write_news, write_risks, write_thesis]
    depends_on: [write_fundamental_analysis, write_company_profile,
                 write_business_model, write_competitive_landscape,
                 write_supply_chain, write_leverage, write_valuation,
                 write_news, write_risks, write_thesis]
    outputs:
      section: {path: "artifacts/00_executive_summary.md", format: md}

  write_conclusion:
    skill: subagent:writer
    params:
      title: "Conclusion & Recommendation"
      guidelines: "Synthesize across sections. Clear recommendation. Key watchpoints. Catalysts."
      reads_from: [write_fundamental_analysis, write_company_profile,
                   write_business_model, write_competitive_landscape,
                   write_supply_chain, write_leverage, write_valuation,
                   write_news, write_risks, write_thesis]
    depends_on: [write_fundamental_analysis, write_company_profile,
                 write_business_model, write_competitive_landscape,
                 write_supply_chain, write_leverage, write_valuation,
                 write_news, write_risks, write_thesis]
    outputs:
      section: {path: "artifacts/11_conclusion.md", format: md}

  # --- Assembly + Polish ---
  assembly:
    skill: script:assemble
    params:
      script: skills/assemble.py
      args: {template: "templates/equity_research_report.md.j2", workdir: "${workdir}"}
    depends_on: [write_executive_summary, write_conclusion]
    outputs:
      report: {path: "artifacts/research_report.md", format: md}

  polish:
    skill: subagent:polish
    params:
      reads_from: [assembly]
    depends_on: [assembly]
    outputs:
      final_report: {path: "artifacts/final_report.md", format: md}
```

### DAG Customization at Intake

During the interactive intake phase, the user can:
- **Remove tasks** — and any tasks that depend on them are also removed or marked skipped
- **Add tasks** — e.g. add an ESG analysis section with appropriate deps
- **Edit params** — change guidelines, add reads_from sources
- **Reorder outputs** — affects Jinja assembly order

When user chooses "edit" at intake, they interact conversationally:

- **Remove tasks:** "remove sec_edgar, wikipedia" — removes tasks and marks dependents for skip
- **Edit guidelines:** "change write_risks guidelines to: Focus on regulatory risk only"
- **Add tasks:** "add write_esg after analysis with guidelines: ESG scoring and sustainability"

The modified DAG is saved to `work/{SYMBOL}_{DATE}/dag.yaml` and used for execution.

---

## 4. DAG Runner Algorithm

The `/research` skill runs four phases:

### Phase 1: INTAKE

1. Parse arguments: ticker (required), dag_file (default: `dags/sra.yaml`)
2. Validate ticker (use `lookup_ticker.py` if needed)
3. Create work directory: `work/{TICKER}_{YYYYMMDD}/`
4. Read DAG YAML and present to user:

```
Equity Research Report for TSLA

Tasks (16):
  profile          → script       (no deps)
  technical        → script       (no deps)
  fundamental      → script       (depends: profile)
  perplexity       → script       (depends: profile)
  sec_edgar        → script       (depends: profile)
  wikipedia        → script       (depends: profile)
  analysis         → script       (depends: profile)
  write_fundamental_analysis → writer (depends: fundamental)
  ...
  assembly         → assemble     (depends: write_executive_summary, write_conclusion)
  polish           → polish       (depends: assembly)

Proceed? [Y/n/edit]
```

5. User confirms, edits (see DAG Editing below), or cancels
6. Save working DAG to `work/{TICKER}_{DATE}/dag.yaml`

### Phase 2: INIT

```bash
./skills/db.py init --workdir {workdir} --dag {dag_file} --ticker {ticker} --date {date}
./skills/db.py research-update --workdir {workdir} --status running
```

### Phase 3: DAG LOOP

```
repeat:
    ready = ./skills/db.py task-ready --workdir {workdir}

    if ready is empty:
        status = ./skills/db.py status --workdir {workdir}
        if all tasks complete/skipped/failed:
            → set research.status = 'complete', break
        else:
            → deadlock detected (see Error Handling), set research.status = 'failed', break

    dispatch all ready tasks in parallel:
        for each task in ready:
            spawn /taskrunner {task.id} {workdir} as background subagent

    wait for all subagents to complete

    check for stale running tasks (taskrunner crash/timeout):
        if any tasks still in 'running' → retry once, then mark failed

    print iteration summary:
        Iteration N complete: K tasks finished
          ✓ fundamental  — 6 artifacts, market cap $892B
          ✓ perplexity   — 3 artifacts, 12 news stories
          ✗ sec_edgar    — FAILED: SEC EDGAR timeout

        Next ready: write_fundamental_analysis, write_company_profile, ...
```

### Phase 4: COMPLETION

```
print final summary:
    Research complete for TSLA

    Status: 15/16 tasks complete, 1 failed

    Outputs:
      - work/TSLA_20260222/artifacts/research_report.md (assembled)
      - work/TSLA_20260222/artifacts/final_report.md (polished)

    Failed tasks:
      - sec_edgar: SEC EDGAR timeout

    Run db.py status --workdir work/TSLA_20260222 for full details
```

```bash
./skills/db.py research-update --workdir {workdir} --status complete
```

---

## 5. Taskrunner Skill

The `/taskrunner` skill is dispatched as a subagent with a task ID and workdir. It:

1. Reads task config: `db.py task-get --workdir {workdir} {task_id}`
2. Sets task to running: `db.py task-update --workdir {workdir} {task_id} --status running`
3. Dispatches based on skill type:

### skill: script

```
Run: cd {root_dir} && python {params.script} {ticker} --workdir {workdir}
```

Where args are converted to CLI flags: `{key: value}` becomes `--key value`.

> Each skill script calls `load_environment()` from `utils.py` at startup to self-load the project root `.env` file. The taskrunner does not need to pre-export environment variables.

After script completes:

1. Parse JSON manifest from stdout
2. For each artifact in manifest:
   ```bash
   db.py artifact-add --workdir {workdir} --task {task_id} --name {name} --path {path} --format {format} --source {source} --summary {summary}
   ```
3. Update task status based on manifest status and exit code:
   - Exit 0 + status "complete" → `--status complete`
   - Exit 1 + status "partial" → `--status complete` (with summary noting partial)
   - Exit 2 or other → `--status failed`

### skill: subagent:writer

The critic-optimizer loop. Taskrunner executes this directly (it IS a Claude Code agent):

**Step 1: GATHER**
- Read `params.reads_from` — list of task IDs whose artifacts to consume
- For each task in reads_from, query `db.py artifact-list --workdir {workdir} --task {task_id}`
- Read the artifact files from `{workdir}/artifacts/{filename}` (paths come from artifact-list)
- Also read task summaries for context

**Step 2: DRAFT**
- Write section based on gathered data + `params.guidelines`
- Use `params.title` as the section heading
- Save draft to `{workdir}/artifacts/{task_id}_draft.md`

**Step 3: CRITIQUE**
- Re-read draft against criteria:
  - Data accuracy, specificity, thesis clarity, completeness, conciseness
- Save critique to `{workdir}/artifacts/{task_id}_critique.md`

**Step 4: REVISE**
- Rewrite addressing critique points
- Save final to `{workdir}/{output_path}` (output path from DAG, e.g. `artifacts/02_company_profile.md`)
- Register artifact + update task status

### skill: subagent:polish

```
Read assembled report from reads_from task's artifact
Critique at document level: flow, consistency, tone, redundancy
Rewrite full report
Save to {workdir}/{output_path}
db.py artifact-add + task-update
```

### skill: script:assemble

Execution is identical to `script` — run the Python script, parse manifest, register artifacts. The `script:assemble` type is just a label distinction for clarity in the DAG.

---

## 6. db.py Utility

Thin CLI wrapper around `research.db`. Task-generic — no phase/section-specific commands.

```
./skills/db.py <command> --workdir <path> [command-specific args]
```

- `--workdir` is required on every command (no global state)
- All output is JSON to stdout; errors go to stderr
- Exit code 0 on success, 1 on error

### `init`

```bash
./skills/db.py init --workdir work/TSLA_20260222 \
  --dag dags/sra.yaml --ticker TSLA --date 20260222
```

Creates `{workdir}/research.db`, creates all tables, parses DAG YAML (substituting `${ticker}`, `${date}`, `${workdir}` in all string values recursively), inserts research row + tasks + task_deps.

```json
{"status": "ok", "tasks": 16, "workdir": "work/TSLA_20260222"}
```

### `task-ready`

```bash
./skills/db.py task-ready --workdir work/TSLA_20260222
```

Core DAG algorithm — returns tasks that are `pending` and whose dependencies are all `complete` or `skipped`:

```sql
SELECT t.id, t.skill, t.params, t.description
FROM tasks t
WHERE t.status = 'pending'
AND NOT EXISTS (
    SELECT 1 FROM task_deps d
    JOIN tasks dep ON d.depends_on = dep.id
    WHERE d.task_id = t.id
    AND dep.status NOT IN ('complete', 'skipped')
)
```

```json
[
  {"id": "technical", "skill": "script", "description": "...", "params": {...}},
  {"id": "profile", "skill": "script", "description": "...", "params": {...}}
]
```

Returns empty array `[]` when no tasks are ready.

### `task-get`

```bash
./skills/db.py task-get --workdir work/TSLA_20260222 technical
```

```json
{
  "id": "technical",
  "skill": "script",
  "description": "...",
  "params": {"script": "skills/fetch_technical/fetch_technical.py", "args": {...}},
  "status": "pending",
  "depends_on": [],
  "artifact_count": 0,
  "summary": null,
  "error": null
}
```

### `task-update`

```bash
./skills/db.py task-update --workdir work/TSLA_20260222 \
  technical --status complete --summary "3 artifacts, 12 peers identified"

./skills/db.py task-update --workdir work/TSLA_20260222 \
  sec_edgar --status failed --error "SEC EDGAR timeout"
```

Sets `started_at` when status becomes `running`, `completed_at` when status becomes `complete`/`failed`/`skipped`. Also updates `research.updated_at`.

```json
{"status": "ok", "task": "technical", "new_status": "complete"}
```

### `artifact-add`

```bash
./skills/db.py artifact-add --workdir work/TSLA_20260222 \
  --task technical --name chart --path artifacts/chart.png \
  --format png --source plotly+yfinance \
  --summary "4yr weekly candlestick, MA13/MA52, RSI, volume"
```

Registers an artifact. Computes `size_bytes` from the file if it exists at `{workdir}/{path}`.

```json
{"status": "ok", "artifact_id": 1, "task": "technical", "name": "chart"}
```

### `artifact-list`

```bash
./skills/db.py artifact-list --workdir work/TSLA_20260222
./skills/db.py artifact-list --workdir work/TSLA_20260222 --task fundamental
```

```json
[
  {"id": 1, "task_id": "technical", "name": "chart", "path": "artifacts/chart.png", "format": "png", "source": "plotly+yfinance", "summary": "...", "size_bytes": 45000}
]
```

### `status`

```bash
./skills/db.py status --workdir work/TSLA_20260222
```

```json
{
  "research": {"ticker": "TSLA", "status": "running", "created_at": "..."},
  "tasks": {
    "total": 16, "pending": 6, "running": 0,
    "complete": 9, "failed": 1, "skipped": 0
  },
  "task_details": [
    {"id": "technical", "status": "complete", "artifact_count": 3, "summary": "..."},
    {"id": "sec_edgar", "status": "failed", "error": "SEC EDGAR timeout"}
  ],
  "artifacts": {"total": 24}
}
```

### `research-update`

```bash
./skills/db.py research-update --workdir work/TSLA_20260222 --status running
./skills/db.py research-update --workdir work/TSLA_20260222 --status complete
```

Updates the `research.status` field. Used by the DAG runner to track overall pipeline state.

### Error handling rules

- If `--workdir` doesn't exist: create it (for `init`), error for other commands
- If `research.db` doesn't exist for non-init commands: error with "run init first"
- If `task_id` doesn't exist: error with message
- If artifact path doesn't exist on disk: still register it (`size_bytes` = null), log warning
- Duplicate `artifact-add` (same task + name): update existing row

### Design decisions

- `--workdir` on every call — no global state, no config files, stateless CLI
- JSON output everywhere — easy for Claude Code subagents to parse
- `init` reads DAG YAML and populates all tables — tasks, deps, expected artifacts
- Variable substitution in `init` — `${ticker}`, `${date}`, `${workdir}` replaced at init time, stored expanded in db
- No expected artifacts table — outputs in YAML are documentation; artifacts table tracks what was actually produced
- `task-ready` is the core algorithm — everything else is CRUD
- No dependencies beyond stdlib (`sqlite3`, `json`, `argparse`, `pathlib`, `yaml` via PyYAML)

---

## 7. Critic-Optimizer Loop

Each `subagent:writer` task runs a 3-step loop within the `/taskrunner` skill:

```
1. GATHER
   Query artifact summaries for tasks listed in reads_from
   Read relevant data files
   (bookend tasks also read completed section artifacts from body writer tasks)

2. DRAFT
   Write section markdown
   Save to {workdir}/artifacts/{task_id}_draft.md

3. CRITIQUE
   Re-read the draft against these criteria:
   - Data accuracy: does every claim trace to a specific artifact?
   - Specificity: concrete numbers, not vague assertions?
   - Thesis clarity: clear analytical point, not just description?
   - Completeness: anything important from the data left out?
   - Conciseness: anything redundant or filler?
   Save to {workdir}/artifacts/{task_id}_critique.md

4. REVISE
   Rewrite addressing every critique point
   Save final to the numbered output path from the DAG (e.g. {workdir}/artifacts/02_company_profile.md)
   Register as artifact, update task status
```

### Section-Specific Guidelines

Defined in DAG YAML per task under `params.guidelines`. Examples:

| Section | Key Guidelines |
|---------|---------------|
| Fundamental Analysis | Use tables for financial data. Calculate and highlight YoY changes. Flag anomalies. |
| Company Profile | Focus on origin story, history, milestones, description of current operations |
| Business Model | Focus on what makes money and why. Revenue segments. Competitive moat. |
| Competitive Landscape | Peer comparison table. Market share. Differentiation. |
| Supply Chain | Key suppliers, dependencies, geographic exposure, logistics. |
| Leverage | Sensitivity to changes in interest rates, economic operating environment, input/output prices |
| Valuation | Appropriate valuation methodologies, metrics under them, peer comparisons |
| News | Recent news and market developments, exec changes, rating changes |
| Risks | Be specific — "revenue concentration: 48% from X" not "concentration risk exists" |
| Thesis | Bull case, bear case, base case. SWOT table. Price implications. |
| Executive Summary | Max 300 words. Investment stance in first sentence. Key metrics. |
| Conclusion | Synthesize across sections. Clear recommendation. Key watchpoints. |

### Final Polish

The `polish` task reads the assembled report and critiques at the document level:
- **Flow:** Do sections connect logically? Contradictions?
- **Consistency:** Same numbers cited the same way throughout?
- **Tone:** Professional analyst voice, not marketing copy?
- **Redundancy:** Same point in multiple sections?

Then rewrites the full report.

---

## 8. Error Handling

### Principle: Degrade Gracefully, Never Silently

Every failure is recorded in `tasks.error`. The DAG runner continues with what it has.

### Task Failures

```
Task fails (script exits non-zero, subagent errors)
  → taskrunner sets: tasks.status = 'failed', tasks.error = message
  → DAG runner continues to next iteration
  → downstream tasks with failed dependency:
    → if ALL required deps failed → mark as 'skipped'
    → if SOME deps available → taskrunner works with reduced data
```

### Partial Script Success

Scripts exit 1 for partial success. Manifest lists whatever artifacts were produced. The task is marked `complete` with a summary noting what's missing. Downstream writer tasks see what's available and work with it.

### Taskrunner Subagent Failures (Stale Running Tasks)

If a taskrunner subagent crashes or times out:
- Task stays in `running` status (no terminal status was set)
- After waiting for subagents each iteration, the DAG runner checks for tasks still in `running` status
- These indicate taskrunner crashes or timeouts
- Retry once: re-dispatch a new `/taskrunner` subagent for the stale task
- If retry also fails, mark as `failed`
- DAG continues, skipping dependents if necessary

### Deadlock Detection

If `task-ready` returns an empty array but not all tasks are in a terminal state (`complete`/`failed`/`skipped`):
- This is a deadlock — tasks exist that can never become ready
- Print which tasks are stuck and their unsatisfied dependencies
- Set `research.status` to `failed`

### User Abort

If the user interrupts (Ctrl+C):
- Print current status summary
- Tasks already dispatched will continue running in their background subagents
- User can resume by re-running `/research` with the same workdir (future: init detects existing db and resumes)

### Timeouts

| Task type | Timeout | Rationale |
|-----------|---------|-----------|
| script (data gathering) | 5 min | API calls + fallback chains |
| subagent:writer | 3 min | Draft + critique + revise |
| script:assemble | 1 min | Jinja is fast |
| subagent:polish | 5 min | Full report critique + rewrite |

### Status Reporting

After each DAG iteration, the runner prints a summary:

```
Iteration 2 complete: 5 tasks finished
  ✓ fundamental  — 6 artifacts, market cap $892B
  ✓ perplexity   — 3 artifacts, 12 news stories
  ✗ sec_edgar    — FAILED: SEC EDGAR timeout
  ✓ wikipedia    — 1 artifact
  ✓ analysis     — 4 artifacts

Next ready: write_fundamental_analysis, write_company_profile (reduced data: no 10-K),
  write_business_model, write_competitive_landscape, write_supply_chain,
  write_leverage, write_valuation, write_news, write_risks, write_thesis
```

---

## 9. Script Migration

### Keep (with manifest changes)

| Script | Changes |
|--------|---------|
| `fetch_technical/fetch_technical.py` | Add JSON manifest stdout. Remove status printing. |
| `fetch_fundamental/fetch_fundamental.py` | Add manifest. Accept `--peers-file` flag. |
| `fetch_perplexity/fetch_perplexity.py` | Add manifest. Summary should capture key facts. |
| `fetch_edgar/fetch_edgar.py` | Add manifest. Summary: filing date, word count, topics. |
| `fetch_wikipedia/fetch_wikipedia.py` | Add manifest. Minimal changes. |
| `fetch_analysis/fetch_analysis.py` | Add manifest. Accept `--workdir`, discover artifacts. |
| `lookup_ticker.py` | No changes needed. |
| `config.py` | No changes needed. |
| `utils.py` | No changes needed. |

### Python Script Contract

Every data-fetching script follows a uniform interface:

```bash
./skills/fetch_technical/fetch_technical.py TSLA --workdir work/TSLA_20260222
```

**Exit codes:** 0 (success), 1 (partial — some data missing), 2 (failure)

**Stdout:** JSON manifest describing what was produced:

```json
{
  "status": "complete",
  "artifacts": [
    {
      "name": "profile",
      "path": "artifacts/profile.json",
      "format": "json",
      "source": "yfinance",
      "summary": "TSLA market cap $892B, P/E 64.2, sector: Consumer Cyclical"
    }
  ],
  "error": null
}
```

### Remove

| Script | Replaced By |
|--------|-------------|
| `research_stock.py` | `/research` skill (DAG runner) |
| `research_report.py` | `subagent:writer` tasks + assembly |
| `research_final.py` | `subagent:polish` task |
| `research_deep.py` | `subagent:writer` tasks (they ARE Claude) |

### Add

| File | Purpose |
|------|---------|
| `skills/db.py` | SQLite CLI utility — init, task-ready, task-update, artifact-add/list, status |
| `skills/assemble.py` | Read section artifacts from db, run Jinja template, write assembled report |
| `skills/research.md` | Claude Code skill: intake + DAG runner loop |
| `skills/taskrunner.md` | Claude Code skill: dispatch a single task by skill type |
| `dags/sra.yaml` | Default DAG for equity research reports |

---

## 10. Script-Specific Specs

Detailed specifications for each data-fetching script are in separate files:

| Spec | Script |
|------|--------|
| `SPEC_PROFILE.md` | `skills/fetch_profile/fetch_profile.py` |
| `SPEC_TECHNICAL.md` | `skills/fetch_technical/fetch_technical.py` |
| `SPEC_FUNDAMENTAL.md` | `skills/fetch_fundamental/fetch_fundamental.py` |
| `SPEC_PERPLEXITY.md` | `skills/fetch_perplexity/fetch_perplexity.py` |
| `SPEC_EDGAR.md` | `skills/fetch_edgar/fetch_edgar.py` |
| `SPEC_WIKIPEDIA.md` | `skills/fetch_wikipedia/fetch_wikipedia.py` |
| `SPEC_ANALYSIS.md` | `skills/fetch_analysis/fetch_analysis.py` |
| `SPEC_ASSEMBLE.md` | `skills/assemble.py` |

These cover script-specific APIs, data sources, fallback chains, and output formats. The core architecture (db.py, DAG runner, taskrunner) is fully documented in this file.
