#!/usr/bin/env python3
"""
web.py — FastAPI app for running equity research pipeline.

Usage: uv run uvicorn web:app --reload --port 8000
"""

import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

DB_PY = Path(__file__).parent / "skills" / "db.py"
WORK_DIR = Path(__file__).parent / "work"

# Track running pipelines: {run_id: asyncio.subprocess.Process}
running: dict[str, asyncio.subprocess.Process] = {}


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.post("/run")
async def run_pipeline(body: dict):
    ticker = body.get("ticker", "").strip().upper()
    if not ticker:
        return JSONResponse({"error": "ticker required"}, status_code=400)

    date = datetime.now().strftime("%Y%m%d")
    run_id = f"{ticker}_{date}"

    if run_id in running and running[run_id].returncode is None:
        return JSONResponse({"error": "already running"}, status_code=409)

    # Spawn research.py as background subprocess
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "research.py", ticker, "--date", date,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    running[run_id] = proc

    return {"run_id": run_id, "workdir": f"work/{run_id}"}


@app.get("/status/{run_id}")
async def get_status(run_id: str):
    workdir = WORK_DIR / run_id
    if not workdir.exists():
        return JSONResponse({"error": "not found"}, status_code=404)

    try:
        result = subprocess.run(
            [sys.executable, str(DB_PY), "status", "--workdir", str(workdir)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass

    return {"error": "status unavailable"}


@app.websocket("/ws/{run_id}")
async def websocket_log(ws: WebSocket, run_id: str):
    await ws.accept()
    workdir = WORK_DIR / run_id

    # Wait for workdir to appear (race with subprocess start)
    for _ in range(50):  # up to 10s
        if workdir.exists():
            break
        await asyncio.sleep(0.2)

    # Track file offsets: {path: offset}
    offsets: dict[Path, int] = {}

    try:
        while True:
            # Scan for *_stream.log files
            logs = sorted(workdir.glob("*_stream.log"))
            for log_path in logs:
                if log_path not in offsets:
                    offsets[log_path] = 0

                size = log_path.stat().st_size
                if size > offsets[log_path]:
                    with open(log_path, "r") as f:
                        f.seek(offsets[log_path])
                        new_text = f.read()
                        offsets[log_path] = f.tell()

                    if new_text.strip():
                        task_name = log_path.stem.replace("_stream", "")
                        await ws.send_json({
                            "type": "log",
                            "task": task_name,
                            "text": new_text,
                        })

            # Check if pipeline finished
            proc = running.get(run_id)
            if proc and proc.returncode is not None:
                # Final drain
                await asyncio.sleep(0.5)
                for log_path in workdir.glob("*_stream.log"):
                    size = log_path.stat().st_size
                    if size > offsets.get(log_path, 0):
                        with open(log_path, "r") as f:
                            f.seek(offsets.get(log_path, 0))
                            new_text = f.read()
                        if new_text.strip():
                            task_name = log_path.stem.replace("_stream", "")
                            await ws.send_json({
                                "type": "log",
                                "task": task_name,
                                "text": new_text,
                            })

                report = workdir / "artifacts" / "final_report.md"
                await ws.send_json({
                    "type": "complete",
                    "report": str(report) if report.exists() else None,
                })

                # Open Typora
                if report.exists():
                    subprocess.Popen(["open", "-a", "Typora", str(report)])

                break

            await asyncio.sleep(0.2)

    except WebSocketDisconnect:
        pass


# Serve static files (after routes so /static/* doesn't shadow API)
app.mount("/static", StaticFiles(directory="static"), name="static")
