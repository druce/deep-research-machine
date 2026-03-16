"""
SEC filing text cleaning utilities.

Strips HTML artifacts, boilerplate sections, and formatting noise from
edgartools-extracted filing text before it's written to knowledge/ files
and chunked into LanceDB.
"""

import re


# ---------------------------------------------------------------------------
# HTML / encoding cleanup
# ---------------------------------------------------------------------------

# HTML tags (inline and block-level) that leak through edgartools
_HTML_TAG_RE = re.compile(r"</?(?:div|span|font|br|hr|table|tr|td|th|p|b|i|u|a|img|sup|sub|center)[^>]*>", re.IGNORECASE)

# HTML entities
_HTML_ENTITY_RE = re.compile(r"&(?:nbsp|amp|lt|gt|quot|apos|#\d+|#x[\da-fA-F]+);")

# Collapse runs of 3+ newlines into 2 (paragraph break)
_EXCESS_NEWLINES_RE = re.compile(r"\n{3,}")

# Collapse runs of 3+ spaces into 1
_EXCESS_SPACES_RE = re.compile(r" {3,}")


def clean_html_artifacts(text: str) -> str:
    """Remove residual HTML tags and entities from SEC filing text."""
    text = _HTML_TAG_RE.sub("", text)
    # Decode common entities before removing the rest
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&apos;", "'")
    text = _HTML_ENTITY_RE.sub("", text)
    text = _EXCESS_SPACES_RE.sub(" ", text)
    text = _EXCESS_NEWLINES_RE.sub("\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# SEC boilerplate removal
# ---------------------------------------------------------------------------

# Forward-looking statements disclaimer — appears in almost every filing
_FLS_PATTERNS = [
    # Match single-paragraph FLS disclaimers (no DOTALL — stays within paragraph)
    re.compile(
        r"(?:This|The)\s+(?:report|document|filing|quarterly report|annual report)"
        r"[^\n]*?forward[- ]looking\s+statements[^\n]*?(?:Private\s+Securities\s+Litigation\s+"
        r"Reform\s+Act|Securities\s+Act)[^\n]*\.",
        re.IGNORECASE,
    ),
    # Match multi-line FLS section with heading (bounded to 30 lines, no DOTALL)
    re.compile(
        r"(?:Forward[- ]Looking\s+Statements?|FORWARD[- ]LOOKING\s+STATEMENTS?)\s*\n"
        r"(?:[^\n]*\n){0,30}?(?:(?:undue\s+reliance|actual\s+results\s+may\s+differ|"
        r"we\s+undertake\s+no\s+obligation)[^\n]*\.)",
        re.IGNORECASE,
    ),
]

# 8-K signature blocks and certifications
_SIGNATURE_RE = re.compile(
    r"(?:^|\n)\s*SIGNATURE[S]?\s*\n"
    r".*",  # everything after SIGNATURES heading
    re.IGNORECASE | re.DOTALL,
)

# Exhibit index tables (common in 8-K)
_EXHIBIT_INDEX_RE = re.compile(
    r"(?:^|\n)\s*(?:EXHIBIT\s+INDEX|Exhibit\s+Index|Item\s+9\.01[^\n]*Exhibits?)\s*\n"
    r".*",  # everything after exhibit index heading
    re.IGNORECASE | re.DOTALL,
)

# Cover page boilerplate (EDGAR filing header block in 8-Ks)
_COVER_PAGE_RE = re.compile(
    r"(?:UNITED\s+STATES\s*\n\s*SECURITIES\s+AND\s+EXCHANGE\s+COMMISSION|"
    r"FORM\s+8-K\s*\n\s*CURRENT\s+REPORT)"
    r".*?(?=(?:\n\s*Item\s+\d|$))",
    re.IGNORECASE | re.DOTALL,
)


def strip_sec_boilerplate(text: str, form_type: str = "") -> str:
    """Remove standard SEC boilerplate from filing text.

    Args:
        text: Raw filing text after HTML cleanup.
        form_type: Filing form type (e.g. "8-K", "10-K") to apply
                   form-specific rules.
    """
    # Forward-looking statements (all form types)
    for pattern in _FLS_PATTERNS:
        text = pattern.sub("", text)

    if form_type.upper() == "8-K":
        text = _COVER_PAGE_RE.sub("", text)
        text = _SIGNATURE_RE.sub("", text)
        text = _EXHIBIT_INDEX_RE.sub("", text)

    # Clean up any resulting whitespace mess
    text = _EXCESS_NEWLINES_RE.sub("\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Combined pipeline
# ---------------------------------------------------------------------------

def clean_sec_text(text: str, form_type: str = "") -> str:
    """Full cleaning pipeline for SEC filing text.

    1. Strip HTML artifacts
    2. Remove SEC boilerplate
    3. Normalize whitespace
    """
    text = clean_html_artifacts(text)
    text = strip_sec_boilerplate(text, form_type)
    return text


# ---------------------------------------------------------------------------
# 8-K materiality filter
# ---------------------------------------------------------------------------

# Items that represent material events worth chunking
MATERIAL_8K_ITEMS = frozenset({
    "Item 1.01",  # Entry into a Material Definitive Agreement
    "Item 1.02",  # Termination of a Material Definitive Agreement
    "Item 1.03",  # Bankruptcy or Receivership
    "Item 2.01",  # Completion of Acquisition or Disposition of Assets
    "Item 2.02",  # Results of Operations and Financial Condition
    "Item 2.05",  # Costs Associated with Exit or Disposal Activities
    "Item 2.06",  # Material Impairments
    "Item 4.01",  # Changes in Registrant's Certifying Accountant
    "Item 4.02",  # Non-Reliance on Previously Issued Financial Statements
    "Item 5.01",  # Changes in Control of Registrant
    "Item 5.02",  # Departure/Appointment of Directors or Officers
    "Item 7.01",  # Regulation FD Disclosure
    "Item 8.01",  # Other Events
})

# Items that are purely procedural/boilerplate
IMMATERIAL_8K_ITEMS = frozenset({
    "Item 9.01",  # Financial Statements and Exhibits (just exhibit listings)
    "Item 2.03",  # Creation of a Direct Financial Obligation (routine)
    "Item 2.04",  # Triggering Events (routine covenant notifications)
    "Item 3.02",  # Unregistered Sales of Equity Securities (routine)
    "Item 3.03",  # Material Modification to Rights of Security Holders
    "Item 5.04",  # Temporary Suspension of Trading
    "Item 5.05",  # Amendments to Code of Ethics
    "Item 5.06",  # Change in Shell Company Status
    "Item 5.07",  # Submission of Matters to a Vote
    "Item 5.08",  # Shareholder Nominations
})


def is_material_8k(items_reported: list[str]) -> bool:
    """Determine if an 8-K filing contains material events worth indexing.

    An 8-K is material if it reports at least one item in MATERIAL_8K_ITEMS.
    If items_reported is empty (couldn't parse items), we keep it to be safe.
    """
    if not items_reported:
        return True  # can't determine → keep it

    return any(item in MATERIAL_8K_ITEMS for item in items_reported)
