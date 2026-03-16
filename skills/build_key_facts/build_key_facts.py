#!/usr/bin/env python3
"""
Extract authoritative financial metrics from structured artifacts into key_facts.json.

Reads CSV/JSON artifacts produced by fetch_fundamental, fetch_profile, and fetch_edgar,
then outputs a single JSON file with verified metrics that research agents use as
ground truth. Each value carries its source file for traceability.

Usage:
    ./skills/build_key_facts/build_key_facts.py SYMBOL --workdir DIR

Output (stdout):  JSON manifest {"status": "complete", "artifacts": [...]}
Output (files):   artifacts/key_facts.json
"""
import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

# Add skills/ to path so we can import shared utilities
_SKILLS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

from utils import setup_logging, validate_symbol, ensure_directory  # noqa: E402

logger = setup_logging(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(value: Optional[float], prefix: str = "$", suffix: str = "") -> str:
    """Format a number for human display."""
    if value is None:
        return "N/A"
    abs_val = abs(value)
    sign = "-" if value < 0 else ""
    if abs_val >= 1e12:
        return f"{sign}{prefix}{abs_val / 1e12:.2f}T{suffix}"
    if abs_val >= 1e9:
        return f"{sign}{prefix}{abs_val / 1e9:.1f}B{suffix}"
    if abs_val >= 1e6:
        return f"{sign}{prefix}{abs_val / 1e6:.1f}M{suffix}"
    if abs_val >= 1e3:
        return f"{sign}{prefix}{abs_val / 1e3:.1f}K{suffix}"
    return f"{sign}{prefix}{abs_val:.2f}{suffix}"


def _pct(value: Optional[float]) -> str:
    """Format a ratio as percentage."""
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def _safe_float(val: Any) -> Optional[float]:
    """Safely convert a value to float, returning None on failure."""
    if val is None or val == "" or val == "N/A":
        return None
    try:
        # Handle comma-formatted numbers from key_ratios.csv
        if isinstance(val, str):
            val = val.replace(",", "").replace("$", "").replace("%", "")
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Safe division returning None if either operand is None or divisor is zero."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def _metric(value: Optional[float], display: str, period: str, source: str) -> dict:
    """Build a metric dict."""
    return {"value": value, "display": display, "period": period, "source": source}


# ---------------------------------------------------------------------------
# CSV readers — CSVs have metric names as first column, dates as column headers
# ---------------------------------------------------------------------------

def _read_row_csv(path: Path) -> dict[str, dict[str, Optional[float]]]:
    """Read a row-oriented CSV (metric rows × date columns).

    Returns {metric_name: {date_col: float_value, ...}, ...}
    """
    result: dict[str, dict[str, Optional[float]]] = {}
    with open(path, newline="") as f:
        reader = csv.reader(f)
        headers = next(reader)  # first row is dates
        for row in reader:
            if not row or not row[0]:
                continue
            metric = row[0]
            result[metric] = {}
            for i, date_col in enumerate(headers[1:], start=1):
                if i < len(row):
                    result[metric][date_col] = _safe_float(row[i])
    return result


def _latest_col(data: dict[str, dict[str, Optional[float]]]) -> str:
    """Get the latest (leftmost) date column from row-CSV data."""
    if not data:
        return ""
    first_metric = next(iter(data.values()))
    cols = list(first_metric.keys())
    return cols[0] if cols else ""


def _get(data: dict[str, dict[str, Optional[float]]], metric: str, col: str) -> Optional[float]:
    """Get a value from row-CSV data."""
    return data.get(metric, {}).get(col)


def _read_key_ratios(path: Path) -> dict[str, dict[str, Any]]:
    """Read key_ratios.csv (Category, Metric, TICKER1, TICKER2, ...).

    Returns {ticker: {metric: value, ...}, ...}
    """
    result: dict[str, dict[str, Any]] = {}
    with open(path, newline="") as f:
        reader = csv.reader(f)
        headers = next(reader)  # Category, Metric, NVDA, TSM, ...
        tickers = headers[2:]
        for ticker in tickers:
            result[ticker] = {}
        for row in reader:
            if len(row) < 3:
                continue
            metric = row[1]
            for i, ticker in enumerate(tickers, start=2):
                if i < len(row):
                    val = row[i]
                    # Try float, else keep as string
                    fval = _safe_float(val)
                    result[ticker][metric] = fval if fval is not None else val
    return result


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------

def _extract_financials(artifacts: Path) -> dict:
    """Extract income statement metrics."""
    path = artifacts / "income_statement.csv"
    if not path.exists():
        logger.warning("income_statement.csv not found")
        return {}

    data = _read_row_csv(path)
    col = _latest_col(data)
    if not col:
        return {}

    # Derive fiscal year from date column (e.g., "2026-01-31" → "FY2026")
    fy = f"FY{col[:4]}"
    src = "income_statement.csv"

    revenue = _get(data, "Total Revenue", col)
    gross_profit = _get(data, "Gross Profit", col)
    cost_of_revenue = _get(data, "Cost Of Revenue", col)
    operating_income = _get(data, "Operating Income", col)
    operating_expense = _get(data, "Operating Expense", col)
    net_income = _get(data, "Net Income", col)
    ebitda = _get(data, "EBITDA", col)
    normalized_ebitda = _get(data, "Normalized EBITDA", col)
    rd = _get(data, "Research And Development", col)
    sga = _get(data, "Selling General And Administration", col)
    diluted_eps = _get(data, "Diluted EPS", col)
    diluted_shares = _get(data, "Diluted Average Shares", col)
    tax_provision = _get(data, "Tax Provision", col)
    pretax_income = _get(data, "Pretax Income", col)
    interest_expense = _get(data, "Interest Expense", col)
    interest_income = _get(data, "Interest Income", col)
    depreciation = _get(data, "Reconciled Depreciation", col)
    total_expenses = _get(data, "Total Expenses", col)

    gross_margin = _safe_div(gross_profit, revenue)
    operating_margin = _safe_div(operating_income, revenue)
    net_margin = _safe_div(net_income, revenue)
    effective_tax_rate = _safe_div(tax_provision, pretax_income)
    rd_pct = _safe_div(rd, revenue)

    # Prior year for YoY growth
    cols = list(next(iter(data.values())).keys())
    prev_col = cols[1] if len(cols) > 1 else None
    prev_revenue = _get(data, "Total Revenue", prev_col) if prev_col else None
    prev_net_income = _get(data, "Net Income", prev_col) if prev_col else None
    revenue_growth = _safe_div((revenue - prev_revenue), prev_revenue) if revenue and prev_revenue else None
    ni_growth = _safe_div((net_income - prev_net_income), prev_net_income) if net_income and prev_net_income else None

    return {
        "revenue": _metric(revenue, _fmt(revenue), fy, src),
        "cost_of_revenue": _metric(cost_of_revenue, _fmt(cost_of_revenue), fy, src),
        "gross_profit": _metric(gross_profit, _fmt(gross_profit), fy, src),
        "gross_margin": _metric(gross_margin, _pct(gross_margin), fy, f"computed from {src}"),
        "operating_income": _metric(operating_income, _fmt(operating_income), fy, src),
        "operating_expense": _metric(operating_expense, _fmt(operating_expense), fy, src),
        "operating_margin": _metric(operating_margin, _pct(operating_margin), fy, f"computed from {src}"),
        "net_income": _metric(net_income, _fmt(net_income), fy, src),
        "net_margin": _metric(net_margin, _pct(net_margin), fy, f"computed from {src}"),
        "ebitda": _metric(ebitda, _fmt(ebitda), fy, src),
        "normalized_ebitda": _metric(normalized_ebitda, _fmt(normalized_ebitda), fy, src),
        "r_and_d": _metric(rd, _fmt(rd), fy, src),
        "r_and_d_pct_revenue": _metric(rd_pct, _pct(rd_pct), fy, f"computed from {src}"),
        "sga": _metric(sga, _fmt(sga), fy, src),
        "total_expenses": _metric(total_expenses, _fmt(total_expenses), fy, src),
        "diluted_eps": _metric(diluted_eps, f"${diluted_eps}" if diluted_eps else "N/A", fy, src),
        "diluted_shares": _metric(diluted_shares, _fmt(diluted_shares, prefix="", suffix=" shares"), fy, src),
        "tax_provision": _metric(tax_provision, _fmt(tax_provision), fy, src),
        "effective_tax_rate": _metric(effective_tax_rate, _pct(effective_tax_rate), fy, f"computed from {src}"),
        "pretax_income": _metric(pretax_income, _fmt(pretax_income), fy, src),
        "interest_expense": _metric(interest_expense, _fmt(interest_expense), fy, src),
        "interest_income": _metric(interest_income, _fmt(interest_income), fy, src),
        "depreciation": _metric(depreciation, _fmt(depreciation), fy, src),
        "revenue_yoy_growth": _metric(revenue_growth, _pct(revenue_growth), fy, f"computed from {src}"),
        "net_income_yoy_growth": _metric(ni_growth, _pct(ni_growth), fy, f"computed from {src}"),
    }


def _extract_balance_sheet(artifacts: Path) -> dict:
    """Extract balance sheet metrics."""
    path = artifacts / "balance_sheet.csv"
    if not path.exists():
        logger.warning("balance_sheet.csv not found")
        return {}

    data = _read_row_csv(path)
    col = _latest_col(data)
    fy = f"FY{col[:4]}"
    src = "balance_sheet.csv"

    total_assets = _get(data, "Total Assets", col)
    total_equity = _get(data, "Stockholders Equity", col)
    total_debt = _get(data, "Total Debt", col)
    cash = _get(data, "Cash And Cash Equivalents", col)
    total_cash = _get(data, "Cash Cash Equivalents And Short Term Investments", col)
    inventory = _get(data, "Inventory", col)
    working_capital = _get(data, "Working Capital", col)
    invested_capital = _get(data, "Invested Capital", col)
    shares = _get(data, "Ordinary Shares Number", col)
    current_assets = _get(data, "Current Assets", col)
    current_liabilities = _get(data, "Current Liabilities", col)
    total_liabilities = _get(data, "Total Liabilities Net Minority Interest", col)
    retained_earnings = _get(data, "Retained Earnings", col)
    tangible_book = _get(data, "Tangible Book Value", col)

    net_cash = (total_cash - total_debt) if total_cash and total_debt else None

    return {
        "total_assets": _metric(total_assets, _fmt(total_assets), fy, src),
        "total_equity": _metric(total_equity, _fmt(total_equity), fy, src),
        "total_debt": _metric(total_debt, _fmt(total_debt), fy, src),
        "cash": _metric(cash, _fmt(cash), fy, src),
        "total_cash_and_investments": _metric(total_cash, _fmt(total_cash), fy, src),
        "net_cash": _metric(net_cash, _fmt(net_cash), fy, f"computed from {src}"),
        "inventory": _metric(inventory, _fmt(inventory), fy, src),
        "working_capital": _metric(working_capital, _fmt(working_capital), fy, src),
        "invested_capital": _metric(invested_capital, _fmt(invested_capital), fy, src),
        "shares_outstanding": _metric(shares, _fmt(shares, prefix="", suffix=" shares"), fy, src),
        "current_assets": _metric(current_assets, _fmt(current_assets), fy, src),
        "current_liabilities": _metric(current_liabilities, _fmt(current_liabilities), fy, src),
        "total_liabilities": _metric(total_liabilities, _fmt(total_liabilities), fy, src),
        "retained_earnings": _metric(retained_earnings, _fmt(retained_earnings), fy, src),
        "tangible_book_value": _metric(tangible_book, _fmt(tangible_book), fy, src),
    }


def _extract_cash_flow(artifacts: Path) -> dict:
    """Extract cash flow metrics."""
    path = artifacts / "cash_flow.csv"
    if not path.exists():
        logger.warning("cash_flow.csv not found")
        return {}

    data = _read_row_csv(path)
    col = _latest_col(data)
    fy = f"FY{col[:4]}"
    src = "cash_flow.csv"

    fcf = _get(data, "Free Cash Flow", col)
    capex = _get(data, "Capital Expenditure", col)
    buybacks = _get(data, "Repurchase Of Capital Stock", col)
    dividends = _get(data, "Cash Dividends Paid", col)
    acquisitions = _get(data, "Net Business Purchase And Sale", col)
    investing_cf = _get(data, "Investing Cash Flow", col)
    financing_cf = _get(data, "Financing Cash Flow", col)
    operating_cf = _get(data, "Operating Cash Flow", col)
    sbc = _get(data, "Stock Based Compensation", col)
    end_cash = _get(data, "End Cash Position", col)

    # Derive OCF if not directly available (FCF + CapEx)
    if operating_cf is None and fcf is not None and capex is not None:
        operating_cf = fcf - capex  # capex is negative, so this adds

    # FCF margin
    # Need revenue from income statement
    is_path = artifacts / "income_statement.csv"
    fcf_margin = None
    if is_path.exists() and fcf:
        is_data = _read_row_csv(is_path)
        revenue = _get(is_data, "Total Revenue", _latest_col(is_data))
        fcf_margin = _safe_div(fcf, revenue)

    return {
        "free_cash_flow": _metric(fcf, _fmt(fcf), fy, src),
        "operating_cash_flow": _metric(operating_cf, _fmt(operating_cf), fy, src),
        "capital_expenditure": _metric(capex, _fmt(capex), fy, src),
        "buybacks": _metric(buybacks, _fmt(buybacks), fy, src),
        "dividends": _metric(dividends, _fmt(dividends), fy, src),
        "acquisitions": _metric(acquisitions, _fmt(acquisitions), fy, src),
        "investing_cash_flow": _metric(investing_cf, _fmt(investing_cf), fy, src),
        "financing_cash_flow": _metric(financing_cf, _fmt(financing_cf), fy, src),
        "stock_based_compensation": _metric(sbc, _fmt(sbc), fy, src),
        "end_cash_position": _metric(end_cash, _fmt(end_cash), fy, src),
        "fcf_margin": _metric(fcf_margin, _pct(fcf_margin), fy, f"computed from {src} + income_statement.csv"),
    }


def _extract_ratios(artifacts: Path) -> dict:
    """Extract key ratios for ticker and peers."""
    path = artifacts / "key_ratios.csv"
    if not path.exists():
        logger.warning("key_ratios.csv not found")
        return {}

    return _read_key_ratios(path)


def _extract_profile(artifacts: Path) -> dict:
    """Extract company profile."""
    path = artifacts / "profile.json"
    if not path.exists():
        logger.warning("profile.json not found")
        return {}

    with open(path) as f:
        data = json.load(f)

    return {
        "company_name": data.get("company_name"),
        "ticker": data.get("symbol"),
        "sector": data.get("sector"),
        "industry": data.get("industry"),
        "country": data.get("country"),
        "employees": data.get("employees"),
        "market_cap": {"value": data.get("market_cap"), "display": _fmt(data.get("market_cap")), "source": "profile.json"},
        "enterprise_value": {"value": data.get("enterprise_value"), "display": _fmt(data.get("enterprise_value")), "source": "profile.json"},
        "current_price": {"value": data.get("current_price"), "display": f"${data.get('current_price')}", "source": "profile.json"},
        "52_week_high": data.get("52_week_high"),
        "52_week_low": data.get("52_week_low"),
        "beta": data.get("beta"),
        "shares_outstanding": {"value": data.get("shares_outstanding"), "display": _fmt(data.get("shares_outstanding"), prefix="", suffix=" shares"), "source": "profile.json"},
        "float_shares": data.get("float_shares"),
    }


def _extract_analyst(artifacts: Path) -> dict:
    """Extract analyst recommendations."""
    path = artifacts / "analyst_recommendations.json"
    if not path.exists():
        logger.warning("analyst_recommendations.json not found")
        return {}

    with open(path) as f:
        data = json.load(f)

    if not data:
        return {}

    # Current month (index 0)
    current = data[0]
    total = sum(current.get(k, 0) for k in ["strongBuy", "buy", "hold", "sell", "strongSell"])
    return {
        "strong_buy": current.get("strongBuy", 0),
        "buy": current.get("buy", 0),
        "hold": current.get("hold", 0),
        "sell": current.get("sell", 0),
        "strong_sell": current.get("strongSell", 0),
        "total_analysts": total,
        "source": "analyst_recommendations.json",
    }


def _extract_filings(artifacts: Path) -> dict:
    """Extract filing metadata."""
    result: dict[str, Any] = {"source": "sec_*_metadata.json + 8k_summary.json"}

    # 10-K
    path_10k = artifacts / "sec_10k_metadata.json"
    if path_10k.exists():
        with open(path_10k) as f:
            data = json.load(f)
        result["10k_filing_date"] = data.get("filing_date")
        result["10k_items_extracted"] = data.get("items_extracted", [])

    # 10-Q
    path_10q = artifacts / "sec_10q_metadata.json"
    if path_10q.exists():
        with open(path_10q) as f:
            data = json.load(f)
        result["10q_filing_date"] = data.get("filing_date")

    # 8-K count
    path_8k = artifacts / "8k_summary.json"
    if path_8k.exists():
        with open(path_8k) as f:
            data = json.load(f)
        result["8k_count"] = len(data)
        if data:
            result["8k_most_recent"] = data[0].get("filing_date")

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Extract authoritative financial metrics")
    parser.add_argument("ticker", help="Stock ticker symbol")
    parser.add_argument("--workdir", required=True, help="Working directory")
    args = parser.parse_args()

    ticker = validate_symbol(args.ticker)
    workdir = Path(args.workdir)
    artifacts = ensure_directory(workdir / "artifacts")

    logger.info("Extracting key facts for %s from %s", ticker, artifacts)

    profile_data = _extract_profile(artifacts)
    company_name = profile_data.get("company_name", ticker)

    key_facts = {
        "meta": {
            "ticker": ticker,
            "company_name": company_name,
            "generated": date.today().isoformat(),
            "description": (
                "Authoritative financial metrics extracted from structured artifacts. "
                "Use these as ground truth when sources disagree. Each value includes "
                "its source file for traceability."
            ),
        },
        "financials": _extract_financials(artifacts),
        "balance_sheet": _extract_balance_sheet(artifacts),
        "cash_flow": _extract_cash_flow(artifacts),
        "ratios": _extract_ratios(artifacts),
        "profile": profile_data,
        "analyst": _extract_analyst(artifacts),
        "filings": _extract_filings(artifacts),
    }

    # Write output
    out_path = artifacts / "key_facts.json"
    with open(out_path, "w") as f:
        json.dump(key_facts, f, indent=2, default=str)

    logger.info("Wrote %s", out_path)

    # Count populated sections
    populated = sum(1 for k, v in key_facts.items() if k != "meta" and v)
    logger.info("Populated %d/7 sections", populated)

    # JSON manifest to stdout
    manifest = {
        "status": "complete",
        "artifacts": [
            {
                "name": "key_facts",
                "path": "artifacts/key_facts.json",
                "format": "json",
                "description": f"Authoritative financial metrics for {ticker} — source of truth for research agents",
            }
        ],
        "error": None,
    }
    print(json.dumps(manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
