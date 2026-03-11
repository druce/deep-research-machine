# Custom Investigation Prompts Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users enter custom investigation prompts before the pipeline runs, execute them in parallel as Claude subprocesses, and feed results into the existing chunk/index pipeline.

**Architecture:** Pre-flight interactive loop in `research.py` collects prompts to `custom_prompts.json`. A new Python DAG task `custom_research` (sort_order 8, depends on profile+peers) reads those prompts, runs each via `invoke_claude` in parallel, auto-tags responses for section relevance, and saves artifacts. `chunk_documents` picks them up via an updated `depends_on`.

**Tech Stack:** Python 3, asyncio, `invoke_claude` from `utils.py`, existing DAG/DB infrastructure

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `skills/custom_research/custom_research.py` | Create | Main script: read prompts, run Claude in parallel, auto-tag, emit manifest |
| `skills/custom_research/__init__.py` | Create | Empty package marker |
| `research.py` | Modify | Add interactive prompt collection before DAG init |
| `dags/sra.yaml` | Modify | Add `custom_research` task, update `chunk_documents` deps |
| `CLAUDE.md` | Modify | Document `custom_research` in architecture and key files sections |

---

### Task 1: Create `custom_research.py` script

**Files:**
- Create: `skills/custom_research/__init__.py`
- Create: `skills/custom_research/custom_research.py`
- Reference: `skills/fetch_detailed_profile_info/fetch_detailed_profile_info.py` (pattern to follow)
- Reference: `skills/utils.py:395-668` (`invoke_claude` signature and behavior)

- [ ] **Step 1: Create directory and empty `__init__.py`**

```bash
mkdir -p skills/custom_research
touch skills/custom_research/__init__.py
```

- [ ] **Step 2: Write `custom_research.py`**

Create `skills/custom_research/custom_research.py` following the `fetch_detailed_profile_info.py` pattern. The script should:

```python
#!/usr/bin/env python3
"""
Custom Research — Run user-provided investigation prompts via Claude.

Reads custom_prompts.json from the workdir, runs each prompt as a parallel
Claude subprocess with web search, auto-tags each response for section
relevance, and emits a JSON manifest on stdout.

Usage:
    ./skills/custom_research/custom_research.py SYMBOL --workdir DIR

Exit codes:
    0  All prompts succeeded (or no prompts to run)
    1  Partial success (at least one prompt succeeded)
    2  Complete failure
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

from utils import (  # noqa: E402
    setup_logging,
    validate_symbol,
    ensure_directory,
    load_environment,
    default_workdir,
    invoke_claude,
)

load_environment()
logger = setup_logging(__name__)


SECTION_TAGS = [
    "profile", "business_model", "competitive",
    "supply_chain", "financial", "valuation", "risk_news",
]

SYSTEM_PROMPT = (
    "You are a financial research analyst investigating a public company. "
    "Use web search to find current, factual data. Cite sources with specific "
    "numbers, dates, and data points. Write in Markdown. "
    "Save your output to the file path specified at the end of the prompt."
)

TAG_PROMPT_TEMPLATE = """Read the file at {response_path} and classify which of these report sections it is relevant to:

{tags_list}

A response may be relevant to multiple sections. Be generous — it's better to over-tag than under-tag.

Return ONLY a JSON array of matching tag strings, e.g.: ["financial", "risk_news", "valuation"]

Write the result to {tag_output_path}
"""


def _get_mcp_config(workdir: Path) -> list[str] | None:
    """Return MCP config paths if mcp-research.json exists in workdir."""
    mcp_path = workdir / "mcp-research.json"
    if mcp_path.exists():
        return [str(mcp_path)]
    return None


def get_company_name(symbol: str, workdir: Path) -> str:
    """Resolve company name from profile.json or fall back to symbol."""
    profile_path = workdir / "artifacts" / "profile.json"
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text())
            name = profile.get("company_name")
            if name and name != "N/A":
                return name
        except (json.JSONDecodeError, OSError):
            pass
    return symbol


async def run_prompt(
    idx: int,
    prompt_text: str,
    company: str,
    symbol: str,
    workdir: Path,
) -> dict:
    """Run a single custom prompt via invoke_claude. Return result dict."""
    prompt_id = f"custom_{idx}"
    output_path = f"artifacts/custom_research_{idx}.md"

    full_prompt = (
        f"Research the following question about {company} ({symbol}):\n\n"
        f"{prompt_text}\n\n"
        "Be thorough. Include specific data, dates, and sources."
    )

    result = await invoke_claude(
        prompt=full_prompt,
        workdir=workdir,
        task_id="custom_research",
        step_label=f"prompt_{idx}",
        system=SYSTEM_PROMPT,
        expected_outputs={
            prompt_id: {"path": output_path, "format": "md"},
        },
        mcp_config=_get_mcp_config(workdir),
    )

    return {
        "idx": idx,
        "prompt_id": prompt_id,
        "output_path": output_path,
        "status": result["status"],
        "error": result.get("error"),
        "artifacts": result.get("artifacts", []),
    }


async def tag_response(idx: int, workdir: Path) -> list[str]:
    """Auto-tag a custom research response for section relevance. Return list of tags."""
    response_path = f"artifacts/custom_research_{idx}.md"
    tag_output_path = f"artifacts/custom_research_{idx}_tags.json"
    tags_list = "\n".join(f"- {t}" for t in SECTION_TAGS)

    prompt = TAG_PROMPT_TEMPLATE.format(
        response_path=response_path,
        tags_list=tags_list,
        tag_output_path=tag_output_path,
    )

    result = await invoke_claude(
        prompt=prompt,
        workdir=workdir,
        task_id="custom_research",
        step_label=f"tag_{idx}",
        disallowed_tools=["WebSearch", "WebFetch"],
        expected_outputs={
            f"tags_{idx}": {"path": tag_output_path, "format": "json"},
        },
    )

    if result["status"] == "complete":
        tag_file = workdir / tag_output_path
        if tag_file.exists():
            try:
                tags = json.loads(tag_file.read_text())
                if isinstance(tags, list):
                    return [t for t in tags if t in SECTION_TAGS]
            except (json.JSONDecodeError, OSError):
                pass

    return []


async def run_all(symbol: str, workdir: Path) -> int:
    """Main async entry point. Returns exit code."""
    workdir = Path(workdir)
    ensure_directory(workdir / "artifacts")

    # Read custom prompts
    prompts_file = workdir / "custom_prompts.json"
    if not prompts_file.exists():
        logger.info("No custom_prompts.json found — skipping")
        print(json.dumps({"status": "complete", "artifacts": [], "error": None}))
        return 0

    prompts = json.loads(prompts_file.read_text())
    if not prompts:
        logger.info("custom_prompts.json is empty — skipping")
        print(json.dumps({"status": "complete", "artifacts": [], "error": None}))
        return 0

    company = get_company_name(symbol, workdir)
    logger.info("Running %d custom prompts for %s (%s)", len(prompts), company, symbol)

    # Phase 1: Run all prompts in parallel
    coros = [
        run_prompt(i + 1, p["prompt"], company, symbol, workdir)
        for i, p in enumerate(prompts)
    ]
    results = await asyncio.gather(*coros)

    succeeded = [r for r in results if r["status"] == "complete"]
    failed = [r for r in results if r["status"] != "complete"]

    for f in failed:
        logger.error("Prompt %d failed: %s", f["idx"], f["error"])

    if not succeeded:
        logger.error("All %d custom prompts failed", len(prompts))
        print(json.dumps({
            "status": "failed",
            "artifacts": [],
            "error": f"All {len(prompts)} custom prompts failed",
        }))
        return 2

    # Phase 2: Auto-tag all successful responses in parallel
    logger.info("Auto-tagging %d responses", len(succeeded))
    tag_coros = [tag_response(r["idx"], workdir) for r in succeeded]
    tag_results = await asyncio.gather(*tag_coros)

    # Build combined tags metadata
    tags_metadata = []
    all_artifacts = []

    for result, tags in zip(succeeded, tag_results):
        tags_metadata.append({
            "id": result["prompt_id"],
            "file": result["output_path"],
            "tags": tags,
        })
        all_artifacts.extend(result["artifacts"])

    # Write combined tags file
    tags_file = workdir / "artifacts" / "custom_research_tags.json"
    tags_file.write_text(json.dumps(tags_metadata, indent=2))
    all_artifacts.append({
        "name": "custom_research_tags",
        "path": "artifacts/custom_research_tags.json",
        "format": "json",
    })

    # Clean up individual tag files
    for r in succeeded:
        tag_file = workdir / f"artifacts/custom_research_{r['idx']}_tags.json"
        if tag_file.exists():
            tag_file.unlink()

    logger.info(
        "Custom research complete: %d/%d succeeded",
        len(succeeded), len(prompts),
    )

    print(json.dumps({
        "status": "complete",
        "artifacts": all_artifacts,
        "error": None,
    }))

    if failed:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run custom investigation prompts")
    parser.add_argument("ticker", help="Stock ticker symbol")
    parser.add_argument("--workdir", default=None, help="Working directory")
    args = parser.parse_args()

    symbol = validate_symbol(args.ticker)
    workdir = args.workdir or default_workdir(symbol)

    return asyncio.run(run_all(symbol, workdir))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Make script executable**

```bash
chmod +x skills/custom_research/custom_research.py
```

- [ ] **Step 4: Verify script loads without errors**

Run: `uv run python skills/custom_research/custom_research.py --help`
Expected: argparse help output with `ticker` and `--workdir` args

- [ ] **Step 5: Commit**

```bash
git add skills/custom_research/
git commit -m "feat: add custom_research script for user investigation prompts"
```

---

### Task 2: Add interactive prompt collection to `research.py`

**Files:**
- Modify: `research.py:485-502` (`init_pipeline` function) and `research.py:639-676` (`main` function)

- [ ] **Step 1: Add `collect_custom_prompts` function to `research.py`**

Add after the `hydrate_mcp_configs` function (around line 83), before `log`:

```python
def collect_custom_prompts(workdir: Path) -> None:
    """Interactively collect custom investigation prompts from the user."""
    prompts_file = workdir / "custom_prompts.json"
    if prompts_file.exists():
        log(f"Custom prompts already exist at {prompts_file} — skipping collection")
        return

    print("\nCustom investigation prompts (enter empty line to finish):", file=sys.stderr)
    prompts = []
    idx = 1
    while True:
        try:
            line = input(f"[{idx}]> ").strip()
        except EOFError:
            break
        if not line:
            break
        prompts.append({"id": f"custom_{idx}", "prompt": line})
        idx += 1

    workdir.mkdir(parents=True, exist_ok=True)
    prompts_file.write_text(json.dumps(prompts, indent=2))
    if prompts:
        log(f"Saved {len(prompts)} custom prompts to {prompts_file}")
    else:
        log("No custom prompts entered — task will be a no-op")
```

- [ ] **Step 2: Call `collect_custom_prompts` in the `main` function**

In the `main` function, add the call after workdir is created but before the DAG execution loop. Insert after `hydrate_mcp_configs(workdir)` (line 680) and before the `wave = 0` line (line 682):

```python
    # Collect custom investigation prompts (interactive, skip on resume)
    if not args.resume:
        collect_custom_prompts(workdir)
```

- [ ] **Step 3: Test prompt collection in isolation**

Write a quick inline test (don't commit — just verify behavior):

```bash
python3 -c "
import sys, json
from pathlib import Path
sys.path.insert(0, '.')
from research import collect_custom_prompts
workdir = Path('work/TEST_prompts')
workdir.mkdir(parents=True, exist_ok=True)
collect_custom_prompts(workdir)
print(json.loads((workdir / 'custom_prompts.json').read_text()))
" <<< $'What is the AI strategy?\nHow exposed to China?\n'
```

Expected: prints list with 2 prompt dicts

- [ ] **Step 4: Test with no prompts (empty input)**

```bash
python3 -c "
import sys, json
from pathlib import Path
sys.path.insert(0, '.')
from research import collect_custom_prompts
workdir = Path('work/TEST_prompts_empty')
workdir.mkdir(parents=True, exist_ok=True)
collect_custom_prompts(workdir)
print(json.loads((workdir / 'custom_prompts.json').read_text()))
" <<< ''
```

Expected: `[]`

Clean up: `rm -rf work/TEST_prompts work/TEST_prompts_empty`

- [ ] **Step 5: Commit**

```bash
git add research.py
git commit -m "feat: interactive custom prompt collection before pipeline launch"
```

---

### Task 3: Add `custom_research` task to DAG and update `chunk_documents` deps

**Files:**
- Modify: `dags/sra.yaml:125-161` (between `wikipedia` and `chunk_documents`)

- [ ] **Step 1: Add `custom_research` task to `dags/sra.yaml`**

Insert after the `wikipedia` task block (after line 137) and before the chunk section comment:

```yaml
  custom_research:
    sort_order: 8
    description: Run user-provided custom investigation prompts via Claude
    type: python
    depends_on: [profile, peers]
    config:
      script: skills/custom_research/custom_research.py
      args:
        ticker: "${ticker}"
        workdir: "${workdir}"
    outputs:
      custom_research_tags: {path: "artifacts/custom_research_tags.json", format: json, description: "Section relevance tags for each custom research response"}
```

Note: Individual `custom_research_N.md` artifacts are registered dynamically by the script's manifest output. Only the tags file is declared as a static output.

- [ ] **Step 2: Update `chunk_documents` depends_on to include `custom_research`**

Change line 161 from:
```yaml
    depends_on: [technical, fundamental, detailed_profile, fetch_edgar, wikipedia, detailed_profile]
```
to:
```yaml
    depends_on: [technical, fundamental, detailed_profile, fetch_edgar, wikipedia, custom_research]
```

This also fixes the duplicate `detailed_profile` entry.

- [ ] **Step 3: Validate DAG**

Run: `uv run python skills/db.py validate --dag dags/sra.yaml --ticker TEST`
Expected: Validation passes, task count increases by 1

- [ ] **Step 4: Commit**

```bash
git add dags/sra.yaml
git commit -m "feat: add custom_research DAG task, update chunk_documents deps"
```

---

### Task 4: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add `custom_research` to the Key Files table**

In the Key Files table (after the `skills/fetch_wikipedia/` row), add:

```markdown
| `skills/custom_research/` | Run user-provided investigation prompts via parallel Claude subprocesses |
```

- [ ] **Step 2: Add to DAG execution order**

In the "DAG execution order" list, update item 2 to include `custom_research`:

```markdown
2. `technical`, `fundamental`, `fetch_edgar`, `wikipedia`, `custom_research` (depend on profile/peers)
```

- [ ] **Step 3: Add to Commands section**

In the "Run individual Python skills" section, add:

```bash
./skills/custom_research/custom_research.py SYMBOL --workdir work/SYMBOL_DATE
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add custom_research to CLAUDE.md"
```

---

### Task 5: End-to-end smoke test

- [ ] **Step 1: Initialize a test workdir and verify custom_research runs as no-op**

```bash
# Init with no custom prompts
uv run python skills/db.py init --workdir work/TEST_smoke --dag dags/sra.yaml --ticker TEST
echo '[]' > work/TEST_smoke/custom_prompts.json
uv run python skills/custom_research/custom_research.py TEST --workdir work/TEST_smoke
```

Expected: stdout is `{"status": "complete", "artifacts": [], "error": null}`

- [ ] **Step 2: Test with a real prompt (requires Claude CLI)**

```bash
echo '[{"id": "custom_1", "prompt": "What are the main revenue segments?"}]' > work/TEST_smoke/custom_prompts.json
mkdir -p work/TEST_smoke/artifacts
echo '{"company_name": "Test Corp", "symbol": "TEST"}' > work/TEST_smoke/artifacts/profile.json
uv run python skills/custom_research/custom_research.py TEST --workdir work/TEST_smoke
```

Expected: `artifacts/custom_research_1.md` created, `artifacts/custom_research_tags.json` created with tag array, stdout manifest shows artifacts

- [ ] **Step 3: Clean up test workdirs**

```bash
rm -rf work/TEST_smoke work/TEST_* work/TEST2_*
```

- [ ] **Step 4: Final commit with any fixes**

```bash
git add -A
git commit -m "test: verify custom research pipeline end-to-end"
```
