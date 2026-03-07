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
