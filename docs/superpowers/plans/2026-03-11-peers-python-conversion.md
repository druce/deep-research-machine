# Peers Task: Convert to Pure Python

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the slow Claude-orchestrated peers task graph (T1 fetch providers, T2 Claude web research, T3 Claude selection) with a single pure-Python script that fetches candidates from multiple providers, enriches them via yfinance, eliminates bad tickers (private/foreign/no-data), scores comparability, and selects the best peers.

**Architecture:** One new script `skills/identify_peers/identify_peers.py` (rewrite in place) with sequential functions mirroring the old T1/T2/T3 graph. T1 (fetch from Finnhub/FMP) stays as-is. T2 (Claude web research) is replaced by fetching sector/industry peers from yfinance. T3 (Claude selection) is replaced by a Python scoring function that ranks candidates on business similarity, scale proximity, and margin profile — then eliminates any candidate that couldn't be enriched (private, foreign ADR with no data, bad ticker). The existing `fetch_provider_peers.py` and `plan_template.md` are deleted; all logic lives in the single script.

**Tech Stack:** Python 3, yfinance, finnhub, openbb, argparse, pathlib

**Output contract (unchanged):** `artifacts/peers_list.json` with shape `{"symbol": [...], "name": [...], "price": [...], "market_cap": [...], "provider": "...", "filtered": true, "filter_rationale": "..."}`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Rewrite | `skills/identify_peers/identify_peers.py` | Single script: fetch candidates, enrich, filter, score, select, output |
| Delete | `skills/identify_peers/fetch_provider_peers.py` | Absorbed into `identify_peers.py` |
| Delete | `skills/identify_peers/plan_template.md` | No longer needed (no Claude task graph) |
| Modify | `skills/identify_peers/identify_peers.md` | Update description (remove Claude/task-graph references) |
| Create | `tests/test_identify_peers.py` | Unit tests for scoring, filtering, enrichment |
| No change | `dags/sra.yaml` | `peers` task already points to `skills/identify_peers/identify_peers.py` |
| No change | `skills/config.py` | Already has `MAX_PEERS_TO_FETCH`, `MAX_PEERS_IN_REPORT`, `TEMP_DIR` |

---

## Chunk 1: Core Implementation

### Task 1: Write failing tests for candidate fetching

**Files:**
- Create: `tests/test_identify_peers.py`

- [ ] **Step 1: Create test file with tests for Finnhub and OpenBB fetchers**

```python
#!/usr/bin/env python3
"""Tests for identify_peers skill."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add skills directory to path
_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

from identify_peers.identify_peers import (  # noqa: E402
    fetch_finnhub_peers,
    fetch_openbb_peers,
    fetch_yfinance_sector_peers,
    enrich_candidates,
    filter_bad_tickers,
    score_and_rank,
    select_peers,
)


class TestFetchFinnhubPeers:
    """Tests for Finnhub peer fetching."""

    @patch("identify_peers.identify_peers.finnhub")
    def test_returns_peer_symbols(self, mock_finnhub):
        mock_client = MagicMock()
        mock_client.company_peers.return_value = ["AAPL", "MSFT", "GOOG", "TSLA"]
        mock_finnhub.Client.return_value = mock_client

        symbols, source = fetch_finnhub_peers("NVDA", api_key="fake")
        assert symbols == ["AAPL", "MSFT", "GOOG"]  # excludes self if present
        assert source == "Finnhub"

    @patch("identify_peers.identify_peers.finnhub")
    def test_excludes_target_symbol(self, mock_finnhub):
        mock_client = MagicMock()
        mock_client.company_peers.return_value = ["NVDA", "AAPL", "MSFT"]
        mock_finnhub.Client.return_value = mock_client

        symbols, source = fetch_finnhub_peers("NVDA", api_key="fake")
        assert "NVDA" not in symbols

    def test_returns_none_without_api_key(self):
        symbols, error = fetch_finnhub_peers("NVDA", api_key=None)
        assert symbols is None
        assert "not set" in error.lower() or "api_key" in error.lower()


class TestFilterBadTickers:
    """Tests for eliminating unenrichable peers."""

    def test_removes_peers_with_no_market_cap(self):
        candidates = [
            {"ticker": "AAPL", "name": "Apple", "market_cap": 3_000_000_000_000, "price": 190.0},
            {"ticker": "PRIV", "name": "PRIV", "market_cap": None, "price": None},
            {"ticker": "BAD", "name": "BAD", "market_cap": None, "price": 0.0},
        ]
        filtered = filter_bad_tickers(candidates)
        assert len(filtered) == 1
        assert filtered[0]["ticker"] == "AAPL"

    def test_removes_peers_with_no_name_resolved(self):
        """Peers where yfinance returned only the ticker as name and no data."""
        candidates = [
            {"ticker": "AAPL", "name": "Apple Inc.", "market_cap": 3e12, "price": 190.0},
            {"ticker": "XYZ", "name": "XYZ", "market_cap": None, "price": None},
        ]
        filtered = filter_bad_tickers(candidates)
        assert len(filtered) == 1

    def test_keeps_valid_peers(self):
        candidates = [
            {"ticker": "AAPL", "name": "Apple Inc.", "market_cap": 3e12, "price": 190.0},
            {"ticker": "MSFT", "name": "Microsoft Corp", "market_cap": 2.8e12, "price": 410.0},
        ]
        filtered = filter_bad_tickers(candidates)
        assert len(filtered) == 2


class TestScoreAndRank:
    """Tests for the comparability scoring function."""

    def test_closer_market_cap_scores_higher(self):
        target = {"market_cap": 1_000_000_000, "sector": "Technology", "industry": "Software"}
        candidates = [
            {"ticker": "A", "name": "A", "market_cap": 900_000_000, "sector": "Technology", "industry": "Software",
             "gross_margins": 0.7, "operating_margins": 0.2},
            {"ticker": "B", "name": "B", "market_cap": 100_000_000_000, "sector": "Technology", "industry": "Software",
             "gross_margins": 0.7, "operating_margins": 0.2},
        ]
        ranked = score_and_rank(target, candidates)
        assert ranked[0]["ticker"] == "A"

    def test_same_industry_scores_higher(self):
        target = {"market_cap": 1e9, "sector": "Technology", "industry": "Semiconductors"}
        candidates = [
            {"ticker": "A", "name": "A", "market_cap": 1e9, "sector": "Technology", "industry": "Semiconductors",
             "gross_margins": 0.5, "operating_margins": 0.2},
            {"ticker": "B", "name": "B", "market_cap": 1e9, "sector": "Healthcare", "industry": "Pharma",
             "gross_margins": 0.5, "operating_margins": 0.2},
        ]
        ranked = score_and_rank(target, candidates)
        assert ranked[0]["ticker"] == "A"


class TestSelectPeers:
    """Tests for the top-level select_peers function."""

    def test_output_format_matches_contract(self):
        """The output dict must have symbol/name/price/market_cap lists + metadata."""
        ranked = [
            {"ticker": "AAPL", "name": "Apple", "price": 190.0, "market_cap": 3e12, "_score": 0.9},
            {"ticker": "MSFT", "name": "Microsoft", "price": 410.0, "market_cap": 2.8e12, "_score": 0.8},
        ]
        result = select_peers(ranked, count=2)
        assert isinstance(result["symbol"], list)
        assert isinstance(result["name"], list)
        assert isinstance(result["price"], list)
        assert isinstance(result["market_cap"], list)
        assert len(result["symbol"]) == 2
        assert result["filtered"] is True

    def test_respects_count_limit(self):
        ranked = [{"ticker": f"T{i}", "name": f"N{i}", "price": 100.0, "market_cap": 1e9, "_score": 1.0 - i * 0.1}
                  for i in range(10)]
        result = select_peers(ranked, count=5)
        assert len(result["symbol"]) == 5
```

- [ ] **Step 2: Run tests to verify they fail (module not yet rewritten)**

Run: `cd /Users/drucev/projects/sra5 && uv run pytest tests/test_identify_peers.py -v 2>&1 | head -40`
Expected: ImportError — the new function names don't exist yet.

- [ ] **Step 3: Commit test file**

```bash
git add tests/test_identify_peers.py
git commit -m "test: add unit tests for pure-Python peers identification"
```

---

### Task 2: Rewrite identify_peers.py as pure Python

**Files:**
- Rewrite: `skills/identify_peers/identify_peers.py`

The new script has these functions, executed in order (mirroring the old T1→T2→T3 graph):

| Function | Replaces | What it does |
|----------|----------|-------------|
| `fetch_finnhub_peers()` | T1 (Finnhub part of `fetch_provider_peers.py`) | Fetch peer tickers from Finnhub API |
| `fetch_openbb_peers()` | T1 (FMP/OpenBB part of `fetch_provider_peers.py`) | Fetch peer tickers from OpenBB/FMP |
| `fetch_yfinance_sector_peers()` | T2 (Claude web research) | Get sector/industry peers from yfinance screener or known-ticker lookup |
| `enrich_candidates()` | T1 enrichment + old `_enrich_peers_yfinance()` | Enrich all unique candidate tickers with yfinance data |
| `filter_bad_tickers()` | **NEW** — the key improvement | Remove candidates with no market_cap, no price, or name==ticker (private/foreign/bad) |
| `score_and_rank()` | T3 (Claude selection) | Score each candidate on scale proximity, sector/industry match, margin similarity |
| `select_peers()` | old `convert_to_peers_list()` | Take top N, format into column-oriented output dict |

- [ ] **Step 4: Write the new identify_peers.py**

```python
#!/usr/bin/env python3
"""
Peer Identification Skill — identify_peers.py

Identifies the most comparable peer companies for a given ticker by:
1. Fetching candidate peers from Finnhub and OpenBB/FMP
2. Supplementing with yfinance sector/industry peers
3. Enriching all candidates with yfinance fundamental data
4. Filtering out bad tickers (private, foreign with no data, invalid)
5. Scoring and ranking by comparability (scale, sector, margins)
6. Selecting the top N peers

Usage:
    ./skills/identify_peers/identify_peers.py SYMBOL [--count 5] [--workdir DIR]

Output:
    - {workdir}/artifacts/peers_list.json — column-oriented peer list
    Prints JSON manifest to stdout.
    All progress/diagnostic output goes to stderr.

Exit codes:
    0 - success
    2 - failure
"""

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yfinance as yf

# Add skills directory to path for local imports
_SKILLS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

from config import MAX_PEERS_TO_FETCH  # noqa: E402
from utils import (  # noqa: E402
    setup_logging,
    validate_symbol,
    ensure_directory,
    format_currency,
    load_environment,
    default_workdir,
)

load_environment()
logger = setup_logging(__name__)


# ---------------------------------------------------------------------------
# Step 1: Fetch candidate peer tickers from providers
# ---------------------------------------------------------------------------

def fetch_finnhub_peers(
    symbol: str,
    *,
    api_key: Optional[str] = None,
) -> Tuple[Optional[List[str]], str]:
    """
    Fetch peer symbols from Finnhub.

    Args:
        symbol: Target ticker.
        api_key: Finnhub API key (reads env if None).

    Returns:
        (list_of_symbols, source_or_error_string).
        First element is None on failure.
    """
    api_key = api_key or os.getenv("FINNHUB_API_KEY")
    if not api_key:
        return None, "FINNHUB_API_KEY not set"
    try:
        import finnhub
        client = finnhub.Client(api_key=api_key)
        peers = client.company_peers(symbol)
        peers = [s for s in (peers or []) if s != symbol]
        if not peers:
            return None, "Finnhub returned no peers"
        logger.info(f"Finnhub returned {len(peers)} peers")
        return peers[:MAX_PEERS_TO_FETCH], "Finnhub"
    except Exception as e:
        return None, f"Finnhub error: {e}"


def fetch_openbb_peers(
    symbol: str,
) -> Tuple[Optional[List[str]], str]:
    """
    Fetch peer symbols from OpenBB/FMP.

    Args:
        symbol: Target ticker.

    Returns:
        (list_of_symbols, source_or_error_string).
    """
    pat = os.getenv("OPENBB_PAT")
    if not pat:
        return None, "OPENBB_PAT not set"
    try:
        from openbb import obb
        obb.user.credentials.openbb_pat = pat
        result = obb.equity.compare.peers(symbol=symbol, provider="fmp")
        data = result.to_dict()
        peer_symbols: List[str] = []
        if isinstance(data, dict):
            for key in ("peers_list", "symbol", "peers"):
                if key in data:
                    val = data[key]
                    if isinstance(val, list):
                        peer_symbols = val
                        break
        if peer_symbols and isinstance(peer_symbols[0], list):
            peer_symbols = [s for sub in peer_symbols for s in sub]
        peer_symbols = [s for s in peer_symbols if isinstance(s, str) and s != symbol]
        if not peer_symbols:
            return None, "OpenBB/FMP returned no peers"
        logger.info(f"OpenBB/FMP returned {len(peer_symbols)} peers")
        return peer_symbols[:MAX_PEERS_TO_FETCH], "OpenBB/FMP"
    except Exception as e:
        return None, f"OpenBB/FMP error: {e}"


def fetch_yfinance_sector_peers(
    symbol: str,
    sector: str,
    industry: str,
) -> Tuple[Optional[List[str]], str]:
    """
    Fetch additional sector/industry peer candidates via yfinance recommendations.

    Uses yfinance's built-in recommendations/similar tickers as a supplementary
    source. This replaces the old Claude web-research step (T2).

    Args:
        symbol: Target ticker.
        sector: Target company's sector.
        industry: Target company's industry.

    Returns:
        (list_of_symbols, source_or_error_string).
    """
    try:
        ticker = yf.Ticker(symbol)
        # yfinance exposes recommendations which often include peer companies
        recs = []
        try:
            rec_df = ticker.recommendations
            if rec_df is not None and not rec_df.empty and "symbol" in rec_df.columns:
                recs = rec_df["symbol"].dropna().unique().tolist()
        except Exception:
            pass

        # Also try .info peers if available (some yfinance versions)
        info_peers = []
        try:
            info = ticker.info
            # Some versions return recommendedSymbols
            rec_symbols = info.get("recommendedSymbols", [])
            if rec_symbols:
                info_peers = [r.get("symbol") for r in rec_symbols if r.get("symbol")]
        except Exception:
            pass

        combined = list(dict.fromkeys(recs + info_peers))  # dedupe, preserve order
        combined = [s for s in combined if s != symbol]

        if not combined:
            return None, "yfinance returned no sector peers"

        logger.info(f"yfinance returned {len(combined)} sector/recommendation peers")
        return combined[:MAX_PEERS_TO_FETCH], "yfinance"
    except Exception as e:
        return None, f"yfinance sector peers error: {e}"


# ---------------------------------------------------------------------------
# Step 2: Enrich candidates with fundamental data
# ---------------------------------------------------------------------------

def enrich_candidates(
    symbols: List[str],
) -> List[Dict]:
    """
    Enrich a list of ticker symbols with yfinance fundamental data.

    Fetches: name, sector, industry, market_cap, price, revenue,
    gross_margins, operating_margins for each symbol.

    Args:
        symbols: List of unique ticker symbols to enrich.

    Returns:
        List of dicts, one per symbol. Fields may be None if yfinance
        returned no data (these get filtered out in the next step).
    """
    enriched = []
    for sym in symbols:
        try:
            info = yf.Ticker(sym).info
            enriched.append({
                "ticker": sym,
                "name": info.get("longName") or info.get("shortName", sym),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "revenue": info.get("totalRevenue"),
                "gross_margins": info.get("grossMargins"),
                "operating_margins": info.get("operatingMargins"),
            })
            logger.info(f"  Enriched {sym}: {enriched[-1]['name']}")
        except Exception as e:
            logger.warning(f"  Could not enrich {sym}: {e}")
            enriched.append({
                "ticker": sym,
                "name": sym,
                "sector": None,
                "industry": None,
                "market_cap": None,
                "price": None,
                "revenue": None,
                "gross_margins": None,
                "operating_margins": None,
            })
        time.sleep(0.15)  # rate-limit courtesy
    return enriched


# ---------------------------------------------------------------------------
# Step 3: Filter out bad tickers
# ---------------------------------------------------------------------------

def filter_bad_tickers(candidates: List[Dict]) -> List[Dict]:
    """
    Remove candidates that could not be enriched — private companies,
    foreign tickers with no US data, delisted tickers, or bad symbols.

    A candidate is removed if:
    - market_cap is None (no valuation data available)
    - price is None or 0 (not actively traded / no data)
    - name equals the ticker symbol (yfinance couldn't resolve a real name)

    Args:
        candidates: Enriched candidate dicts from enrich_candidates().

    Returns:
        Filtered list with only valid, data-rich candidates.
    """
    filtered = []
    removed = []
    for c in candidates:
        has_market_cap = c.get("market_cap") is not None
        has_price = c.get("price") is not None and c.get("price", 0) > 0
        name_resolved = c.get("name", c["ticker"]) != c["ticker"]

        if has_market_cap and has_price:
            filtered.append(c)
        else:
            reasons = []
            if not has_market_cap:
                reasons.append("no market cap")
            if not has_price:
                reasons.append("no price")
            if not name_resolved:
                reasons.append("name not resolved")
            removed.append((c["ticker"], ", ".join(reasons)))

    if removed:
        logger.info(f"Filtered out {len(removed)} bad tickers:")
        for sym, reason in removed:
            logger.info(f"  {sym}: {reason}")

    return filtered


# ---------------------------------------------------------------------------
# Step 4: Score and rank by comparability
# ---------------------------------------------------------------------------

def score_and_rank(
    target: Dict,
    candidates: List[Dict],
) -> List[Dict]:
    """
    Score each candidate on comparability to the target company.

    Scoring dimensions (each 0.0-1.0, weighted):
    - Scale proximity (40%): log-ratio of market caps, closer = higher
    - Industry match (30%): same industry > same sector > different
    - Margin similarity (30%): absolute difference in gross + operating margins

    Args:
        target: Dict with target's market_cap, sector, industry,
                gross_margins, operating_margins.
        candidates: Enriched and filtered candidate dicts.

    Returns:
        Candidates sorted by _score descending (best first).
        Each dict gets a "_score" key added.
    """
    target_mcap = target.get("market_cap") or 1
    target_sector = (target.get("sector") or "").lower()
    target_industry = (target.get("industry") or "").lower()
    target_gm = target.get("gross_margins") or 0
    target_om = target.get("operating_margins") or 0

    for c in candidates:
        # Scale score: 1.0 when same size, drops with log-distance
        c_mcap = c.get("market_cap") or 1
        log_ratio = abs(math.log10(max(c_mcap, 1) / max(target_mcap, 1)))
        scale_score = max(0.0, 1.0 - log_ratio / 3.0)  # 3 orders of magnitude = 0

        # Industry score
        c_sector = (c.get("sector") or "").lower()
        c_industry = (c.get("industry") or "").lower()
        if c_industry and c_industry == target_industry:
            industry_score = 1.0
        elif c_sector and c_sector == target_sector:
            industry_score = 0.5
        else:
            industry_score = 0.0

        # Margin score
        c_gm = c.get("gross_margins") or 0
        c_om = c.get("operating_margins") or 0
        gm_diff = abs(c_gm - target_gm)
        om_diff = abs(c_om - target_om)
        margin_score = max(0.0, 1.0 - (gm_diff + om_diff))

        c["_score"] = round(0.4 * scale_score + 0.3 * industry_score + 0.3 * margin_score, 4)

    candidates.sort(key=lambda c: c["_score"], reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# Step 5: Select top N and format output
# ---------------------------------------------------------------------------

def select_peers(
    ranked: List[Dict],
    count: int,
) -> Dict:
    """
    Take the top N ranked candidates and format into the column-oriented
    output dict expected by downstream tasks.

    Args:
        ranked: Scored and sorted candidate list (best first).
        count: Number of peers to select.

    Returns:
        Dict with keys: symbol, name, price, market_cap (each a list),
        plus provider, filtered, filter_rationale metadata.
    """
    selected = ranked[:count]
    peer_names = ", ".join(c["ticker"] for c in selected)
    return {
        "symbol": [c["ticker"] for c in selected],
        "name": [c["name"] for c in selected],
        "price": [round(float(c["price"]), 2) if c.get("price") else None for c in selected],
        "market_cap": [c.get("market_cap") for c in selected],
        "provider": "identify_peers",
        "filtered": True,
        "filter_rationale": (
            f"Top {len(selected)} peers selected by comparability scoring "
            f"(scale proximity, industry match, margin similarity) "
            f"from {len(ranked)} enriched candidates after filtering bad tickers"
        ),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def get_target_profile(symbol: str) -> Dict:
    """
    Fetch target company profile from yfinance.

    Args:
        symbol: Validated ticker symbol.

    Returns:
        Dict with ticker, name, sector, industry, market_cap, revenue, margins.
    """
    logger.info(f"Fetching target profile for {symbol}...")
    info = yf.Ticker(symbol).info
    return {
        "ticker": symbol,
        "name": info.get("longName") or info.get("shortName", symbol),
        "sector": info.get("sector", "N/A"),
        "industry": info.get("industry", "N/A"),
        "market_cap": info.get("marketCap"),
        "revenue": info.get("totalRevenue"),
        "gross_margins": info.get("grossMargins"),
        "operating_margins": info.get("operatingMargins"),
    }


def main() -> int:
    """
    CLI entry point. Orchestrates the peer identification pipeline.

    Returns:
        Exit code: 0 (success), 2 (failure).
    """
    parser = argparse.ArgumentParser(
        description="Identify the most comparable peer companies for a given ticker"
    )
    parser.add_argument("symbol", help="Stock ticker symbol")
    parser.add_argument(
        "--count", type=int, default=5,
        help="Number of peers to select (default: 5)"
    )
    parser.add_argument(
        "--workdir", default=None,
        help="Work directory (default: work/SYMBOL_YYYYMMDD)"
    )
    args = parser.parse_args()

    try:
        symbol = validate_symbol(args.symbol)
    except ValueError as e:
        manifest = {"status": "error", "artifacts": [], "error": str(e)}
        print(json.dumps(manifest, indent=2))
        return 2

    workdir = Path(args.workdir or default_workdir(symbol))
    artifacts_dir = ensure_directory(workdir / "artifacts")
    count = args.count

    logger.info(f"{'=' * 60}")
    logger.info(f"Identify Peers: {symbol} (selecting {count})")
    logger.info(f"Work directory: {workdir}")
    logger.info(f"{'=' * 60}")

    # ---- Fetch target profile ----
    try:
        target = get_target_profile(symbol)
    except Exception as e:
        logger.error(f"Failed to fetch target profile: {e}")
        print(json.dumps({"status": "error", "artifacts": [], "error": str(e)}))
        return 2

    logger.info(
        f"Target: {target['name']} | {target['industry']} | "
        f"Market cap {format_currency(target['market_cap']) if target.get('market_cap') else 'N/A'}"
    )

    # ---- Step 1: Gather candidate tickers from all sources ----
    all_symbols: List[str] = []
    sources_used: List[str] = []

    # Finnhub
    finnhub_peers, finnhub_src = fetch_finnhub_peers(symbol)
    if finnhub_peers:
        all_symbols.extend(finnhub_peers)
        sources_used.append(f"Finnhub ({len(finnhub_peers)})")
    else:
        logger.warning(f"Finnhub: {finnhub_src}")

    # OpenBB/FMP
    openbb_peers, openbb_src = fetch_openbb_peers(symbol)
    if openbb_peers:
        all_symbols.extend(openbb_peers)
        sources_used.append(f"OpenBB/FMP ({len(openbb_peers)})")
    else:
        logger.warning(f"OpenBB/FMP: {openbb_src}")

    # yfinance sector peers (replaces Claude web research)
    yf_peers, yf_src = fetch_yfinance_sector_peers(
        symbol, target.get("sector", ""), target.get("industry", "")
    )
    if yf_peers:
        all_symbols.extend(yf_peers)
        sources_used.append(f"yfinance ({len(yf_peers)})")
    else:
        logger.warning(f"yfinance: {yf_src}")

    # Deduplicate, preserving order
    seen = set()
    unique_symbols = []
    for s in all_symbols:
        s_upper = s.upper()
        if s_upper not in seen and s_upper != symbol:
            seen.add(s_upper)
            unique_symbols.append(s_upper)

    logger.info(f"Collected {len(unique_symbols)} unique candidates from: {', '.join(sources_used)}")

    if not unique_symbols:
        logger.error("No candidate peers found from any source")
        print(json.dumps({"status": "error", "artifacts": [], "error": "No candidates found"}))
        return 2

    # ---- Step 2: Enrich all candidates ----
    logger.info(f"Enriching {len(unique_symbols)} candidates with yfinance data...")
    enriched = enrich_candidates(unique_symbols)

    # ---- Step 3: Filter bad tickers ----
    valid = filter_bad_tickers(enriched)
    logger.info(f"{len(valid)} candidates remain after filtering ({len(enriched) - len(valid)} removed)")

    if not valid:
        logger.error("No valid candidates after filtering")
        print(json.dumps({"status": "error", "artifacts": [], "error": "All candidates filtered out"}))
        return 2

    # ---- Step 4: Score and rank ----
    ranked = score_and_rank(target, valid)
    for i, c in enumerate(ranked[:10]):
        logger.info(f"  #{i+1} {c['ticker']:6s} score={c['_score']:.3f} mcap={format_currency(c.get('market_cap'))}")

    # ---- Step 5: Select and output ----
    peers_list = select_peers(ranked, count)
    peer_count = len(peers_list["symbol"])

    output_path = artifacts_dir / "peers_list.json"
    with output_path.open("w") as f:
        json.dump(peers_list, f, indent=2, default=str)
    logger.info(f"Wrote {output_path}")

    peer_names = ", ".join(peers_list["symbol"])
    manifest = {
        "status": "complete",
        "artifacts": [{
            "name": "peers_list",
            "path": "artifacts/peers_list.json",
            "format": "json",
            "description": f"{peer_count} peer companies for {symbol}: {peer_names}",
        }],
        "error": None,
    }
    print(json.dumps(manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/drucev/projects/sra5 && uv run pytest tests/test_identify_peers.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/identify_peers/identify_peers.py tests/test_identify_peers.py
git commit -m "feat: rewrite identify_peers as pure Python (no Claude subprocess)"
```

---

### Task 3: Delete obsolete files and update frontmatter

**Files:**
- Delete: `skills/identify_peers/fetch_provider_peers.py`
- Delete: `skills/identify_peers/plan_template.md`
- Modify: `skills/identify_peers/identify_peers.md`

- [ ] **Step 7: Delete fetch_provider_peers.py and plan_template.md**

```bash
git rm skills/identify_peers/fetch_provider_peers.py
git rm skills/identify_peers/plan_template.md
```

- [ ] **Step 8: Update identify_peers.md frontmatter**

Replace the contents of `skills/identify_peers/identify_peers.md` with:

```markdown
---
name: identify_peers
description: Identify comparable peer companies using provider APIs and yfinance data
type: python
---

# identify_peers

Fetches candidate peers from Finnhub, OpenBB/FMP, and yfinance, enriches each
with fundamental data, filters out bad tickers (private, foreign, no data),
scores by comparability (scale, industry, margins), and selects the top N.

## Usage

```bash
./skills/identify_peers/identify_peers.py SYMBOL [--count 5] [--workdir DIR]
```

## Outputs

- `artifacts/peers_list.json` — column-oriented peer list with symbol, name, price, market_cap
```

- [ ] **Step 9: Run full test suite to verify nothing breaks**

Run: `cd /Users/drucev/projects/sra5 && uv run pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: All tests pass, no import errors from deleted files.

- [ ] **Step 10: Commit cleanup**

```bash
git add -A skills/identify_peers/ tests/
git commit -m "chore: delete obsolete fetch_provider_peers.py and plan_template.md"
```

---

### Task 4: Smoke test with a real ticker

- [ ] **Step 11: Run the script end-to-end**

```bash
cd /Users/drucev/projects/sra5
mkdir -p work/TEST_20260311
uv run python skills/identify_peers/identify_peers.py AAPL --workdir work/TEST_20260311 --count 5
```

Expected: JSON manifest on stdout with status "complete" and 5 peers. Stderr shows enrichment progress and the filtering/scoring log. Verify `work/TEST_20260311/artifacts/peers_list.json` has the correct shape.

- [ ] **Step 12: Verify output format matches downstream expectations**

```bash
cd /Users/drucev/projects/sra5
python3 -c "
import json
data = json.load(open('work/TEST_20260311/artifacts/peers_list.json'))
assert isinstance(data['symbol'], list), 'symbol must be a list'
assert isinstance(data['name'], list), 'name must be a list'
assert isinstance(data['price'], list), 'price must be a list'
assert isinstance(data['market_cap'], list), 'market_cap must be a list'
assert len(data['symbol']) == 5, f'expected 5 peers, got {len(data[\"symbol\"])}'
assert data['filtered'] is True
print('Output format OK')
print('Peers:', list(zip(data['symbol'], data['name'])))
"
```

- [ ] **Step 13: Clean up test directory**

```bash
rm -rf work/TEST_20260311
```

- [ ] **Step 14: Final commit if any tweaks were needed**

```bash
# Only if smoke test revealed issues that needed fixing
git add skills/identify_peers/identify_peers.py tests/test_identify_peers.py
git commit -m "fix: address issues found during peers smoke test"
```
