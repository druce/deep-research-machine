#!/usr/bin/env python3
"""
web.py — FastAPI web runner for the stock research pipeline.

Provides REST endpoints for launching research runs, checking status,
viewing past reports, and a WebSocket for live log streaming.

Usage:
    uvicorn web:app --reload
"""

import asyncio
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent
WORK_DIR = ROOT / "work"
DB_PY = ROOT / "skills" / "db.py"
DAG_PATH = ROOT / "dags" / "sra.yaml"
STATIC_DIR = ROOT / "static"

# ---------------------------------------------------------------------------
# Load sort_order from DAG YAML at import time
# ---------------------------------------------------------------------------
_dag_data = yaml.safe_load(DAG_PATH.read_text())
TASK_SORT_ORDER: dict[str, int] = {
    task_id: task_cfg.get("sort_order", 999)
    for task_id, task_cfg in _dag_data.get("tasks", {}).items()
}

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="Stock Research Agent")

# Track running subprocess per run_id
running: dict[str, asyncio.subprocess.Process] = {}

# Regex for valid run_id
RUN_ID_RE = re.compile(r"^[A-Z]{1,10}_\d{8}$")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class RunRequest(BaseModel):
    ticker: str


class RunResponse(BaseModel):
    run_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def run_db_status(workdir: Path) -> dict:
    """Call db.py status and return parsed JSON."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(DB_PY), "status", "--workdir", str(workdir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode().strip() or stdout.decode().strip()
        raise HTTPException(status_code=500, detail=f"db.py status failed: {err}")
    return json.loads(stdout.decode())


def validate_run_id(run_id: str) -> None:
    """Raise 400 if run_id format is invalid."""
    if not RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail=f"Invalid run_id format: {run_id}")


# ---------------------------------------------------------------------------
# 1. GET / — serve static/index.html
# ---------------------------------------------------------------------------
@app.get("/")
async def index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path)


# ---------------------------------------------------------------------------
# 2. GET /reports — list completed reports, newest first
# ---------------------------------------------------------------------------
@app.get("/reports")
async def list_reports():
    if not WORK_DIR.exists():
        return []

    reports = []
    for d in WORK_DIR.iterdir():
        if not d.is_dir():
            continue
        # Must match TICKER_YYYYMMDD pattern
        if not RUN_ID_RE.match(d.name):
            continue
        report_path = d / "artifacts" / "final_report.md"
        if report_path.exists():
            parts = d.name.rsplit("_", 1)
            ticker = parts[0]
            date_str = parts[1] if len(parts) == 2 else ""
            reports.append({
                "run_id": d.name,
                "ticker": ticker,
                "date": date_str,
                "report_path": str(report_path),
            })

    # Sort newest first by date string (YYYYMMDD sorts lexically)
    reports.sort(key=lambda r: r["date"], reverse=True)
    return reports


# ---------------------------------------------------------------------------
# 3. POST /run — launch a new pipeline run
# ---------------------------------------------------------------------------
@app.post("/run", response_model=RunResponse)
async def start_run(req: RunRequest):
    ticker = req.ticker.strip().upper()
    if not re.match(r"^[A-Z]{1,10}$", ticker):
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {req.ticker}")

    date_str = datetime.now().strftime("%Y%m%d")
    run_id = f"{ticker}_{date_str}"

    # Only one pipeline per run_id at a time
    if run_id in running:
        proc = running[run_id]
        if proc.returncode is None:
            raise HTTPException(
                status_code=409,
                detail=f"Pipeline already running for {run_id}",
            )

    # Spawn research.py as async subprocess
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(ROOT / "research.py"), ticker, "--date", date_str,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    running[run_id] = proc

    return RunResponse(run_id=run_id)


# ---------------------------------------------------------------------------
# 4. GET /status/{run_id} — pipeline status with sorted task details
# ---------------------------------------------------------------------------
@app.get("/status/{run_id}")
async def get_status(run_id: str):
    validate_run_id(run_id)
    workdir = WORK_DIR / run_id
    if not workdir.exists():
        raise HTTPException(status_code=404, detail=f"Workdir not found: {run_id}")

    data = await run_db_status(workdir)

    # Sort task_details by DAG sort_order
    if "task_details" in data:
        data["task_details"].sort(
            key=lambda t: TASK_SORT_ORDER.get(t["id"], 999)
        )

    return data


# ---------------------------------------------------------------------------
# 5. POST /open/{run_id} — open final report in Typora
# ---------------------------------------------------------------------------
@app.post("/open/{run_id}")
async def open_report(run_id: str):
    validate_run_id(run_id)
    workdir = WORK_DIR / run_id
    report_path = workdir / "artifacts" / "final_report.md"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="final_report.md not found")

    subprocess.Popen(["open", "-a", "Typora", str(report_path)])
    return {"status": "opened", "path": str(report_path)}


# ---------------------------------------------------------------------------
# 6. WS /ws/{run_id} — tail stream logs, push updates
# ---------------------------------------------------------------------------
@app.websocket("/ws/{run_id}")
async def websocket_tail(ws: WebSocket, run_id: str):
    await ws.accept()
    if not RUN_ID_RE.match(run_id):
        await ws.send_json({"type": "error", "text": "Invalid run_id format"})
        await ws.close()
        return

    workdir = WORK_DIR / run_id

    # Wait up to 10s for workdir to appear (race with subprocess start)
    for _ in range(20):
        if workdir.exists():
            break
        await asyncio.sleep(0.5)
    else:
        await ws.send_json({"type": "error", "text": "Workdir did not appear within 10s"})
        await ws.close()
        return

    # Track file positions for each stream log
    file_positions: dict[str, int] = {}

    try:
        while True:
            # Discover all *_stream.log files
            log_files = list(workdir.glob("*_stream.log"))

            for log_file in log_files:
                path_str = str(log_file)
                pos = file_positions.get(path_str, 0)

                try:
                    size = log_file.stat().st_size
                    if size > pos:
                        with open(log_file, "r") as f:
                            f.seek(pos)
                            new_text = f.read()
                            file_positions[path_str] = f.tell()

                        if new_text.strip():
                            # Extract task name from filename: {task}_stream.log
                            task_name = log_file.stem.replace("_stream", "")
                            await ws.send_json({
                                "type": "log",
                                "task": task_name,
                                "text": new_text,
                            })
                except OSError:
                    continue

            # Check if pipeline process has finished
            proc = running.get(run_id)
            if proc and proc.returncode is not None:
                # Final drain to catch last bytes written before exit
                await asyncio.sleep(0.3)
                for log_file in list(workdir.glob("*_stream.log")):
                    path_str = str(log_file)
                    pos = file_positions.get(path_str, 0)
                    try:
                        size = log_file.stat().st_size
                        if size > pos:
                            with open(log_file, "r") as f:
                                f.seek(pos)
                                new_text = f.read()
                                file_positions[path_str] = f.tell()
                            if new_text.strip():
                                task_name = log_file.stem.replace("_stream", "")
                                await ws.send_json({"type": "log", "task": task_name, "text": new_text})
                    except OSError:
                        continue

                report_path = workdir / "artifacts" / "final_report.md"
                success = proc.returncode == 0 and report_path.exists()
                await ws.send_json({
                    "type": "complete",
                    "success": success,
                    "report": str(report_path) if report_path.exists() else None,
                })
                # Auto-open Typora on success
                if success:
                    subprocess.Popen(["open", "-a", "Typora", str(report_path)])
                break

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# 7. Mount /static for static files
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
