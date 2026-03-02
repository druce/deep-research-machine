# Web Runner v2 — Design Doc

**Date:** 2026-03-02
**Status:** Approved

## Summary

Local single-page web app for running the equity research pipeline. Dark navy UI (deepvalue.tech-inspired) with Open Sans typography, Alpine.js reactivity, streaming WebSocket log output, task status grid in DAG order, completion progress bar, and past report history. Replaces previous web.py + static/index.html implementation.

## Files

- `web.py` — FastAPI backend (single file)
- `static/index.html` — Single-page UI (HTML + CSS + JS inline, Alpine.js via CDN)
- `test.html` — Aesthetic prototype (reference only, not served)

## Layout

Two-column: fixed left sidebar (past reports) + main panel (controls, progress, tasks, log).

```
┌─── header ──────────────────────────────────────────────┐
│ ◆ SRA4 | Stock Research Agent       [status bar]        │
├─── sidebar (210px) ────┬─── main ──────────────────────┤
│ PAST REPORTS           │  TICKER [____] [▶ Run] [Demo]  │
│ ADSK  Mar 1            │  ████████████░░  62% Progress  │
│ MNDY  Mar 1            │                                 │
│ ...                    │  TASKS ──────────────────────── │
│                        │  ● profile  ● technical  ✓ ... │
│                        │                                 │
│                        │  OUTPUT ─────────────────────── │
│                        │  [log stream]                   │
└────────────────────────┴─────────────────────────────────┘
```

## Visual Design

- **Fonts:** Open Sans (UI), JetBrains Mono (log output, task names, ticker input)
- **Background:** `#07090f` with dot-grid overlay + ambient cyan/green radial blobs
- **Surface:** `#0c1220` (sidebar, header, control bar)
- **Accents:** cyan `#00c8f0` (primary), green `#00e87a` (complete), amber `#ffb340` (running), red `#ff4060` (failed)
- **Header:** thin cyan→green gradient line along bottom edge
- **Progress bar:** cyan→green gradient fill with glowing dot cursor, 2px height
- **Task pills:** colored border + background tint per state; amber shimmer animation on running; pulse dot animation
- **Status bar:** top-right, shows `TICKER — N pending · N running · N complete · N failed` while running; `TICKER — Complete` in green on finish

## Backend — web.py

### Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /` | — | Serve `static/index.html` |
| `POST /run` | `{ticker}` | Spawn `research.py`, return `{run_id, workdir}` |
| `GET /status/{run_id}` | — | `db.py status` → task list in `sort_order` |
| `GET /reports` | — | Scan `work/*/artifacts/final_report.md`, return list |
| `POST /open/{run_id}` | — | `open -a Typora` on `final_report.md` |
| `WS /ws/{run_id}` | WebSocket | Tail `*_stream.log` files, stream to browser |

### Task ordering

Read `sort_order` from `dags/sra.yaml` once at startup, cache as `{task_id: sort_order}`. `/status` returns tasks sorted by this value — never alphabetical.

### Subprocess management

Dict `{run_id: asyncio.Process}` tracks running pipelines. `POST /run` checks for existing process with `returncode is None` and returns 409 if already running.

### Log tailing (WebSocket)

Per-connection dict `{log_path: byte_offset}`. Poll every 200ms:
- Scan for new `*_stream.log` files
- Read new bytes from each, send `{type:"log", task:"...", text:"..."}`
- On process exit: drain final bytes, send `{type:"complete", report: path_or_null}`, call `open -a Typora`

### Report discovery

Walk `work/*/artifacts/final_report.md`, parse `{TICKER}_{YYYYMMDD}` from dir name, sort descending by date.

### Dependencies

`fastapi`, `uvicorn`, `websockets` (already added to pyproject.toml)

## Frontend — static/index.html

### Alpine.js state

```js
{
  tickerInput: '',
  ticker: '',
  running: false,
  completed: false,
  pct: 0,
  tasks: [{id, state}],   // ordered by sort_order from /status
  logs: [],               // innerHTML strings
  reports: [],            // from GET /reports
  ws: null,
  pollTimer: null,
}
```

### Run flow

1. `POST /run {ticker}` → `{run_id}`
2. Open `WebSocket /ws/{run_id}` → append log lines, auto-scroll
3. `setInterval` 2s → `GET /status/{run_id}` → update task states + `pct`
4. WS `{type:"complete"}` → clear interval, `completed=true`, refresh sidebar

### Error handling

- Empty ticker: flash input border red
- 409 already running: inline log message
- WS disconnect mid-run: amber warning in log, one reconnect attempt after 1s

### Past reports sidebar

Populated from `GET /reports` on page load. Refreshed after each completed run. Click row → `POST /open/{run_id}`.

## Data Flow

```
Page load  →  GET /reports  →  sidebar populated

User clicks Run
  →  POST /run {ticker}  →  research.py spawned  →  {run_id}
  →  WS /ws/{run_id}  →  log lines stream in  →  appended to log area
  →  poll GET /status  →  task pills update  →  progress bar fills

research.py exits
  →  WS sends {type:"complete"}
  →  open -a Typora final_report.md
  →  frontend: completed=true, sidebar refreshed
```

## Error Handling

- Empty ticker → 400
- Run already in progress → 409
- `research.py` nonzero exit → WS sends error message
- Missing workdir on WS connect → retry with 200ms backoff (up to 10s)

## Out of Scope

- Auth, multi-user, cancel mid-run, Docker, deployment
