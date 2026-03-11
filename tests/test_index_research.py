"""
Tests for skills/chunk_index/index_research.py — post-research indexing pipeline.

Tests cover:
- MCP cache text extraction and chunking
- Research findings conversion to chunks
- Tag derivation from requestor task IDs
- Deduplication of MCP entries
- Append to existing LanceDB index
- Graceful handling of empty inputs
"""
import json
import sqlite3
import sys
from pathlib import Path

# Add skills/ to path for imports
_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

from chunk_index.index_research import (
    extract_text_from_result,
    tags_from_requestors,
    read_mcp_cache,
    read_findings,
    TASK_TO_SECTION,
)


# --- extract_text_from_result ---

def test_extract_text_from_content_list():
    """Extracts text from MCP TextContent blocks."""
    result = json.dumps({
        "content": [
            {"type": "text", "text": "Apple Inc. was founded in 1976."},
            {"type": "text", "text": "It is headquartered in Cupertino."},
        ]
    })
    text = extract_text_from_result(result)
    assert "Apple Inc. was founded in 1976." in text
    assert "It is headquartered in Cupertino." in text


def test_extract_text_from_list_format():
    """Extracts text when result is a list of content blocks."""
    result = json.dumps([
        {"type": "text", "text": "Revenue grew 15% year-over-year."},
    ])
    text = extract_text_from_result(result)
    assert "Revenue grew 15%" in text


def test_extract_text_skips_non_text():
    """Non-text content blocks are ignored."""
    result = json.dumps({
        "content": [
            {"type": "image", "data": "base64..."},
            {"type": "text", "text": "Actual content here."},
        ]
    })
    text = extract_text_from_result(result)
    assert "Actual content here." in text
    assert "base64" not in text


def test_extract_text_invalid_json():
    """Invalid JSON returns empty string."""
    assert extract_text_from_result("not valid json {{{") == ""


def test_extract_text_empty():
    """Empty/None input returns empty string."""
    assert extract_text_from_result("") == ""
    assert extract_text_from_result("null") == ""


# --- tags_from_requestors ---

def test_tags_single_requestor():
    """Single research task maps to its section tag."""
    assert tags_from_requestors(["research_financial"]) == ["financial"]


def test_tags_multiple_requestors():
    """Multiple requestors produce union of tags."""
    tags = tags_from_requestors(["research_financial", "research_valuation"])
    assert "financial" in tags
    assert "valuation" in tags


def test_tags_unknown_requestor():
    """Unknown task IDs get default 'research' tag."""
    assert tags_from_requestors(["unknown_task"]) == ["research"]


def test_tags_mixed_known_unknown():
    """Known requestors override the default; unknown ones don't add noise."""
    tags = tags_from_requestors(["research_competitive", "unknown_task"])
    assert tags == ["competitive"]


def test_tags_dedup():
    """Same section from multiple requestors doesn't duplicate."""
    tags = tags_from_requestors(["research_financial", "research_financial"])
    assert tags == ["financial"]


# --- read_mcp_cache ---

def _create_mcp_cache(workdir: Path, rows: list[dict]) -> None:
    """Helper to create an mcp-cache.db with given rows."""
    db_path = workdir / "mcp-cache.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE mcp_cache (
            cache_key TEXT PRIMARY KEY,
            server TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            arguments TEXT NOT NULL,
            result TEXT NOT NULL,
            requestors TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        )
    """)
    for row in rows:
        conn.execute(
            "INSERT INTO mcp_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                row["cache_key"], row.get("server", "test"),
                row["tool_name"], row.get("arguments", "{}"),
                row["result"], row.get("requestors", "[]"),
                row.get("created_at", "2026-01-01T00:00:00Z"),
            )
        )
    conn.commit()
    conn.close()


def test_read_mcp_cache_basic(tmp_path):
    """MCP cache entries with sufficient text are converted to chunks."""
    long_text = "This is a detailed analysis of the company's financial performance. " * 5
    result = json.dumps({"content": [{"type": "text", "text": long_text}]})
    _create_mcp_cache(tmp_path, [{
        "cache_key": "abc123",
        "tool_name": "get_financials",
        "result": result,
        "requestors": json.dumps(["research_financial"]),
    }])
    chunks = read_mcp_cache(tmp_path)
    assert len(chunks) > 0
    assert all("financial" in json.loads(c["tags"]) for c in chunks)
    assert all(c["doc_type"] == "mcp_research" for c in chunks)


def test_read_mcp_cache_short_text_skipped(tmp_path):
    """MCP results with too little text are skipped."""
    result = json.dumps({"content": [{"type": "text", "text": "42"}]})
    _create_mcp_cache(tmp_path, [{
        "cache_key": "short1",
        "tool_name": "get_price",
        "result": result,
        "requestors": json.dumps(["research_valuation"]),
    }])
    chunks = read_mcp_cache(tmp_path)
    assert len(chunks) == 0


def test_read_mcp_cache_missing_db(tmp_path):
    """No mcp-cache.db returns empty list."""
    chunks = read_mcp_cache(tmp_path)
    assert chunks == []


def test_read_mcp_cache_dedup_requestors(tmp_path):
    """Same cache entry requested by multiple agents produces one set of chunks with union tags."""
    long_text = "Detailed competitive analysis showing market dynamics and positioning. " * 5
    result = json.dumps({"content": [{"type": "text", "text": long_text}]})
    _create_mcp_cache(tmp_path, [{
        "cache_key": "shared1",
        "tool_name": "search",
        "result": result,
        "requestors": json.dumps(["research_competitive", "research_supply_chain"]),
    }])
    chunks = read_mcp_cache(tmp_path)
    assert len(chunks) > 0
    tags = json.loads(chunks[0]["tags"])
    assert "competitive" in tags
    assert "supply_chain" in tags


# --- read_findings ---

def _create_findings_db(workdir: Path, findings: list[dict]) -> None:
    """Helper to create a research.db with research_findings table."""
    db_path = workdir / "research.db"
    conn = sqlite3.connect(str(db_path))
    # Minimal schema — just the table we need
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY
        )
    """)
    conn.execute("INSERT OR IGNORE INTO tasks VALUES ('research_financial')")
    conn.execute("INSERT OR IGNORE INTO tasks VALUES ('research_competitive')")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_findings (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            content TEXT NOT NULL,
            source TEXT,
            tags TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    for f in findings:
        conn.execute(
            "INSERT INTO research_findings (id, task_id, content, source, tags) VALUES (?, ?, ?, ?, ?)",
            (f["id"], f["task_id"], f["content"], f.get("source"), f.get("tags", "[]"))
        )
    conn.commit()
    conn.close()


def test_read_findings_basic(tmp_path):
    """Research findings are converted to chunks with correct metadata."""
    long_content = "The company's revenue grew 25% year-over-year driven by strong demand in cloud services. " * 3
    _create_findings_db(tmp_path, [{
        "id": "abcd1234-5678-9abc-def0-123456789abc",
        "task_id": "research_financial",
        "content": long_content,
        "source": "10-K filing",
        "tags": json.dumps(["financial", "valuation"]),
    }])
    chunks = read_findings(tmp_path)
    assert len(chunks) == 1
    assert chunks[0]["id"] == "finding_abcd1234"
    assert chunks[0]["source"] == "10-K filing"
    assert chunks[0]["doc_type"] == "research_finding"
    tags = json.loads(chunks[0]["tags"])
    assert "financial" in tags


def test_read_findings_short_content_skipped(tmp_path):
    """Findings with very short content are skipped."""
    _create_findings_db(tmp_path, [{
        "id": "short-1234",
        "task_id": "research_financial",
        "content": "N/A",
        "source": None,
        "tags": "[]",
    }])
    chunks = read_findings(tmp_path)
    assert len(chunks) == 0


def test_read_findings_missing_db(tmp_path):
    """No research.db returns empty list."""
    chunks = read_findings(tmp_path)
    assert chunks == []


def test_read_findings_uses_task_id_as_source_fallback(tmp_path):
    """When source is None, falls back to finding:{task_id}."""
    long_content = "Significant finding about competitive dynamics in the semiconductor industry. " * 3
    _create_findings_db(tmp_path, [{
        "id": "nosource-1234-5678",
        "task_id": "research_competitive",
        "content": long_content,
        "source": None,
        "tags": json.dumps(["competitive"]),
    }])
    chunks = read_findings(tmp_path)
    assert len(chunks) == 1
    assert chunks[0]["source"] == "finding:research_competitive"


# --- TASK_TO_SECTION mapping ---

def test_task_to_section_completeness():
    """All 7 research tasks are mapped."""
    expected_tasks = [
        "research_profile", "research_business", "research_competitive",
        "research_supply_chain", "research_financial", "research_valuation",
        "research_risk_news",
    ]
    for task in expected_tasks:
        assert task in TASK_TO_SECTION, f"Missing mapping for {task}"
