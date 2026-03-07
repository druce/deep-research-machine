# Research Swarm Refactor — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the equity research pipeline to separate research from writing via a shared findings store, chunked document index, and MCP tool caching proxy.

**Architecture:** Python tasks chunk and embed downloaded artifacts into a LanceDB hybrid index. Seven parallel Claude research agents populate a SQLite findings store (cross-tagged by section). Seven parallel Claude writing agents synthesize from findings. MCP proxy transparently caches all tool calls per run.

**Tech Stack:** Python 3.11+, LanceDB, OpenAI embeddings (text-embedding-3-small), rank-bm25, mcp (Python SDK), SQLite, asyncio, pytest

**Design doc:** `docs/plans/2026-03-07-research-swarm-design.md`

---

## Task 1: Add research_findings table + finding-add / finding-list to db.py

**Files:**
- Modify: `skills/db.py`
- Test: `tests/test_db.py`

### Step 1: Write the failing tests

Add to `tests/test_db.py`:

```python
def test_finding_add(workdir):
    rc, out = run_db(
        "finding-add", "--workdir", str(workdir),
        "--task-id", "research_competitive",
        "--content", "NVDA competes with AMD and Intel in discrete GPUs.",
        "--source", "artifacts/sec_10k_item1.md",
        "--tags", "competitive", "supply_chain",
    )
    assert rc == 0
    assert out["status"] == "ok"
    assert "id" in out


def test_finding_list_all(workdir):
    run_db("finding-add", "--workdir", str(workdir),
           "--task-id", "research_competitive",
           "--content", "NVDA dominates GPU market.",
           "--source", "10-K", "--tags", "competitive")
    run_db("finding-add", "--workdir", str(workdir),
           "--task-id", "research_financial",
           "--content", "NVDA revenue grew 120% YoY.",
           "--source", "income_statement.csv", "--tags", "financial")
    rc, out = run_db("finding-list", "--workdir", str(workdir))
    assert rc == 0
    assert len(out) == 2


def test_finding_list_filter_by_tags(workdir):
    run_db("finding-add", "--workdir", str(workdir),
           "--task-id", "research_competitive",
           "--content", "AMD is gaining share in data center.",
           "--source", "10-K", "--tags", "competitive", "financial")
    run_db("finding-add", "--workdir", str(workdir),
           "--task-id", "research_financial",
           "--content", "Gross margin expanded to 73%.",
           "--source", "income_statement.csv", "--tags", "financial")
    rc, out = run_db("finding-list", "--workdir", str(workdir), "--tags", "competitive")
    assert rc == 0
    assert len(out) == 1
    assert "AMD" in out[0]["content"]


def test_finding_add_requires_task_id(workdir):
    rc, out = run_db(
        "finding-add", "--workdir", str(workdir),
        "--content", "some content",
        "--tags", "competitive",
    )
    assert rc != 0
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_db.py::test_finding_add tests/test_db.py::test_finding_list_all tests/test_db.py::test_finding_list_filter_by_tags -v
```
Expected: FAIL — `finding-add` command not found.

### Step 3: Add research_findings table to SCHEMA in `skills/db.py`

Add to the `SCHEMA` string (after the `dag_vars` table):

```python
CREATE TABLE IF NOT EXISTS research_findings (
  id          TEXT PRIMARY KEY,
  task_id     TEXT NOT NULL REFERENCES tasks(id),
  content     TEXT NOT NULL,
  source      TEXT,
  tags        TEXT NOT NULL DEFAULT '[]',
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Step 4: Add cmd_finding_add to `skills/db.py`

After `cmd_var_get`:

```python
def cmd_finding_add(args: argparse.Namespace) -> None:
    """Add a research finding tagged with section relevance."""
    import uuid
    conn = get_db(args.workdir)

    row = conn.execute("SELECT id FROM tasks WHERE id = ?", (args.task_id,)).fetchone()
    if not row:
        conn.close()
        error_exit(f"Task not found: {args.task_id}")

    finding_id = str(uuid.uuid4())
    tags = json.dumps(args.tags or [])
    conn.execute(
        """INSERT INTO research_findings (id, task_id, content, source, tags)
           VALUES (?, ?, ?, ?, ?)""",
        (finding_id, args.task_id, args.content, args.source, tags)
    )
    conn.commit()
    conn.close()
    print(json.dumps({"status": "ok", "id": finding_id}))
```

### Step 5: Add cmd_finding_list to `skills/db.py`

```python
def cmd_finding_list(args: argparse.Namespace) -> None:
    """List research findings, optionally filtered by tags."""
    conn = get_db(args.workdir)

    rows = conn.execute(
        "SELECT id, task_id, content, source, tags, created_at FROM research_findings ORDER BY created_at"
    ).fetchall()

    result = []
    for row in rows:
        tags = json.loads(row["tags"])
        if args.tags:
            if not any(t in tags for t in args.tags):
                continue
        result.append({
            "id": row["id"],
            "task_id": row["task_id"],
            "content": row["content"],
            "source": row["source"],
            "tags": tags,
            "created_at": row["created_at"],
        })

    conn.close()
    print(json.dumps(result, indent=2))
```

### Step 6: Wire up CLI parsers in `main()` in `skills/db.py`

In the `subparsers` block add:

```python
# finding-add
p_fadd = subparsers.add_parser('finding-add', help='Add a research finding')
p_fadd.add_argument('--workdir', required=True)
p_fadd.add_argument('--task-id', required=True, dest='task_id')
p_fadd.add_argument('--content', required=True)
p_fadd.add_argument('--source', default=None)
p_fadd.add_argument('--tags', nargs='*', default=[])

# finding-list
p_flist = subparsers.add_parser('finding-list', help='List research findings')
p_flist.add_argument('--workdir', required=True)
p_flist.add_argument('--tags', nargs='*', default=None)
```

In the `commands` dict:

```python
'finding-add': cmd_finding_add,
'finding-list': cmd_finding_list,
```

Also ensure the `research_findings` table is created for existing DBs by running `executescript(SCHEMA)` with `IF NOT EXISTS` — already the case since SCHEMA uses `CREATE TABLE IF NOT EXISTS`.

### Step 7: Run tests to verify they pass

```bash
uv run pytest tests/test_db.py::test_finding_add tests/test_db.py::test_finding_list_all tests/test_db.py::test_finding_list_filter_by_tags -v
```
Expected: PASS

### Step 8: Commit

```bash
git add skills/db.py tests/test_db.py
git commit -m "feat: add research_findings table + finding-add/finding-list CLI commands"
```

---

## Task 2: chunk_documents.py — load, chunk, and embed artifacts

**Files:**
- Create: `skills/chunk_index/chunk_documents.py`
- Test: `tests/test_chunk_documents.py`

### Step 1: Add dependency

```bash
uv add openai tiktoken
```

### Step 2: Write the failing test

Create `tests/test_chunk_documents.py`:

```python
"""Tests for chunk_documents.py — chunking and embedding of text artifacts."""
import json
import subprocess
from pathlib import Path

import pytest

CWD = str(Path(__file__).parent.parent)
SCRIPT = ["uv", "run", "python", "skills/chunk_index/chunk_documents.py"]


def run_chunk(workdir, *extra_args):
    result = subprocess.run(
        SCRIPT + ["TEST", "--workdir", str(workdir)] + list(extra_args),
        capture_output=True, text=True, cwd=CWD,
    )
    try:
        manifest = json.loads(result.stdout)
    except json.JSONDecodeError:
        manifest = None
    return result.returncode, manifest, result.stderr


@pytest.fixture
def workdir_with_artifacts(tmp_path):
    """Create a minimal workdir with text artifacts and a manifest."""
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "wikipedia_full.txt").write_text(
        "Nvidia Corporation is an American multinational technology company.\n\n"
        "It designs graphics processing units for gaming and professional markets.\n\n"
        "Nvidia was founded in 1993 by Jensen Huang, Chris Malachowsky, and Curtis Priem.\n\n"
        "The company is headquartered in Santa Clara, California.\n\n"
        "Nvidia's primary products include the GeForce line of GPUs for gaming.\n\n"
        "Nvidia competes with AMD in discrete graphics cards for gaming.\n\n"
        "The data center segment has grown rapidly due to AI computing demand.\n\n"
        "Nvidia's CUDA platform is widely used in scientific computing.\n\n"
        "The company reported record revenue in fiscal year 2024.\n\n"
        "Supply chain dependencies include TSMC for chip manufacturing."
    )
    (art / "manifest.json").write_text(json.dumps([
        {"file": "artifacts/wikipedia_full.txt", "format": "txt",
         "description": "Wikipedia full article"}
    ]))
    return tmp_path


def test_chunk_documents_produces_chunks_json(workdir_with_artifacts):
    rc, manifest, stderr = run_chunk(workdir_with_artifacts)
    assert rc == 0, f"Failed: {stderr}"
    assert manifest["status"] == "complete"
    chunks_path = workdir_with_artifacts / "artifacts" / "chunks.json"
    assert chunks_path.exists()
    chunks = json.loads(chunks_path.read_text())
    assert len(chunks) >= 1
    assert all("id" in c for c in chunks)
    assert all("text" in c for c in chunks)
    assert all("source" in c for c in chunks)
    assert all("embedding" in c for c in chunks)
    assert all(len(c["embedding"]) == 1536 for c in chunks)


def test_chunk_documents_skips_binary(workdir_with_artifacts):
    """PNG and CSV files should not be chunked."""
    (workdir_with_artifacts / "artifacts" / "chart.png").write_bytes(b"\x89PNG fake")
    (workdir_with_artifacts / "artifacts" / "income.csv").write_text("year,revenue\n2024,60000\n")
    rc, manifest, _ = run_chunk(workdir_with_artifacts)
    assert rc == 0
    chunks = json.loads((workdir_with_artifacts / "artifacts" / "chunks.json").read_text())
    sources = [c["source"] for c in chunks]
    assert not any("chart.png" in s for s in sources)
    assert not any("income.csv" in s for s in sources)


def test_chunk_documents_metadata(workdir_with_artifacts):
    rc, _, _ = run_chunk(workdir_with_artifacts)
    assert rc == 0
    chunks = json.loads((workdir_with_artifacts / "artifacts" / "chunks.json").read_text())
    for c in chunks:
        assert c["source"].startswith("artifacts/")
        assert "doc_type" in c
```

### Step 3: Run to verify fail

```bash
uv run pytest tests/test_chunk_documents.py -v
```
Expected: FAIL — script not found.

### Step 4: Create `skills/chunk_index/__init__.py` (empty) and `skills/chunk_index/chunk_documents.py`

```python
#!/usr/bin/env python3
"""
Chunk and embed text artifacts for hybrid search index.

Loads text artifacts discovered via manifest.json, splits them into
400-800 token chunks at semantic boundaries, embeds via OpenAI
text-embedding-3-small, and writes artifacts/chunks.json.

Usage:
    ./skills/chunk_index/chunk_documents.py SYMBOL --workdir DIR

Output (stdout):  JSON manifest {"status": "complete", "artifacts": [...]}
Output (files):   artifacts/chunks.json
"""
import argparse
import json
import sys
from pathlib import Path

import tiktoken
from openai import OpenAI

_SKILLS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

from utils import setup_logging, load_environment  # noqa: E402

load_environment()
logger = setup_logging(__name__)

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536
CHUNK_TARGET_TOKENS = 600
CHUNK_MAX_TOKENS = 800
SKIP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".csv", ".json", ".db", ".pdf"}
TEXT_EXTENSIONS = {".md", ".txt"}

enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(enc.encode(text))


def chunk_text(text: str, source: str) -> list[dict]:
    """Split text into chunks at paragraph boundaries, targeting CHUNK_TARGET_TOKENS."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current_parts = []
    current_tokens = 0
    chunk_idx = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)
        if current_tokens + para_tokens > CHUNK_MAX_TOKENS and current_parts:
            chunks.append({
                "id": f"{Path(source).stem}_{chunk_idx:04d}",
                "text": "\n\n".join(current_parts),
                "source": source,
                "doc_type": infer_doc_type(source),
            })
            chunk_idx += 1
            current_parts = []
            current_tokens = 0
        current_parts.append(para)
        current_tokens += para_tokens

    if current_parts:
        chunks.append({
            "id": f"{Path(source).stem}_{chunk_idx:04d}",
            "text": "\n\n".join(current_parts),
            "source": source,
            "doc_type": infer_doc_type(source),
        })

    return chunks


def infer_doc_type(source: str) -> str:
    name = Path(source).name.lower()
    if "10k" in name or "10-k" in name:
        return "10-K"
    if "10q" in name or "10-q" in name:
        return "10-Q"
    if "8k" in name or "8-k" in name:
        return "8-K"
    if "wikipedia" in name:
        return "wikipedia"
    if "news" in name:
        return "news"
    if "perplexity" in name or "analysis" in name:
        return "analysis"
    if "business_profile" in name:
        return "profile"
    return "other"


def embed_chunks(chunks: list[dict], client: OpenAI) -> list[dict]:
    """Embed all chunks in a single batched API call."""
    texts = [c["text"] for c in chunks]
    logger.info(f"Embedding {len(texts)} chunks...")
    response = client.embeddings.create(model=EMBED_MODEL, input=texts)
    for i, data in enumerate(response.data):
        chunks[i]["embedding"] = data.embedding
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--workdir", required=True)
    args = parser.parse_args()

    workdir = Path(args.workdir)
    artifacts_dir = workdir / "artifacts"
    manifest_path = artifacts_dir / "manifest.json"

    if not manifest_path.exists():
        print(json.dumps({"status": "failed", "error": "manifest.json not found", "artifacts": []}))
        return 1

    manifest = json.loads(manifest_path.read_text())
    client = OpenAI()
    all_chunks = []

    for entry in manifest:
        file_path = workdir / entry["file"]
        ext = file_path.suffix.lower()
        if ext not in TEXT_EXTENSIONS:
            continue
        if not file_path.exists():
            logger.warning(f"Skipping missing file: {file_path}")
            continue
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            continue
        source = entry["file"]
        chunks = chunk_text(text, source)
        logger.info(f"  {source}: {len(chunks)} chunks")
        all_chunks.extend(chunks)

    if not all_chunks:
        print(json.dumps({"status": "failed", "error": "No text artifacts to chunk", "artifacts": []}))
        return 1

    all_chunks = embed_chunks(all_chunks, client)

    out_path = artifacts_dir / "chunks.json"
    out_path.write_text(json.dumps(all_chunks, indent=2))
    logger.info(f"Wrote {len(all_chunks)} chunks to {out_path}")

    print(json.dumps({
        "status": "complete",
        "artifacts": [{"name": "chunks", "path": "artifacts/chunks.json", "format": "json"}],
        "error": None,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Also create empty `skills/chunk_index/__init__.py`.

### Step 5: Run tests to verify they pass

```bash
uv run pytest tests/test_chunk_documents.py -v
```
Expected: PASS (requires OPENAI_API_KEY in .env — these are integration tests, mark them `@pytest.mark.integration` if desired)

### Step 6: Commit

```bash
git add skills/chunk_index/ tests/test_chunk_documents.py
git commit -m "feat: add chunk_documents.py — load, chunk, and embed text artifacts"
```

---

## Task 3: build_index.py + search_index.py — LanceDB hybrid index

**Files:**
- Create: `skills/chunk_index/build_index.py`
- Create: `skills/search_index/__init__.py` (empty)
- Create: `skills/search_index/search_index.py`
- Test: `tests/test_search_index.py`

### Step 1: Add dependencies

```bash
uv add lancedb
```

### Step 2: Write the failing test

Create `tests/test_search_index.py`:

```python
"""Tests for build_index.py + search_index.py."""
import json
import subprocess
from pathlib import Path

import pytest

CWD = str(Path(__file__).parent.parent)
BUILD_SCRIPT = ["uv", "run", "python", "skills/chunk_index/build_index.py"]
SEARCH_SCRIPT = ["uv", "run", "python", "skills/search_index/search_index.py"]


def run_build(workdir):
    r = subprocess.run(BUILD_SCRIPT + ["TEST", "--workdir", str(workdir)],
                       capture_output=True, text=True, cwd=CWD)
    try:
        return r.returncode, json.loads(r.stdout), r.stderr
    except json.JSONDecodeError:
        return r.returncode, None, r.stderr


def run_search(workdir, query, sections=None, top_k=5):
    cmd = SEARCH_SCRIPT + [query, "--workdir", str(workdir), "--top-k", str(top_k)]
    if sections:
        cmd += ["--sections"] + sections
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=CWD)
    try:
        return r.returncode, json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.returncode, None


@pytest.fixture
def workdir_with_chunks(tmp_path):
    """Minimal workdir with chunks.json and chunk_tags.json."""
    art = tmp_path / "artifacts"
    art.mkdir()

    # Fake embeddings (1536 zeros — good enough for index structure tests)
    fake_vec = [0.0] * 1536
    chunks = [
        {"id": "wiki_0000", "text": "Nvidia competes with AMD and Intel in GPUs.",
         "source": "artifacts/wikipedia_full.txt", "doc_type": "wikipedia",
         "embedding": fake_vec},
        {"id": "wiki_0001", "text": "Nvidia revenue grew 120% in FY2024.",
         "source": "artifacts/wikipedia_full.txt", "doc_type": "wikipedia",
         "embedding": fake_vec},
        {"id": "10k_0000", "text": "Supply chain depends on TSMC for chip manufacturing.",
         "source": "artifacts/sec_10k_item1.md", "doc_type": "10-K",
         "embedding": fake_vec},
    ]
    (art / "chunks.json").write_text(json.dumps(chunks))
    tags = [
        {"id": "wiki_0000", "tags": ["competitive"]},
        {"id": "wiki_0001", "tags": ["financial"]},
        {"id": "10k_0000", "tags": ["supply_chain", "risk_news"]},
    ]
    (art / "chunk_tags.json").write_text(json.dumps(tags))
    return tmp_path


def test_build_index_creates_lance_db(workdir_with_chunks):
    rc, manifest, stderr = run_build(workdir_with_chunks)
    assert rc == 0, f"build_index failed: {stderr}"
    assert manifest["status"] == "complete"
    index_dir = workdir_with_chunks / "artifacts" / "index"
    assert index_dir.exists()
    assert any(index_dir.iterdir())  # non-empty


def test_search_returns_results(workdir_with_chunks):
    run_build(workdir_with_chunks)
    rc, results = run_search(workdir_with_chunks, "GPU competition")
    assert rc == 0
    assert isinstance(results, list)
    assert len(results) >= 1
    assert all("text" in r for r in results)
    assert all("source" in r for r in results)
    assert all("tags" in r for r in results)


def test_search_filter_by_section(workdir_with_chunks):
    run_build(workdir_with_chunks)
    rc, results = run_search(workdir_with_chunks, "supply chain", sections=["supply_chain"])
    assert rc == 0
    # All returned results should have supply_chain tag
    for r in results:
        assert "supply_chain" in r["tags"]


def test_build_index_merges_tags(workdir_with_chunks):
    rc, _, _ = run_build(workdir_with_chunks)
    assert rc == 0
    # Verify the index file exists and contains expected data
    import lancedb
    db = lancedb.connect(str(workdir_with_chunks / "artifacts" / "index"))
    table = db.open_table("chunks")
    df = table.to_pandas()
    assert "tags" in df.columns
    assert len(df) == 3
```

### Step 3: Run to verify fail

```bash
uv run pytest tests/test_search_index.py -v
```
Expected: FAIL — scripts not found.

### Step 4: Create `skills/chunk_index/build_index.py`

```python
#!/usr/bin/env python3
"""
Build LanceDB hybrid index from chunks.json + chunk_tags.json.

Usage:
    ./skills/chunk_index/build_index.py SYMBOL --workdir DIR
"""
import argparse
import json
import sys
from pathlib import Path

import lancedb
import pyarrow as pa

_SKILLS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

from utils import setup_logging  # noqa: E402

logger = setup_logging(__name__)
EMBED_DIM = 1536


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--workdir", required=True)
    args = parser.parse_args()

    workdir = Path(args.workdir)
    artifacts_dir = workdir / "artifacts"

    chunks_path = artifacts_dir / "chunks.json"
    tags_path = artifacts_dir / "chunk_tags.json"

    if not chunks_path.exists():
        print(json.dumps({"status": "failed", "error": "chunks.json not found", "artifacts": []}))
        return 1
    if not tags_path.exists():
        print(json.dumps({"status": "failed", "error": "chunk_tags.json not found", "artifacts": []}))
        return 1

    chunks = json.loads(chunks_path.read_text())
    tags_list = json.loads(tags_path.read_text())
    tags_map = {t["id"]: t["tags"] for t in tags_list}

    # Merge tags into chunks
    for c in chunks:
        c["tags"] = json.dumps(tags_map.get(c["id"], []))

    # Build LanceDB table
    index_dir = artifacts_dir / "index"
    index_dir.mkdir(exist_ok=True)
    db = lancedb.connect(str(index_dir))

    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("source", pa.string()),
        pa.field("doc_type", pa.string()),
        pa.field("tags", pa.string()),  # JSON-encoded list
        pa.field("vector", pa.list_(pa.float32(), EMBED_DIM)),
    ])

    records = []
    for c in chunks:
        records.append({
            "id": c["id"],
            "text": c["text"],
            "source": c["source"],
            "doc_type": c.get("doc_type", "other"),
            "tags": c["tags"],
            "vector": [float(x) for x in c["embedding"]],
        })

    if "chunks" in db.table_names():
        db.drop_table("chunks")
    table = db.create_table("chunks", data=records, schema=schema)
    table.create_fts_index("text", replace=True)
    logger.info(f"Built index: {len(records)} chunks in {index_dir}")

    print(json.dumps({
        "status": "complete",
        "artifacts": [{"name": "index", "path": "artifacts/index/", "format": "lancedb"}],
        "error": None,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Step 5: Create `skills/search_index/search_index.py`

```python
#!/usr/bin/env python3
"""
Hybrid vector + BM25 search over the LanceDB chunk index.

Usage:
    ./skills/search_index/search_index.py QUERY --workdir DIR [--sections S1 S2] [--top-k N]

Output: JSON array of matching chunks, ranked by reciprocal rank fusion.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import lancedb
from openai import OpenAI

_SKILLS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

from utils import setup_logging, load_environment  # noqa: E402

load_environment()
logger = setup_logging(__name__)

EMBED_MODEL = "text-embedding-3-small"


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[str]:
    """Merge multiple ranked lists via RRF. Returns IDs sorted by fused score."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda x: scores[x], reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--sections", nargs="*", default=None)
    parser.add_argument("--top-k", type=int, default=10, dest="top_k")
    args = parser.parse_args()

    workdir = Path(args.workdir)
    index_dir = workdir / "artifacts" / "index"

    if not index_dir.exists():
        print(json.dumps({"error": "Index not found — run build_index first"}))
        return 1

    db = lancedb.connect(str(index_dir))
    table = db.open_table("chunks")

    # Vector search
    client = OpenAI()
    resp = client.embeddings.create(model=EMBED_MODEL, input=[args.query])
    query_vec = resp.data[0].embedding

    vec_results = (
        table.search(query_vec, query_type="vector")
        .limit(args.top_k * 2)
        .to_pandas()
    )

    # FTS search
    try:
        fts_results = (
            table.search(args.query, query_type="fts")
            .limit(args.top_k * 2)
            .to_pandas()
        )
    except Exception:
        fts_results = vec_results.head(0)  # empty fallback if FTS unavailable

    # RRF fusion
    vec_ids = vec_results["id"].tolist()
    fts_ids = fts_results["id"].tolist() if len(fts_results) > 0 else []
    merged_ids = reciprocal_rank_fusion([vec_ids, fts_ids])

    # Build id->row lookup
    all_rows = {row["id"]: row for _, row in vec_results.iterrows()}
    for _, row in fts_results.iterrows():
        all_rows[row["id"]] = row

    output = []
    for doc_id in merged_ids[: args.top_k]:
        if doc_id not in all_rows:
            continue
        row = all_rows[doc_id]
        tags = json.loads(row["tags"])
        if args.sections and not any(s in tags for s in args.sections):
            continue
        output.append({
            "id": doc_id,
            "text": row["text"],
            "source": row["source"],
            "doc_type": row["doc_type"],
            "tags": tags,
        })

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Also create empty `skills/search_index/__init__.py`.

### Step 6: Run tests to verify they pass

```bash
uv run pytest tests/test_search_index.py -v
```
Expected: PASS

### Step 7: Commit

```bash
git add skills/chunk_index/build_index.py skills/search_index/ tests/test_search_index.py
git commit -m "feat: add build_index.py and search_index.py — LanceDB hybrid search"
```

---

## Task 4: Add chunk wave tasks to dags/sra.yaml

**Files:**
- Modify: `dags/sra.yaml`
- Test: run `./skills/db.py validate` to confirm DAG is valid

The new tasks must be added after all data-gathering tasks and before writing tasks. Add them with `sort_order: 15` (between data tasks at 1-7 and writing tasks which start at ~20).

### Step 1: Add the three chunk wave tasks to `dags/sra.yaml`

Add after the `perplexity_analysis` task and before any writing tasks:

```yaml
  chunk_documents:
    sort_order: 15
    description: Chunk and embed text artifacts for hybrid retrieval
    type: python
    depends_on: [profile, technical, fundamental, perplexity, fetch_edgar, wikipedia, perplexity_analysis]
    config:
      script: skills/chunk_index/chunk_documents.py
      args:
        ticker: "${ticker}"
        workdir: "${workdir}"
    outputs:
      chunks: {path: "artifacts/chunks.json", format: json, description: "Text chunks with embeddings from all text artifacts"}

  tag_chunks:
    sort_order: 16
    description: Assign section relevance tags to each chunk using AI
    type: claude
    depends_on: [chunk_documents]
    config:
      prompt: |
        Read artifacts/chunks.json. For each chunk, assign relevance tags from this list:
        profile, business_model, competitive, supply_chain, financial, valuation, risk_news

        A chunk may have multiple tags if it is relevant to multiple sections.
        Apply tags generously — it is better to over-tag than under-tag.

        Write a JSON file to artifacts/chunk_tags.json in this exact format:
        [{"id": "<chunk_id>", "tags": ["tag1", "tag2"]}, ...]

        Include every chunk from chunks.json. Do not skip any.
      disallowed_tools: [WebSearch, WebFetch]
    outputs:
      chunk_tags: {path: "artifacts/chunk_tags.json", format: json, description: "Section relevance tags for each chunk"}

  build_index:
    sort_order: 17
    description: Build LanceDB hybrid vector+BM25 index from chunks and tags
    type: python
    depends_on: [tag_chunks]
    config:
      script: skills/chunk_index/build_index.py
      args:
        ticker: "${ticker}"
        workdir: "${workdir}"
    outputs:
      index: {path: "artifacts/index/", format: lancedb, description: "LanceDB hybrid search index of all chunked artifacts"}
```

### Step 2: Validate DAG

```bash
./skills/db.py validate --dag dags/sra.yaml --ticker TEST
```
Expected: `{"status": "ok", "version": 2, "tasks": <N+3>, ...}`

### Step 3: Commit

```bash
git add dags/sra.yaml
git commit -m "feat: add chunk_documents, tag_chunks, build_index tasks to DAG"
```

---

## Task 5: mcp_proxy.py — MCP caching proxy server

**Files:**
- Create: `skills/mcp_proxy/__init__.py` (empty)
- Create: `skills/mcp_proxy/mcp_proxy.py`

### Step 1: Add dependency

```bash
uv add mcp
```

Check the MCP SDK API before implementing:
```bash
uv run python -c "import mcp; help(mcp)"
```
Use context7 to look up `mcp` Python SDK documentation if needed:
```
resolve library id: mcp python sdk
query: "stdio server client tool call"
```

### Step 2: Create `skills/mcp_proxy/mcp_proxy.py`

The proxy must:
1. Run as a stdio MCP server (Claude connects to it)
2. Internally connect to the real server (stdio or HTTP transport)
3. On startup: call `tools/list` on real server, cache discovered tools
4. On `tools/call`: check SQLite cache, return cached result or forward to real server
5. If `MCP_CACHE_WORKDIR` is unset: pass through without caching

```python
#!/usr/bin/env python3
"""
MCP caching proxy — wraps any MCP server with SQLite result cache.

Runs as a stdio MCP server. Internally connects to the real server.
Caches all tool call results in {MCP_CACHE_WORKDIR}/mcp-cache.db.

Usage (stdio transport):
    python mcp_proxy.py --transport stdio --command npx --args "-y,@pkg/server"

Usage (HTTP/SSE transport):
    python mcp_proxy.py --transport http --url https://api.example.com/mcp?key=KEY

Environment:
    MCP_CACHE_WORKDIR  Path to workdir — cache stored at {workdir}/mcp-cache.db
                       If unset, proxy passes through without caching.
"""
import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# NOTE: Exact import paths depend on the installed mcp SDK version.
# Run: uv run python -c "import mcp; print(mcp.__version__)"
# and consult context7 docs for the correct API for your version.
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS mcp_cache (
  cache_key  TEXT PRIMARY KEY,
  server     TEXT NOT NULL,
  tool_name  TEXT NOT NULL,
  arguments  TEXT NOT NULL,
  result     TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def make_cache_key(tool_name: str, arguments: dict) -> str:
    payload = tool_name + "|" + json.dumps(arguments, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def open_cache(workdir: str | None) -> sqlite3.Connection | None:
    if not workdir:
        return None
    path = Path(workdir) / "mcp-cache.db"
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(CACHE_SCHEMA)
    conn.commit()
    return conn


async def run_proxy(args: argparse.Namespace) -> None:
    cache_conn = open_cache(os.environ.get("MCP_CACHE_WORKDIR"))
    server_label = args.command or args.url

    if args.transport == "stdio":
        cmd_args = args.args.split(",") if args.args else []
        server_params = StdioServerParameters(command=args.command, args=cmd_args)
        client_ctx = stdio_client(server_params)
    else:
        # HTTP/SSE transport — import here to avoid errors if not needed
        from mcp.client.sse import sse_client
        client_ctx = sse_client(args.url)

    async with client_ctx as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_response = await session.list_tools()
            available_tools = tools_response.tools

            proxy = Server("mcp-proxy")

            @proxy.list_tools()
            async def list_tools():
                return available_tools

            @proxy.call_tool()
            async def call_tool(name: str, arguments: dict | None = None):
                arguments = arguments or {}
                key = make_cache_key(name, arguments)

                if cache_conn:
                    row = cache_conn.execute(
                        "SELECT result FROM mcp_cache WHERE cache_key = ?", (key,)
                    ).fetchone()
                    if row:
                        return json.loads(row["result"])

                result = await session.call_tool(name, arguments)

                if cache_conn:
                    cache_conn.execute(
                        "INSERT OR REPLACE INTO mcp_cache VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            key, server_label, name,
                            json.dumps(arguments, sort_keys=True),
                            json.dumps(result, default=str),
                            datetime.now(timezone.utc).isoformat(),
                        )
                    )
                    cache_conn.commit()

                return result

            init_options = proxy.create_initialization_options()
            async with stdio_server() as (read_proxy, write_proxy):
                await proxy.run(read_proxy, write_proxy, init_options)


def main():
    parser = argparse.ArgumentParser(description="MCP caching proxy")
    parser.add_argument("--transport", choices=["stdio", "http"], required=True)
    parser.add_argument("--command", help="Command for stdio transport (e.g. npx)")
    parser.add_argument("--args", help="Comma-separated args for the command")
    parser.add_argument("--url", help="URL for HTTP/SSE transport")
    args = parser.parse_args()

    if args.transport == "stdio" and not args.command:
        parser.error("--command is required for stdio transport")
    if args.transport == "http" and not args.url:
        parser.error("--url is required for http transport")

    asyncio.run(run_proxy(args))


if __name__ == "__main__":
    main()
```

**Important:** The `mcp` Python SDK API evolves rapidly. Before implementing, verify the exact import paths and method signatures using:
```bash
uv run python -c "from mcp.server import Server; print('ok')"
uv run python -c "from mcp.client.stdio import stdio_client; print('ok')"
```
If imports fail, use `mcp__plugin_context7_context7__query-docs` to look up the current API.

### Step 3: Commit

```bash
git add skills/mcp_proxy/ pyproject.toml uv.lock
git commit -m "feat: add mcp_proxy.py — MCP caching proxy with SQLite backend"
```

---

## Task 6: gen_mcp_configs.py — generate .mcp.json and mcp-research.json

**Files:**
- Create: `scripts/__init__.py` (empty, if scripts/ dir doesn't exist)
- Create: `scripts/gen_mcp_configs.py`

### Step 1: Create `scripts/gen_mcp_configs.py`

```python
#!/usr/bin/env python3
"""
Generate MCP config files from Claude Desktop config.

Reads ~/Library/Application Support/Claude/claude_desktop_config.json and produces:
  .mcp.json          — coding profile: context7, playwright, filesystem (direct)
  mcp-research.json  — research profile: all finance/research servers via mcp_proxy.py

Usage:
    python scripts/gen_mcp_configs.py [--dry-run]
"""
import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESKTOP_CONFIG = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
PROXY_SCRIPT = str(PROJECT_ROOT / "skills" / "mcp_proxy" / "mcp_proxy.py")

# Servers to use directly in coding sessions (no proxy, no cache)
CODING_SERVERS = {"context7", "playwright", "filesystem"}


def wrap_with_proxy(name: str, server_def: dict) -> dict:
    """Wrap a server definition with mcp_proxy.py."""
    if "url" in server_def:
        # HTTP/SSE transport
        return {
            "command": "uv",
            "args": [
                "run", "python", PROXY_SCRIPT,
                "--transport", "http",
                "--url", server_def["url"],
            ]
        }
    else:
        # stdio transport
        real_cmd = server_def.get("command", "")
        real_args = server_def.get("args", [])
        args_str = ",".join(str(a) for a in real_args)
        proxy_args = [
            "run", "python", PROXY_SCRIPT,
            "--transport", "stdio",
            "--command", real_cmd,
        ]
        if args_str:
            proxy_args += ["--args", args_str]
        result = {"command": "uv", "args": proxy_args}
        if "env" in server_def:
            result["env"] = server_def["env"]
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not DESKTOP_CONFIG.exists():
        print(f"ERROR: Claude Desktop config not found at {DESKTOP_CONFIG}", file=sys.stderr)
        sys.exit(1)

    config = json.loads(DESKTOP_CONFIG.read_text())
    all_servers = config.get("mcpServers", {})

    coding_mcp = {"mcpServers": {}}
    research_mcp = {"mcpServers": {}}

    for name, definition in all_servers.items():
        if name in CODING_SERVERS:
            coding_mcp["mcpServers"][name] = definition
        else:
            research_mcp["mcpServers"][name] = wrap_with_proxy(name, definition)

    mcp_json_path = PROJECT_ROOT / ".mcp.json"
    research_json_path = PROJECT_ROOT / "mcp-research.json"

    if args.dry_run:
        print("=== .mcp.json ===")
        print(json.dumps(coding_mcp, indent=2))
        print("\n=== mcp-research.json ===")
        print(json.dumps(research_mcp, indent=2))
    else:
        mcp_json_path.write_text(json.dumps(coding_mcp, indent=2))
        research_json_path.write_text(json.dumps(research_mcp, indent=2))
        print(f"Written: {mcp_json_path}")
        print(f"Written: {research_json_path}")


if __name__ == "__main__":
    main()
```

### Step 2: Run it to generate configs

```bash
python scripts/gen_mcp_configs.py --dry-run
```
Review output — verify coding servers are direct, research servers are proxied.

```bash
python scripts/gen_mcp_configs.py
```

### Step 3: Add mcp-research.json to .gitignore (contains API keys via proxied env)

```bash
echo "mcp-research.json" >> .gitignore
```

### Step 4: Commit

```bash
git add scripts/gen_mcp_configs.py .gitignore
git commit -m "feat: add gen_mcp_configs.py — generate .mcp.json and mcp-research.json"
```

---

## Task 7: Update research.py — wire mcp_config into _invoke_claude

**Files:**
- Modify: `research.py:138-215` (`_invoke_claude`) and `research.py:342-511` (`run_claude_task`)

The schema (`ClaudeConfig`) already has `mcp_config: list[str] = []`. `research.py` needs to read it from params and pass it to claude.

### Step 1: Write failing test

Add to `tests/test_web.py` or create `tests/test_research_invoke.py`:

```python
"""Test that _invoke_claude passes mcp_config flags correctly."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_invoke_claude_mcp_config_in_cmd(tmp_path):
    """mcp_config paths should appear as --mcp-config flags in claude command."""
    from research import _invoke_claude

    captured_cmd = []

    async def fake_exec(*cmd, **kwargs):
        captured_cmd.extend(cmd)
        proc = MagicMock()
        proc.returncode = 0
        proc.stdin = AsyncMock()
        proc.stdout = AsyncMock()
        proc.stdout.__aiter__ = AsyncMock(return_value=iter([]))
        proc.wait = AsyncMock()
        # Write a dummy output file so _invoke_claude thinks it succeeded
        return proc

    # Create a dummy output file
    out_path = tmp_path / "artifacts" / "test.md"
    out_path.parent.mkdir(parents=True)
    out_path.write_text("content")

    async def run():
        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            await _invoke_claude(
                prompt="test prompt",
                workdir=tmp_path,
                task_id="test_task",
                step_label="write",
                mcp_config=["mcp-research.json"],
                expected_outputs={"out": {"path": "artifacts/test.md", "format": "md"}},
            )

    asyncio.run(run())
    assert "--mcp-config" in captured_cmd
    idx = captured_cmd.index("--mcp-config")
    assert captured_cmd[idx + 1] == "mcp-research.json"
```

### Step 2: Run to verify fail

```bash
uv run pytest tests/test_research_invoke.py -v
```
Expected: FAIL — `_invoke_claude` doesn't accept `mcp_config`.

### Step 3: Update `_invoke_claude` in `research.py`

Add `mcp_config: list[str] | None = None` and `extra_env: dict[str, str] | None = None` parameters.

After the existing `if max_budget_usd is not None:` block, add:

```python
    for config_path in (mcp_config or []):
        cmd.extend(["--mcp-config", config_path])
```

For `extra_env`, update the env construction:

```python
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    if extra_env:
        env.update(extra_env)
```

### Step 4: Update `run_claude_task` to pass mcp_config

In the `_invoke_claude(...)` call(s) in `run_claude_task`, add:

```python
        mcp_config=params.get("mcp_config") or None,
        extra_env={"MCP_CACHE_WORKDIR": str(workdir)} if params.get("mcp_config") else None,
```

Do this for all three `_invoke_claude` calls in `run_claude_task` (write, critic, rewrite steps).

### Step 5: Run tests

```bash
uv run pytest tests/test_research_invoke.py -v
```
Expected: PASS

### Step 6: Commit

```bash
git add research.py tests/test_research_invoke.py
git commit -m "feat: wire mcp_config and extra_env through _invoke_claude in research.py"
```

---

## Task 8: Integration tests for MCP proxy — all 7 services

**Files:**
- Create: `tests/test_mcp_proxy.py`

These tests require real API keys and running services. Mark them `@pytest.mark.integration` so they are excluded from default test runs.

### Step 1: Add integration marker to `tests/conftest.py`

```python
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires real API keys and network access")
```

Run integration tests with:
```bash
uv run pytest tests/test_mcp_proxy.py -m integration -v
```
Skip in CI with:
```bash
uv run pytest -m "not integration" -v
```

### Step 2: Create `tests/test_mcp_proxy.py`

```python
"""
Integration tests for mcp_proxy.py — one test per service.

Each test:
1. Creates a temp workdir with MCP_CACHE_WORKDIR set
2. Starts proxy subprocess, makes one tool call
3. Verifies mcp-cache.db has 1 row, result is non-empty
4. Makes identical call again
5. Verifies mcp-cache.db still has 1 row (cache hit, no new insert)
6. Verifies result matches

Run with: uv run pytest tests/test_mcp_proxy.py -m integration -v
"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

CWD = str(Path(__file__).parent.parent)
PROXY = ["uv", "run", "python", "skills/mcp_proxy/mcp_proxy.py"]


def call_via_proxy(proxy_args: list[str], tool_name: str, arguments: dict, workdir: str) -> dict:
    """Start proxy, send a single tool call, return result."""
    env = {**os.environ, "MCP_CACHE_WORKDIR": workdir}
    # Build a minimal JSON-RPC exchange via stdin
    # This is done by invoking the proxy via a helper that sends one call and exits
    # Use a small test harness script to drive the proxy
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
def test_fmp_cache(tmp_path):
    """FMP HTTP transport — quote for AAPL."""
    import dotenv
    dotenv.load_dotenv()
    api_key = os.environ.get("FMP_API_KEY", "")
    pytest.skip("FMP test requires manual mcp-research.json URL") if not api_key else None

    workdir = str(tmp_path)
    proxy_args = ["--transport", "http", "--url", f"https://financialmodelingprep.com/mcp?apikey={api_key}"]

    result1 = call_via_proxy(proxy_args, "quote", {"symbol": "AAPL"}, workdir)
    assert result1  # non-empty
    assert cache_row_count(workdir) == 1

    result2 = call_via_proxy(proxy_args, "quote", {"symbol": "AAPL"}, workdir)
    assert cache_row_count(workdir) == 1  # cache hit — no new row
    assert result1 == result2


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
```

### Step 3: Create test harness `tests/_proxy_harness.py`

This small script starts the proxy and drives one tool call via the MCP protocol:

```python
#!/usr/bin/env python3
"""
Test harness for mcp_proxy.py integration tests.
Starts the proxy as a subprocess, sends one tool call, prints result to stdout.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills"))

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy-args", required=True)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--arguments", required=True)
    args = parser.parse_args()

    proxy_args_list = json.loads(args.proxy_args)
    tool_name = args.tool
    tool_arguments = json.loads(args.arguments)

    proxy_params = StdioServerParameters(
        command="uv",
        args=["run", "python", "skills/mcp_proxy/mcp_proxy.py"] + proxy_args_list,
    )

    async with stdio_client(proxy_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, tool_arguments)
            print(json.dumps(result, default=str))


if __name__ == "__main__":
    asyncio.run(main())
```

### Step 4: Run integration tests (requires API keys and running MCP servers)

First verify the exact server names match what's in `mcp-research.json` — update proxy_args in each test to match. Then:

```bash
uv run pytest tests/test_mcp_proxy.py::test_yfinance_cache -m integration -v
uv run pytest tests/test_mcp_proxy.py::test_wikipedia_cache -m integration -v
# run each individually to identify server name issues before running all
uv run pytest tests/test_mcp_proxy.py -m integration -v
```

### Step 5: Commit

```bash
git add tests/test_mcp_proxy.py tests/_proxy_harness.py tests/conftest.py
git commit -m "test: add MCP proxy integration tests for all 7 research services"
```

---

## Task 9: Add 7 research agent tasks to dags/sra.yaml

**Files:**
- Modify: `dags/sra.yaml`

All 7 tasks follow the same pattern: `type: claude`, depend on `build_index` + all data-gathering tasks, use `mcp_config: [mcp-research.json]`.

### Step 1: Add the research tasks to `dags/sra.yaml`

Add after `build_index` (sort_order 17), before writing tasks (sort_order ~20):

```yaml
  research_profile:
    sort_order: 18
    description: Research company profile, history, and management
    type: claude
    depends_on: [build_index, profile, perplexity, wikipedia, perplexity_analysis]
    config:
      mcp_config: [mcp-research.json]
      prompt: |
        You are a research analyst investigating ${company_name} (${symbol}).
        Your domain: company profile, history, management, and business overview.

        1. Search the artifact index for relevant background:
           Run: uv run python skills/search_index/search_index.py "company history overview management" --workdir ${workdir} --sections profile --top-k 15

        2. Use available MCP tools to fill gaps (company profile, executives, Wikipedia).

        3. For each significant finding, record it with:
           uv run python skills/db.py finding-add --workdir ${workdir} --task-id research_profile \
             --content "<finding>" --source "<source>" --tags profile [other_relevant_tags...]

        Tag any finding cross-relevant to other sections (e.g. leadership changes → risk_news).
        Aim for at least 10 substantial findings.
      disallowed_tools: [WebSearch, WebFetch]

  research_business:
    sort_order: 18
    description: Research business model, revenue streams, and competitive moat
    type: claude
    depends_on: [build_index, profile, perplexity, perplexity_analysis]
    config:
      mcp_config: [mcp-research.json]
      prompt: |
        You are a research analyst investigating ${company_name} (${symbol}).
        Your domain: business model, revenue streams, unit economics, and competitive moat.

        1. Search the artifact index:
           Run: uv run python skills/search_index/search_index.py "business model revenue streams products segments" --workdir ${workdir} --sections business_model --top-k 15

        2. Use available MCP tools to research revenue breakdown, segment trends, and moat sources.

        3. Record each finding:
           uv run python skills/db.py finding-add --workdir ${workdir} --task-id research_business \
             --content "<finding>" --source "<source>" --tags business_model [other_relevant_tags...]

        Tag cross-relevant findings (e.g. margin structure → financial, moat → competitive).
        Aim for at least 10 substantial findings.
      disallowed_tools: [WebSearch, WebFetch]

  research_competitive:
    sort_order: 18
    description: Research competitive landscape, market share, and industry dynamics
    type: claude
    depends_on: [build_index, profile, perplexity, perplexity_analysis, fundamental]
    config:
      mcp_config: [mcp-research.json]
      prompt: |
        You are a research analyst investigating ${company_name} (${symbol}).
        Your domain: competitive landscape, market share, industry dynamics, and positioning.

        1. Search the artifact index:
           Run: uv run python skills/search_index/search_index.py "competitors market share industry landscape" --workdir ${workdir} --sections competitive --top-k 15

        2. Use available MCP tools to research competitors, peer financials, and market dynamics.

        3. Record each finding:
           uv run python skills/db.py finding-add --workdir ${workdir} --task-id research_competitive \
             --content "<finding>" --source "<source>" --tags competitive [other_relevant_tags...]

        Cross-tag relevant findings to supply_chain, valuation, or risk_news as appropriate.
        Aim for at least 10 substantial findings.
      disallowed_tools: [WebSearch, WebFetch]

  research_supply_chain:
    sort_order: 18
    description: Research supply chain, manufacturing dependencies, and geopolitical exposure
    type: claude
    depends_on: [build_index, profile, fetch_edgar, perplexity_analysis]
    config:
      mcp_config: [mcp-research.json]
      prompt: |
        You are a research analyst investigating ${company_name} (${symbol}).
        Your domain: supply chain, manufacturing partners, input dependencies, and geopolitical exposure.

        1. Search the artifact index:
           Run: uv run python skills/search_index/search_index.py "supply chain manufacturing suppliers dependencies" --workdir ${workdir} --sections supply_chain --top-k 15

        2. Use available MCP tools to research key suppliers, concentration risk, and geographic exposure.

        3. Record each finding:
           uv run python skills/db.py finding-add --workdir ${workdir} --task-id research_supply_chain \
             --content "<finding>" --source "<source>" --tags supply_chain [other_relevant_tags...]

        Cross-tag relevant findings to risk_news or competitive as appropriate.
        Aim for at least 10 substantial findings.
      disallowed_tools: [WebSearch, WebFetch]

  research_financial:
    sort_order: 18
    description: Research financial performance, growth trends, and key metrics
    type: claude
    depends_on: [build_index, profile, fundamental, fetch_edgar]
    config:
      mcp_config: [mcp-research.json]
      prompt: |
        You are a research analyst investigating ${company_name} (${symbol}).
        Your domain: financial performance — revenue growth, margins, cash flow, balance sheet, and key ratios.

        1. Search the artifact index:
           Run: uv run python skills/search_index/search_index.py "revenue growth margins profitability cash flow balance sheet" --workdir ${workdir} --sections financial --top-k 15

        2. Use available MCP tools to research financial statements, TTM metrics, and trend analysis.

        3. Record each finding:
           uv run python skills/db.py finding-add --workdir ${workdir} --task-id research_financial \
             --content "<finding>" --source "<source>" --tags financial [other_relevant_tags...]

        Cross-tag findings relevant to valuation (margins, FCF) or risk_news (debt levels).
        Aim for at least 10 substantial findings.
      disallowed_tools: [WebSearch, WebFetch]

  research_valuation:
    sort_order: 18
    description: Research valuation multiples, analyst targets, and DCF inputs
    type: claude
    depends_on: [build_index, profile, fundamental, fetch_edgar]
    config:
      mcp_config: [mcp-research.json]
      prompt: |
        You are a research analyst investigating ${company_name} (${symbol}).
        Your domain: valuation — current multiples, historical ranges, analyst price targets, and DCF inputs.

        1. Search the artifact index:
           Run: uv run python skills/search_index/search_index.py "valuation P/E EV/EBITDA price target analyst" --workdir ${workdir} --sections valuation --top-k 15

        2. Use available MCP tools to research current multiples, analyst consensus, and peer comparisons.

        3. Record each finding:
           uv run python skills/db.py finding-add --workdir ${workdir} --task-id research_valuation \
             --content "<finding>" --source "<source>" --tags valuation [other_relevant_tags...]

        Cross-tag findings relevant to financial (FCF yield, EPS growth) or competitive (peer multiples).
        Aim for at least 10 substantial findings.
      disallowed_tools: [WebSearch, WebFetch]

  research_risk_news:
    sort_order: 18
    description: Research risks, recent news events, and regulatory developments
    type: claude
    depends_on: [build_index, profile, perplexity, fetch_edgar, perplexity_analysis]
    config:
      mcp_config: [mcp-research.json]
      prompt: |
        You are a research analyst investigating ${company_name} (${symbol}).
        Your domain: key risks, recent news events, regulatory developments, and catalysts.

        1. Search the artifact index:
           Run: uv run python skills/search_index/search_index.py "risks regulatory legal news events catalysts" --workdir ${workdir} --sections risk_news --top-k 15

        2. Use available MCP tools to research recent material events, risk factors, and regulatory filings.

        3. Record each finding:
           uv run python skills/db.py finding-add --workdir ${workdir} --task-id research_risk_news \
             --content "<finding>" --source "<source>" --tags risk_news [other_relevant_tags...]

        Cross-tag findings relevant to supply_chain, competitive, or valuation as appropriate.
        Aim for at least 10 substantial findings.
      disallowed_tools: [WebSearch, WebFetch]
```

### Step 2: Validate DAG

```bash
./skills/db.py validate --dag dags/sra.yaml --ticker TEST
```
Expected: status ok with correct task count.

### Step 3: Commit

```bash
git add dags/sra.yaml
git commit -m "feat: add 7 research agent tasks to DAG (research wave)"
```

---

## Task 10: Update writing tasks in dags/sra.yaml — add research dependencies and findings preamble

**Files:**
- Modify: `dags/sra.yaml` — the 7 section writing tasks

Each writing task needs:
1. All 7 `research_*` tasks added to `depends_on`
2. A preamble in the prompt instructing the agent to retrieve findings before writing

### Step 1: Update each writing task

For every writing task (`write_profile`, `write_business_model`, `write_competitive`, `write_supply_chain`, `write_financial`, `write_valuation`, `write_risk_news`):

**Add to `depends_on`:**
```yaml
depends_on: [...existing_deps..., research_profile, research_business, research_competitive, research_supply_chain, research_financial, research_valuation, research_risk_news]
```

**Prepend to each `prompt`:**
```
Before writing, retrieve research findings for your section:
  Run: uv run python skills/db.py finding-list --workdir ${workdir} --tags <section_tag>

Use these findings as your primary source. They were produced by specialist
research agents and include cross-tagged evidence from other domains.
Fall back to artifact files in artifacts/ for specific data and citations.
Do not call external tools or APIs — focus on synthesis from research findings.

---
```

Where `<section_tag>` matches the section: `profile`, `business_model`, `competitive`, `supply_chain`, `financial`, `valuation`, `risk_news`.

For writing tasks, also add `disallowed_tools` that block API calls (to enforce research-only synthesis):
```yaml
disallowed_tools: [WebSearch, WebFetch]
```

### Step 2: Validate DAG

```bash
./skills/db.py validate --dag dags/sra.yaml --ticker TEST
```

### Step 3: Commit

```bash
git add dags/sra.yaml
git commit -m "feat: update writing tasks to depend on research wave and read from findings store"
```

---

## Task 11: Install all new dependencies and verify imports

### Step 1: Install

```bash
uv add lancedb openai tiktoken mcp
```

### Step 2: Verify all imports work

```bash
uv run python -c "import lancedb; import openai; import tiktoken; import mcp; print('all imports ok')"
uv run python -c "from mcp.server import Server; from mcp.client.stdio import stdio_client, StdioServerParameters; print('mcp imports ok')"
```

If any MCP import fails, check the SDK version and update `mcp_proxy.py` imports accordingly using context7.

### Step 3: Run full non-integration test suite

```bash
uv run pytest tests/ -m "not integration" -v
```
Expected: all existing tests pass.

### Step 4: Commit

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add lancedb, openai, tiktoken, mcp dependencies"
```

---

## Task 12: End-to-end smoke test

### Step 1: Run gen_mcp_configs.py to generate research config

```bash
python scripts/gen_mcp_configs.py
```
Verify `mcp-research.json` exists and contains the expected proxied server entries.

### Step 2: Run the pipeline for a single ticker (data gathering + chunk + index only)

Temporarily mark all research and writing tasks as skipped to test just the new pipeline stages:

```bash
./research.py AAPL --date 20260307
```

After `build_index` completes:
```bash
uv run python skills/search_index/search_index.py "Who are Apple's main competitors?" --workdir work/AAPL_20260307 --top-k 5
```
Expected: returns ranked chunks from SEC filings and other text artifacts.

### Step 3: Check findings after research wave

After research wave completes:
```bash
./skills/db.py finding-list --workdir work/AAPL_20260307 | python -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d)} findings'); [print(f['tags']) for f in d[:5]]"
```
Expected: 70+ findings total, cross-tagging visible.

### Step 4: Verify cache hit behavior

```bash
sqlite3 work/AAPL_20260307/mcp-cache.db "SELECT server, tool_name, COUNT(*) as hits FROM mcp_cache GROUP BY server, tool_name ORDER BY hits DESC LIMIT 20;"
```
Any tool called by multiple research agents should show count = 1 (single fetch, multiple logical uses).

### Step 5: Run full end-to-end pipeline

```bash
./research.py NVDA --date 20260307
```

After completion, spot-check the final report:
- No contradictions between competitive and supply chain sections
- Valuation section references financial findings
- Writing tasks show no MCP tool calls in `tools.log` (only Bash calls to `db.py finding-list`)

### Step 6: Commit

```bash
git add .
git commit -m "chore: end-to-end smoke test complete — research swarm refactor working"
```
