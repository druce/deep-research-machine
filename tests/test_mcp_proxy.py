"""
Tests for mcp_proxy.py — unit tests for requestors tracking + integration tests.

Unit tests verify requestors column behavior without starting MCP servers.
Integration tests (marked @pytest.mark.integration) test full proxy with real services.

Run unit tests:  uv run pytest tests/test_mcp_proxy.py -v -m "not integration"
Run all:         uv run pytest tests/test_mcp_proxy.py -v
"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "mcp_proxy"))
from mcp_proxy import open_cache, make_cache_key  # noqa: E402

CWD = str(Path(__file__).parent.parent)
PROXY = ["uv", "run", "python", "skills/mcp_proxy/mcp_proxy.py"]


def call_via_proxy(proxy_args: list[str], tool_name: str, arguments: dict, workdir: str) -> dict:
    """Start proxy, send a single tool call, return result."""
    env = {**os.environ, "MCP_CACHE_WORKDIR": workdir}
    harness = Path(CWD) / "tests" / "_proxy_harness.py"
    result = subprocess.run(
        ["uv", "run", "python", str(harness),
         "--proxy-args", json.dumps(proxy_args),
         "--tool", tool_name,
         "--arguments", json.dumps(arguments)],
        capture_output=True, text=True, cwd=CWD, env=env, timeout=60
    )
    assert result.returncode == 0, f"Harness failed: {result.stderr}"
    return json.loads(result.stdout)


def cache_row_count(workdir: str) -> int:
    db_path = Path(workdir) / "mcp-cache.db"
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM mcp_cache").fetchone()[0]
    conn.close()
    return count


@pytest.mark.integration
def test_yfinance_cache(tmp_path):
    """yfinance stdio transport — get_stock_info for AAPL."""
    workdir = str(tmp_path)
    proxy_args = ["--transport", "stdio", "--command", "uvx", "--args", "yfinance-mcp"]

    result1 = call_via_proxy(proxy_args, "get_stock_info", {"symbol": "AAPL"}, workdir)
    assert result1
    assert cache_row_count(workdir) == 1

    result2 = call_via_proxy(proxy_args, "get_stock_info", {"symbol": "AAPL"}, workdir)
    assert cache_row_count(workdir) == 1
    assert result1 == result2


@pytest.mark.integration
def test_wikipedia_cache(tmp_path):
    """wikipedia stdio transport — get_article for Apple Inc."""
    workdir = str(tmp_path)
    proxy_args = ["--transport", "stdio", "--command", "uvx", "--args", "wikipedia-mcp"]

    result1 = call_via_proxy(proxy_args, "get_article", {"title": "Apple Inc."}, workdir)
    assert result1
    assert cache_row_count(workdir) == 1

    result2 = call_via_proxy(proxy_args, "get_article", {"title": "Apple Inc."}, workdir)
    assert cache_row_count(workdir) == 1
    assert result1 == result2


@pytest.mark.integration
def test_perplexity_cache(tmp_path):
    """perplexity-ask stdio/npx — simple factual query."""
    workdir = str(tmp_path)
    proxy_args = ["--transport", "stdio", "--command", "npx",
                  "--args", "-y,@anthropic-ai/mcp-server-perplexity"]

    result1 = call_via_proxy(proxy_args, "ask", {"query": "What year was Apple founded?"}, workdir)
    assert result1
    assert cache_row_count(workdir) == 1

    result2 = call_via_proxy(proxy_args, "ask", {"query": "What year was Apple founded?"}, workdir)
    assert cache_row_count(workdir) == 1
    assert result1 == result2


@pytest.mark.integration
def test_brave_search_cache(tmp_path):
    """brave-search stdio/npx — company news query."""
    workdir = str(tmp_path)
    proxy_args = ["--transport", "stdio", "--command", "npx",
                  "--args", "-y,@modelcontextprotocol/server-brave-search"]

    result1 = call_via_proxy(proxy_args, "brave_web_search",
                              {"query": "Apple Inc earnings 2024"}, workdir)
    assert result1
    assert cache_row_count(workdir) == 1

    result2 = call_via_proxy(proxy_args, "brave_web_search",
                              {"query": "Apple Inc earnings 2024"}, workdir)
    assert cache_row_count(workdir) == 1
    assert result1 == result2


@pytest.mark.integration
def test_alphavantage_cache(tmp_path):
    """alphavantage stdio — TIME_SERIES_DAILY for AAPL."""
    workdir = str(tmp_path)
    proxy_args = ["--transport", "stdio", "--command", "uvx",
                  "--args", "alphavantage-mcp"]

    result1 = call_via_proxy(proxy_args, "TIME_SERIES_DAILY",
                              {"symbol": "AAPL", "outputsize": "compact"}, workdir)
    assert result1
    assert cache_row_count(workdir) == 1

    result2 = call_via_proxy(proxy_args, "TIME_SERIES_DAILY",
                              {"symbol": "AAPL", "outputsize": "compact"}, workdir)
    assert cache_row_count(workdir) == 1
    assert result1 == result2


@pytest.mark.integration
def test_openbb_cache(tmp_path):
    """openbb-mcp stdio — equity quote for AAPL."""
    workdir = str(tmp_path)
    proxy_args = ["--transport", "stdio", "--command", "uvx", "--args", "openbb-mcp"]

    result1 = call_via_proxy(proxy_args, "equity_quote", {"symbol": "AAPL"}, workdir)
    assert result1
    assert cache_row_count(workdir) == 1

    result2 = call_via_proxy(proxy_args, "equity_quote", {"symbol": "AAPL"}, workdir)
    assert cache_row_count(workdir) == 1
    assert result1 == result2


@pytest.mark.integration
def test_fmp_cache(tmp_path):
    """FMP HTTP transport — quote for AAPL."""
    import dotenv
    dotenv.load_dotenv()
    api_key = os.environ.get("FMP_API_KEY", "")
    if not api_key:
        pytest.skip("FMP test requires FMP_API_KEY")

    workdir = str(tmp_path)
    proxy_args = ["--transport", "http", "--url", f"https://financialmodelingprep.com/mcp?apikey={api_key}"]

    result1 = call_via_proxy(proxy_args, "quote", {"symbol": "AAPL"}, workdir)
    assert result1
    assert cache_row_count(workdir) == 1

    result2 = call_via_proxy(proxy_args, "quote", {"symbol": "AAPL"}, workdir)
    assert cache_row_count(workdir) == 1
    assert result1 == result2


# --- Unit tests for requestors tracking ---

def test_requestors_populated_on_cache_miss(tmp_path):
    """New cache entries get requestors populated from MCP_TASK_ID env."""
    workdir = str(tmp_path)
    conn = open_cache(workdir)
    assert conn is not None

    # Simulate a cache miss insert
    key = make_cache_key("test_tool", {"arg": "val"})
    task_id = "research_financial"
    conn.execute(
        "INSERT INTO mcp_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
        (key, "test-server", "test_tool", '{"arg":"val"}',
         '{"content":[]}', json.dumps([task_id]),
         "2026-01-01T00:00:00Z")
    )
    conn.commit()

    row = conn.execute(
        "SELECT requestors FROM mcp_cache WHERE cache_key = ?", (key,)
    ).fetchone()
    requestors = json.loads(row["requestors"])
    assert requestors == ["research_financial"]
    conn.close()


def test_requestors_updated_on_cache_hit(tmp_path):
    """Cache hit from different task_id appends to requestors list."""
    workdir = str(tmp_path)
    conn = open_cache(workdir)
    assert conn is not None

    key = make_cache_key("search", {"query": "test"})
    # Initial insert with first requestor
    conn.execute(
        "INSERT INTO mcp_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
        (key, "test-server", "search", '{"query":"test"}',
         '{"content":[]}', json.dumps(["research_competitive"]),
         "2026-01-01T00:00:00Z")
    )
    conn.commit()

    # Simulate cache hit from different task — update requestors
    row = conn.execute(
        "SELECT requestors FROM mcp_cache WHERE cache_key = ?", (key,)
    ).fetchone()
    requestors = json.loads(row["requestors"])
    new_task = "research_supply_chain"
    assert new_task not in requestors
    requestors.append(new_task)
    conn.execute(
        "UPDATE mcp_cache SET requestors = ? WHERE cache_key = ?",
        (json.dumps(requestors), key)
    )
    conn.commit()

    # Verify both requestors present
    row = conn.execute(
        "SELECT requestors FROM mcp_cache WHERE cache_key = ?", (key,)
    ).fetchone()
    final = json.loads(row["requestors"])
    assert "research_competitive" in final
    assert "research_supply_chain" in final
    conn.close()


def test_requestors_no_duplicate_on_same_task(tmp_path):
    """Same task_id hitting cache again doesn't duplicate in requestors."""
    workdir = str(tmp_path)
    conn = open_cache(workdir)
    assert conn is not None

    key = make_cache_key("get_info", {})
    task_id = "research_profile"
    conn.execute(
        "INSERT INTO mcp_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
        (key, "test-server", "get_info", '{}',
         '{"content":[]}', json.dumps([task_id]),
         "2026-01-01T00:00:00Z")
    )
    conn.commit()

    # Simulate second hit from same task
    row = conn.execute(
        "SELECT requestors FROM mcp_cache WHERE cache_key = ?", (key,)
    ).fetchone()
    requestors = json.loads(row["requestors"])
    if task_id not in requestors:
        requestors.append(task_id)
    conn.execute(
        "UPDATE mcp_cache SET requestors = ? WHERE cache_key = ?",
        (json.dumps(requestors), key)
    )
    conn.commit()

    row = conn.execute(
        "SELECT requestors FROM mcp_cache WHERE cache_key = ?", (key,)
    ).fetchone()
    assert json.loads(row["requestors"]) == ["research_profile"]
    conn.close()


def test_schema_migration_existing_db(tmp_path):
    """open_cache adds requestors column to existing DB without it."""
    db_path = tmp_path / "mcp-cache.db"
    # Create an old-schema DB without requestors
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE mcp_cache (
            cache_key TEXT PRIMARY KEY,
            server TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            arguments TEXT NOT NULL,
            result TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO mcp_cache VALUES (?, ?, ?, ?, ?, ?)",
        ("key1", "srv", "tool", "{}", "{}", "2026-01-01")
    )
    conn.commit()
    conn.close()

    # open_cache should migrate — add requestors column
    migrated = open_cache(str(tmp_path))
    assert migrated is not None
    row = migrated.execute(
        "SELECT requestors FROM mcp_cache WHERE cache_key = 'key1'"
    ).fetchone()
    assert json.loads(row["requestors"]) == []
    migrated.close()
