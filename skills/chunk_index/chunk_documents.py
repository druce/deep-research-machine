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
