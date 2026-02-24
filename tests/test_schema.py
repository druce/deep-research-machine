"""Tests for DAG schema v2 Pydantic models."""

import pytest
from schema import OutputDef, DagHeader
from schema import PythonConfig, ClaudeConfig, ShellConfig, PerplexityConfig, OpenAIConfig


def test_output_def_valid():
    out = OutputDef(path="artifacts/profile.json", format="json")
    assert out.path == "artifacts/profile.json"
    assert out.format == "json"


def test_output_def_missing_path():
    with pytest.raises(Exception):
        OutputDef(format="json")


def test_output_def_missing_format():
    with pytest.raises(Exception):
        OutputDef(path="artifacts/profile.json")


def test_dag_header_valid():
    header = DagHeader(
        version=2,
        name="Test DAG",
        inputs={"ticker": "${ticker}", "workdir": "${workdir}"},
        root_dir="..",
        template_dir="../templates",
    )
    assert header.version == 2
    assert header.name == "Test DAG"


def test_dag_header_wrong_version():
    with pytest.raises(Exception):
        DagHeader(
            version=1,
            name="Test DAG",
            inputs={},
            root_dir="..",
            template_dir="../templates",
        )


def test_dag_header_defaults():
    header = DagHeader(version=2, name="Test")
    assert header.inputs == {}
    assert header.root_dir == "."
    assert header.template_dir == "templates"


def test_python_config_valid():
    cfg = PythonConfig(script="skills/research_profile.py", args={"ticker": "AAPL"})
    assert cfg.script == "skills/research_profile.py"
    assert cfg.args == {"ticker": "AAPL"}


def test_python_config_missing_script():
    with pytest.raises(Exception):
        PythonConfig(args={"ticker": "AAPL"})


def test_python_config_no_args():
    cfg = PythonConfig(script="skills/run.py")
    assert cfg.args == {}


def test_claude_config_valid():
    cfg = ClaudeConfig(
        prompt="Write a report about ${ticker}",
        system="You are an analyst.",
        model="claude-sonnet-4-6",
        max_turns=10,
        tools=["read", "write"],
        reads_from=["profile", "technical"],
    )
    assert cfg.prompt == "Write a report about ${ticker}"
    assert cfg.tools == ["read", "write"]
    assert cfg.reads_from == ["profile", "technical"]


def test_claude_config_minimal():
    cfg = ClaudeConfig(prompt="Do something")
    assert cfg.system is None
    assert cfg.model is None
    assert cfg.max_turns is None
    assert cfg.tools == []
    assert cfg.reads_from == []


def test_claude_config_missing_prompt():
    with pytest.raises(Exception):
        ClaudeConfig(model="claude-sonnet-4-6")


def test_shell_config_valid():
    cfg = ShellConfig(command="pandoc input.md -o output.pdf")
    assert cfg.command == "pandoc input.md -o output.pdf"


def test_shell_config_missing_command():
    with pytest.raises(Exception):
        ShellConfig()


def test_perplexity_config_valid():
    cfg = PerplexityConfig(prompt="Research news about AAPL", model="sonar-pro")
    assert cfg.model == "sonar-pro"


def test_perplexity_config_defaults():
    cfg = PerplexityConfig(prompt="Research news")
    assert cfg.model is None
    assert cfg.reads_from == []


def test_openai_config_valid():
    cfg = OpenAIConfig(prompt="Summarize this", model="gpt-4o")
    assert cfg.model == "gpt-4o"
