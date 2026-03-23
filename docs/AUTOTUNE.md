# Autotuner: Prompt Optimization Loop

Autonomous prompt tuning for equity research section writers. One section at a time, iteratively improve the writing prompt in `dags/sra.yaml` using an eval rubric and trimmed scoring.

## Overview

The autotuner runs a loop: modify the prompt, regenerate the section, score it with 5 parallel evals, keep or discard the change. Each experiment touches ONE variable so we can attribute score changes. Discards are reverted with `git reset --hard HEAD~1`.

## Setup Checklist

For each section you want to tune:

### 1. Create an evaluation rubric

Copy an existing rubric (e.g., `evaluate_competitive.md`) and adapt it:

```bash
cp evaluate_competitive.md evaluate_<section>.md
```

Customize:
- **Completeness**: checklist items from the `write_<section>` task prompt + critic prompt
- **Length**: set target word range based on section importance (see below)
- **Insight**: what analytical depth looks like for this section
- **Relevance**: what a PM would skip
- **Style**: correct heading (e.g., `## N. Section Name`), same professional standards

Output schema is always the same:
```json
{"completeness": N, "length": N, "insight": N, "relevance": N, "style": N, "total": N.N, "notes": "..."}
```

### 2. Set length targets

Generate the section once and check word count:
```bash
wc -w work/NVDA_20260318/artifacts/section_N_<section>.md
```

Set the rubric target so the current output scores 8-10 on length. Adjust by +/-10-20% if needed. Round all bands to nearest 100.

### 3. Update autotuner.md

Update `autotuner.md` for the target section. Key things to change:
- Task name (`write_<section>`)
- Output file path (`artifacts/section_N_<section>.md`)
- Drafts path (`drafts/section_N_<section>*`)
- Search sections (`--sections <section>`)
- Eval output files (`eval_<abbrev>_N.json`)
- Rubric file (`evaluate_<section>.md`)
- Strategy guidance (section-specific optimization suggestions)

### 4. Set n_iterations to 0 in DAG

In `dags/sra.yaml`, set `n_iterations: 0` on the target task. We tune the raw write, not the critic loop output.

### 5. Reset experiments.tsv

```bash
echo "commit\ttotal\tcompleteness\tlength\tinsight\trelevance\tstyle\tstatus\tdescription" > experiments.tsv
```

### 6. Run baseline

```bash
rm -f work/NVDA_20260318/artifacts/section_N_<section>.md
rm -f work/NVDA_20260318/drafts/section_N_<section>*
./research.py NVDA --date 20260318 --task write_<section> --reload-yaml
```

Then run 5 evals (see "Running evals" below), compute trimmed scores, and record baseline in experiments.tsv.

### 7. Create a branch

```bash
git checkout -b autoresearch/<section>-nvda master
```

Commit the rubric and autotuner.md so they're tracked. These are untracked files and survive `git reset --hard HEAD~1` either way, but committing keeps them in history.

**Important**: The `--reload-yaml` flag must be on `master` before branching. The autotuner's discard mechanism (`git reset --hard HEAD~1`) will revert any commit on the tuning branch. Infrastructure changes go on master first, then merge into the tuning branch.

## Running Evals

Evals run as 5 parallel background Agent tasks within the same Claude session. Do NOT use `claude -p` subprocesses — that spawns separate sessions and causes auth/rate-limit issues.

Each agent reads the rubric + section output and writes JSON to `work/NVDA_20260318/tmp/eval_<abbrev>_N.json`.

### Trimmed scoring

Drop the best and worst score per dimension, average the middle 3. This removes outlier evals.

```bash
python3 -c "
import json, re

results = []
for i in range(1, 6):
    with open(f'work/NVDA_20260318/tmp/eval_<abbrev>_{i}.json') as f:
        text = f.read().strip()
        m = re.search(r'\{[^}]+\}', text, re.DOTALL)
        results.append(json.loads(m.group()))

dims = ['completeness', 'length', 'insight', 'relevance', 'style']
trimmed = {}
for d in dims:
    vals = sorted(r[d] for r in results)
    trimmed[d] = round(sum(vals[1:4]) / 3, 2)

total = round(sum(trimmed.values()) / len(dims), 2)
print(f'total={total}')
for d in dims:
    print(f'{d}={trimmed[d]}')
"
```

## Launching the Autotuner

Once baseline is recorded, launch a new Claude session with this prompt:

```
Read autotuner.md and begin. A baseline and an initial experiment is already recorded in experiments.tsv. Start the experiment loop.
```

The autotuner will run autonomously until interrupted. It commits each experiment, evals, records in experiments.tsv, then keeps (advances) or discards (`git reset --hard HEAD~1`).

## Sections Tuned So Far

| Section | Branch | Best Total | Experiments |
|---------|--------|-----------|-------------|
| Profile | autoresearch/profile-nvda | 8.8 | 49 |
| Competitive | autoresearch/profile-nvda | 9.0 | 6 |
| Supply Chain | (pending) | 8.6 baseline | 0 |

## Key Lessons

- **Length is always the first bottleneck.** Raw outputs run 20-40% over target. Adding explicit word count constraints is typically the first +1 point gain.
- **Style plateaus at 8.** Bullet-point lists and formulaic structure are the main deductors. Hard to push past 8 without very specific prose style rules.
- **One change at a time.** Multi-variable experiments make attribution impossible. If a two-change experiment fails, you don't know which change hurt.
- **Commit infrastructure to master.** The `--reload-yaml` flag was lost twice because it was committed on the tuning branch and reverted by `git reset --hard HEAD~1`. Anything that isn't a prompt experiment goes on master first.
- **Untracked files survive resets.** `autotuner.md`, `evaluate_*.md`, and `experiments.tsv` are untracked, so `git reset --hard HEAD~1` doesn't touch them.
- **Don't use `claude -p` for parallel evals.** Multiple simultaneous `claude -p` subprocesses cause auth/session conflicts. Use Agent background tasks within one session instead.
- **Eval agents need local write paths.** Agents can't write to `/tmp`. Use `work/NVDA_20260318/tmp/` instead.
