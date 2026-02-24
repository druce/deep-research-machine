"""DAG Schema v2 — Pydantic models for YAML validation.

Defines typed models for each task execution environment (python, claude,
shell, perplexity, openai). YAML is loaded and validated through these
models at db.py init time.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class OutputDef(BaseModel):
    """A named artifact produced by a task."""
    path: str
    format: str


class DagHeader(BaseModel):
    """Top-level DAG metadata."""
    version: Literal[2]
    name: str
    inputs: dict[str, str] = {}
    root_dir: str = "."
    template_dir: str = "templates"
