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


class PythonConfig(BaseModel):
    """Config for type: python — runs a Python script with argparse-style args."""
    script: str
    args: dict[str, str] = {}


class ClaudeConfig(BaseModel):
    """Config for type: claude — invokes Claude Code CLI."""
    prompt: str
    system: str | None = None
    model: str | None = None
    max_turns: int | None = None
    tools: list[str] = []
    reads_from: list[str] = []


class ShellConfig(BaseModel):
    """Config for type: shell — runs a shell command."""
    command: str


class PerplexityConfig(BaseModel):
    """Config for type: perplexity — calls Perplexity API."""
    prompt: str
    model: str | None = None
    reads_from: list[str] = []


class OpenAIConfig(BaseModel):
    """Config for type: openai — calls OpenAI API."""
    prompt: str
    model: str | None = None
    reads_from: list[str] = []
