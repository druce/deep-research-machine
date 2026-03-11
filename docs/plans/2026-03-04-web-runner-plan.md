# Web Runner Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a dark-neon web UI for launching and monitoring stock research pipeline runs.

**Architecture:** FastAPI backend serves a single-page Alpine.js app. WebSocket streams log output in real-time. REST endpoints handle pipeline launching, status polling, and report discovery. Auto-opens Typora on completion.

**Tech Stack:** FastAPI, uvicorn, websockets, Alpine.js (CDN), PyYAML — all already in pyproject.toml.

**Design doc:** `docs/plans/2026-03-04-web-runner-design.md`

---

### Task 1: Backend — web.py

**Files:**
- Create: `web.py`

**Step 1: Create `web.py` with all endpoints**

```python
#!/usr/bin/env python3
"""
web.py — FastAPI app for running equity research pipeline.

Usage: uv run uvicorn web:app --reload --port 8000
"""

import asyncio
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent
WORK_DIR = ROOT / "work"
DB_PY = ROOT / "skills" / "db.py"
DAG_PATH = ROOT / "dags" / "sra.yaml"

app = FastAPI()

_sort_order: dict[str, int] = {}
running: dict[str, asyncio.subprocess.Process] = {}


def load_sort_order(dag_path: Path) -> dict[str, int]:
    with open(dag_path) as f:
        dag = yaml.safe_load(f)
    tasks = dag.get("tasks", {})
    return {tid: (cfg or {}).get("sort_order", 999) for tid, cfg in tasks.items()}


def list_reports(work_dir: Path) -> list[dict]:
    pattern = re.compile(r"^([A-Z]+)_(\d{8})$")
    results = []
    if not work_dir.exists():
        return []
    for d in work_dir.iterdir():
        if not d.is_dir():
            continue
        m = pattern.match(d.name)
        if not m:
            continue
        report = d / "artifacts" / "final_report.md"
        if not report.exists():
            continue
        ticker, datestr = m.group(1), m.group(2)
        date = f"{datestr[:4]}-{datestr[4:6]}-{datestr[6:]}"
        results.append({"run_id": d.name, "ticker": ticker, "date": date, "path": str(report)})
    results.sort(key=lambda r: r["date"], reverse=True)
    return results


@app.on_event("startup")
async def startup():
    global _sort_order
    _sort_order = load_sort_order(DAG_PATH)


@app.get("/")
async def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/reports")
async def get_reports():
    return list_reports(WORK_DIR)


@app.post("/run")
async def run_pipeline(body: dict):
    ticker = body.get("ticker", "").strip().upper()
    if not ticker or not re.fullmatch(r"[A-Z]{1,10}", ticker):
        return JSONResponse({"error": "invalid ticker"}, status_code=400)

    date = datetime.now().strftime("%Y%m%d")
    run_id = f"{ticker}_{date}"

    # Reject if already running
    proc = running.get(run_id)
    if proc and proc.returncode is None:
        return JSONResponse({"error": "already running"}, status_code=409)

    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(ROOT / "research.py"), ticker, "--date", date,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    running[run_id] = proc
    return {"run_id": run_id}


@app.get("/status/{run_id}")
async def get_status(run_id: str):
    if not re.fullmatch(r"[A-Z]{1,10}_\d{8}", run_id):
        return JSONResponse({"error": "invalid run_id"}, status_code=400)
    workdir = WORK_DIR / run_id
    if not workdir.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(DB_PY), "status", "--workdir", str(workdir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0:
            data = json.loads(stdout.decode())
            if "task_details" in data:
                data["task_details"].sort(key=lambda t: _sort_order.get(t.get("id", ""), 999))
            return data
    except Exception:
        pass
    return JSONResponse({"error": "status unavailable"}, status_code=500)


@app.post("/open/{run_id}")
async def open_report(run_id: str):
    if not re.fullmatch(r"[A-Z]{1,10}_\d{8}", run_id):
        return JSONResponse({"error": "invalid run_id"}, status_code=400)
    report = WORK_DIR / run_id / "artifacts" / "final_report.md"
    if not report.exists():
        return JSONResponse({"error": "report not found"}, status_code=404)
    subprocess.Popen(["open", "-a", "Typora", str(report)])
    return {"ok": True}


@app.websocket("/ws/{run_id}")
async def websocket_log(ws: WebSocket, run_id: str):
    await ws.accept()
    if not re.fullmatch(r"[A-Z]{1,10}_\d{8}", run_id):
        await ws.send_json({"type": "error", "text": "invalid run_id"})
        await ws.close()
        return
    workdir = WORK_DIR / run_id

    # Wait up to 10s for workdir to appear
    for _ in range(50):
        if workdir.exists():
            break
        await asyncio.sleep(0.2)
    if not workdir.exists():
        await ws.send_json({"type": "error", "text": f"workdir not found: {run_id}"})
        await ws.close()
        return

    offsets: dict[Path, int] = {}

    async def drain():
        for log_path in sorted(workdir.glob("*_stream.log")):
            if log_path not in offsets:
                offsets[log_path] = 0
            try:
                size = log_path.stat().st_size
            except FileNotFoundError:
                continue
            if size > offsets[log_path]:
                with open(log_path, "r", errors="replace") as f:
                    f.seek(offsets[log_path])
                    text = f.read()
                    offsets[log_path] = f.tell()
                if text.strip():
                    task_name = log_path.stem.replace("_stream", "")
                    await ws.send_json({"type": "log", "task": task_name, "text": text})

    try:
        while True:
            await drain()
            proc = running.get(run_id)
            if proc and proc.returncode is not None:
                await asyncio.sleep(0.3)
                await drain()
                report = workdir / "artifacts" / "final_report.md"
                await ws.send_json({
                    "type": "complete",
                    "success": proc.returncode == 0,
                    "report": str(report) if report.exists() else None,
                })
                if report.exists():
                    subprocess.Popen(["open", "-a", "Typora", str(report)])
                break
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        pass


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
```

**Step 2: Create `static/` directory**

Run: `mkdir -p static`

**Step 3: Verify backend starts**

Run: `uv run uvicorn web:app --port 8000 &` then `curl -s http://localhost:8000/reports | python -m json.tool`
Expected: `[]` or a list of report objects. Kill the server after.

**Step 4: Commit**

```bash
git add web.py
git commit -m "feat: add web.py FastAPI backend with all endpoints"
```

---

### Task 2: Frontend — static/index.html

**Files:**
- Create: `static/index.html`

This is the largest task. Build the full single-page app with:

**Step 1: Create `static/index.html`**

The HTML file should include:

1. **Head:** Google Fonts (Open Sans + JetBrains Mono), Alpine.js CDN, all CSS inline
2. **CSS variables:** The dark neon color scheme from the design doc
3. **Layout structure:**
   - Header bar with title "SRA5", ticker input, Run button
   - Sidebar (left, ~210px) listing past reports
   - Main area split: status panel (top) + log output (bottom)
4. **Status panel:**
   - Current ticker display + progress bar
   - Task grid showing all 21 tasks with status icons (○ pending, ◌ running, ✓ complete, ✗ failed)
   - Color-coded: cyan for active, green for complete, amber for running, red for failed
5. **Log output:**
   - Monospace textarea with auto-scroll
   - Color-coded task prefixes
   - Shows WebSocket streamed content
6. **Visual details:**
   - Dot-grid background pattern (subtle cyan dots)
   - Ambient glow blobs (radial gradients)
   - Glow effects on status indicators
   - Shimmer animation on progress bar
   - Pulsing dot on running tasks

**Alpine.js state and methods:**

```javascript
Alpine.data('app', () => ({
    ticker: '',
    runId: null,
    status: null,
    logs: [],
    reports: [],
    running: false,
    ws: null,
    pollInterval: null,

    async init() {
        this.reports = await (await fetch('/reports')).json();
    },

    async startRun() {
        if (!this.ticker.trim() || this.running) return;
        const res = await fetch('/run', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ticker: this.ticker.trim()})
        });
        const data = await res.json();
        if (data.error) { alert(data.error); return; }
        this.runId = data.run_id;
        this.running = true;
        this.logs = [];
        this.status = null;
        this.connectWs();
        this.startPolling();
    },

    connectWs() {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.ws = new WebSocket(`${proto}//${location.host}/ws/${this.runId}`);
        this.ws.onmessage = (e) => {
            const msg = JSON.parse(e.data);
            if (msg.type === 'log') {
                this.logs.push({task: msg.task, text: msg.text});
                this.$nextTick(() => {
                    const el = this.$refs.logArea;
                    if (el) el.scrollTop = el.scrollHeight;
                });
            } else if (msg.type === 'complete') {
                this.running = false;
                this.stopPolling();
                this.refreshReports();
            }
        };
        this.ws.onclose = () => {
            if (this.running) setTimeout(() => this.connectWs(), 2000);
        };
    },

    startPolling() {
        this.pollInterval = setInterval(async () => {
            if (!this.runId) return;
            try {
                this.status = await (await fetch(`/status/${this.runId}`)).json();
            } catch {}
        }, 2000);
    },

    stopPolling() {
        if (this.pollInterval) { clearInterval(this.pollInterval); this.pollInterval = null; }
    },

    async refreshReports() {
        this.reports = await (await fetch('/reports')).json();
    },

    get progress() {
        if (!this.status?.task_details) return 0;
        const done = this.status.task_details.filter(t => t.status === 'complete').length;
        return Math.round((done / this.status.task_details.length) * 100);
    },

    taskIcon(status) {
        return {pending: '○', running: '◌', complete: '✓', failed: '✗'}[status] || '○';
    },

    taskColor(status) {
        return {pending: 'var(--text-dim)', running: 'var(--amber)', complete: 'var(--green)', failed: 'var(--red)'}[status] || 'var(--text-dim)';
    }
}));
```

**Step 2: Verify the full app**

Run: `uv run uvicorn web:app --reload --port 8000`
Open: `http://localhost:8000` in browser
Expected: Dark neon UI loads, sidebar shows any existing reports, ticker input is functional.

**Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat: add dark neon frontend with Alpine.js"
```

---

### Task 3: Integration test — end-to-end

**Step 1: Manual smoke test**

1. Start server: `uv run uvicorn web:app --reload --port 8000`
2. Open `http://localhost:8000`
3. Verify sidebar shows existing reports (e.g., TOST_20260303)
4. Enter a ticker, click Run
5. Verify: WebSocket connects, logs stream in, task grid updates, progress bar fills
6. On completion: Typora opens with final report

**Step 2: Commit**

```bash
git add web.py static/index.html
git commit -m "feat: complete web runner with live streaming and auto-open"
```
