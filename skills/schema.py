"""DAG Schema v2 — Pydantic models for YAML validation.

Defines typed models for each task execution environment (python, claude,
shell, perplexity, openai). YAML is loaded and validated through these
models at db.py init time.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Discriminator, Tag


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


# ---------------------------------------------------------------------------
# Task models (one per execution type) and discriminated union
# ---------------------------------------------------------------------------

class _TaskBase(BaseModel):
    """Common fields for all task types."""
    description: str
    depends_on: list[str] = []
    outputs: dict[str, OutputDef] = {}


class PythonTask(_TaskBase):
    type: Literal["python"]
    config: PythonConfig


class ClaudeTask(_TaskBase):
    type: Literal["claude"]
    config: ClaudeConfig


class ShellTask(_TaskBase):
    type: Literal["shell"]
    config: ShellConfig


class PerplexityTask(_TaskBase):
    type: Literal["perplexity"]
    config: PerplexityConfig


class OpenAITask(_TaskBase):
    type: Literal["openai"]
    config: OpenAIConfig


Task = Annotated[
    Union[
        Annotated[PythonTask, Tag("python")],
        Annotated[ClaudeTask, Tag("claude")],
        Annotated[ShellTask, Tag("shell")],
        Annotated[PerplexityTask, Tag("perplexity")],
        Annotated[OpenAITask, Tag("openai")],
    ],
    Discriminator("type"),
]


# ---------------------------------------------------------------------------
# Root DAG file model
# ---------------------------------------------------------------------------

class DagFile(BaseModel):
    """Root model representing a complete DAG YAML file."""
    dag: DagHeader
    tasks: dict[str, Task]
