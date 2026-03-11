# Web Runner Design — 2026-03-04

## Overview

Single-page web app for launching and monitoring stock research pipeline runs. FastAPI backend + Alpine.js frontend with WebSocket log streaming.

## Stack

- **Backend:** FastAPI, uvicorn, websockets (all in pyproject.toml already)
- **Frontend:** Alpine.js (CDN), single `static/index.html`
- **Styling:** Custom CSS, dark neon theme inspired by deepvalue.tech

## Backend: `web.py`

### Endpoints

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Serve `static/index.html` |
| `/reports` | GET | Scan `work/` for completed runs with `artifacts/final_report.md` |
| `/run` | POST | Accept `{ticker}`, compute date, spawn `research.py`, return `{run_id}` |
| `/status/{run_id}` | GET | Query `db.py status`, return task states + completion % |
| `/ws/{run_id}` | WS | Tail `*_stream.log` files, push lines to client |
| `/open/{run_id}` | POST | `open -a Typora` on `artifacts/final_report.md` |

### Process Management

- `running: dict[str, Process]` tracks active pipelines
- Only one pipeline at a time (reject `/run` if busy)
- On pipeline completion: auto-open Typora

### Status Response Shape

```json
{
  "run_id": "ADSK_20260304",
  "ticker": "ADSK",
  "status": "running",
  "progress": 0.65,
  "tasks": [
    {"id": "profile", "status": "complete", "sort_order": 1},
    {"id": "technical", "status": "running", "sort_order": 2}
  ]
}
```

### WebSocket Protocol

- Server pushes log lines as plain text
- Client just appends to log area
- On disconnect/error: client auto-reconnects after 2s

## Frontend: `static/index.html`

### Layout

Three-panel layout:
1. **Header bar** — title, ticker input, Run button
2. **Sidebar** (left) — past reports with dates, clickable
3. **Main area** (right) — status panel (task grid + progress bar) above, log output below

### Color Scheme

```css
--bg:        #07090f;
--surface:   #0c1220;
--cyan:      #00c8f0;    /* primary accent */
--green:     #00e87a;    /* complete */
--amber:     #ffb340;    /* running */
--red:       #ff4060;    /* failed */
--text:      #dde8f8;
--text-dim:  #5a7898;
```

Subtle dot-grid background, glow effects on status indicators. JetBrains Mono for logs, Open Sans for UI.

### Interactions

- Type ticker + Enter (or click Run) → POST /run → connect WebSocket
- Status panel polls GET /status/{run_id} every 2s
- Log area streams via WebSocket, auto-scrolls
- Sidebar populated on load via GET /reports
- On completion: Typora auto-opens, UI shows "Complete" state

### Alpine.js State

```javascript
{
  ticker: '',
  runId: null,
  status: null,       // from /status polling
  logs: [],           // from WebSocket
  reports: [],        // from /reports
  running: false,
  ws: null,
  pollInterval: null
}
```

## Files

| File | Purpose |
|------|---------|
| `web.py` | FastAPI backend (~200 lines) |
| `static/index.html` | Frontend (~800 lines) |

## Launch

```bash
uv run uvicorn web:app --reload --port 8000
```
