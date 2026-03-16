# Best Practices Cheatsheet

Quick reference for writing skills following best practices.

## Skill Directory Structure

Each skill lives in its own subdirectory under `skills/`:

```
skills/
├── fetch_profile/
│   ├── fetch_profile.md    # Skill frontmatter (name, description, type)
│   └── fetch_profile.py    # Executable Python script
├── fetch_technical/
│   ├── fetch_technical.md
│   └── fetch_technical.py
├── ...
├── config.py               # Shared configuration constants
├── utils.py                # Shared utility functions
├── db.py                   # Database CLI
└── schema.py               # Pydantic DAG schema models
```

### Skill Frontmatter (.md file)

Each skill subdirectory contains a `.md` file with YAML frontmatter:

```markdown
---
name: fetch_edgar
description: Fetch SEC filings (10-K, 10-Q, 8-K) via edgartools
type: python
---

# fetch_edgar

Brief description of the skill.

## Usage
...

## Outputs
...
```

## File Header Template

Since each skill lives in a subdirectory (e.g. `skills/fetch_profile/`), Python can't find sibling modules like `config` and `utils` without a path fix. The `_SKILLS_DIR` block below adds the `skills/` parent directory to `sys.path` so those imports work. Because the local imports come **after** the `sys.path` manipulation (a non-import statement), linters flag them as E402 ("module level import not at top of file"). Suppress this with `# noqa: E402` on each local import line.

```python
#!/usr/bin/env python3
"""
Skill Name

Brief description of what this skill does.

Usage:
    ./skills/fetch_<name>/fetch_<name>.py SYMBOL [options]

Output:
    - Description of outputs
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add skills directory to path for local imports
_SKILLS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

from config import (  # noqa: E402
    WORK_DIR,
    # Add other needed constants
)
from utils import (  # noqa: E402
    setup_logging,
    create_work_directory,
    validate_symbol,
    ensure_directory,
    print_section_header,
)

logger = setup_logging(__name__)
```

## Stdout/Stderr Protocol

Skills are invoked by the `/taskrunner` which reads their stdout to get results. **This convention is critical:**

- **stdout**: Only the final JSON manifest (`{"status": "...", "artifacts": [...], "error": ...}`)
- **stderr**: All progress output, diagnostics, and logging (via `logger.*`)

Never use `print()` for status messages — it goes to stdout and corrupts the manifest. Use `logger.info()` / `logger.warning()` / `logger.error()` which routes to stderr via the StreamHandler.

### Environment Loading

Skills that need API keys should call `load_environment()` at module level after imports:

```python
from utils import load_environment
load_environment()  # loads .env from project root
```

## Common Patterns

### Setup and Argument Parsing

```python
def main() -> int:
    """Main execution function."""
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description='Skill description')
    parser.add_argument('symbol', help='Stock ticker symbol')
    parser.add_argument('--work-dir', help='Work directory')
    parser.add_argument('--verbose', '-v', action='store_true')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    symbol = validate_symbol(args.symbol)
    work_dir = Path(args.work_dir) if args.work_dir else create_work_directory(symbol)

    # ... implementation

    return 0  # Success

if __name__ == '__main__':
    sys.exit(main())
```

### Function with Type Hints and Docstring

```python
def process_data(
    symbol: str,
    work_dir: Path,
    limit: int = 10
) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Process data for symbol.

    Args:
        symbol: Stock ticker symbol
        work_dir: Working directory path
        limit: Maximum items to process

    Returns:
        Tuple of (success, data, error_message)

    Example:
        >>> success, data, err = process_data("TSLA", Path("work"))
        >>> if success:
        ...     print(data['price'])
    """
    try:
        # Implementation
        return True, data, None
    except ValueError as e:
        logger.error(f"Invalid data: {e}")
        return False, None, str(e)
```

### Exception Handling

```python
try:
    result = api_call()
except (KeyError, ValueError) as e:
    logger.warning(f"Could not parse: {e}")
    return False, None, str(e)
except ImportError as e:
    logger.error(f"Missing dependency: {e}")
    return False, None, str(e)
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    raise
```

### Path Operations

```python
from pathlib import Path
from utils import ensure_directory

# Create artifacts directory
artifacts_dir = ensure_directory(Path(workdir) / 'artifacts')

# Create file path
output_file = artifacts_dir / 'data.csv'

# Check existence
if output_file.exists():
    logger.info(f"File exists: {output_file}")

# Read/Write — use Path.open(), not built-in open()
with output_file.open('r') as f:
    data = f.read()
```

### Logging

```python
# Status messages
logger.info("Starting analysis")
logger.debug(f"Processing {len(items)} items")

# Success
logger.info("✓ Analysis complete")

# Warnings
logger.warning("API rate limit approaching")

# Errors
logger.error(f"Failed to fetch data: {error}")
logger.error("Critical error occurred", exc_info=True)  # Include traceback
```

### Using Config Constants

```python
from config import (
    MAX_PEERS_TO_FETCH,
    SMA_SHORT_PERIOD,
    PHASE_TIMEOUTS,
    PERPLEXITY_MODEL,
)

# Use directly
peers = fetch_peers(symbol, limit=MAX_PEERS_TO_FETCH)
sma = calculate_sma(prices, period=SMA_SHORT_PERIOD)
timeout = PHASE_TIMEOUTS.get('technical', 300)
```

### Formatting Values

```python
from utils import format_currency, format_number, format_percentage

# Format money
market_cap = format_currency(1234567890)  # "$1.23B"

# Format numbers
shares = format_number(1234567)  # "1,234,567"

# Format percentages
margin = format_percentage(0.1567)  # "15.67%"
```

### Output Formatting

```python
from utils import (
    print_section_header,
    print_success,
    print_error,
    print_warning,
    print_info,
)

print_section_header("Technical Analysis")
print_success("Data fetched successfully")
print_error("API call failed")
print_warning("Rate limit approaching")
print_info("Using cached data")
```

## Quick Checklist

When writing a new skill:

- [ ] Place script in `skills/fetch_<name>/fetch_<name>.py` with matching `.md` frontmatter
- [ ] Set `_SKILLS_DIR = Path(__file__).resolve().parent.parent` and `sys.path.insert` for imports
- [ ] Use `#!/usr/bin/env python3` shebang
- [ ] Import from `config` for constants — add `# noqa: E402`
- [ ] Import from `utils` for common functions — add `# noqa: E402`
- [ ] Call `load_environment()` at module level if API keys are needed
- [ ] Set up logger: `logger = setup_logging(__name__)`
- [ ] Add type hints to all functions (use `Path` not `str` for paths)
- [ ] Write comprehensive docstrings
- [ ] Use `pathlib.Path` for all paths, `path.open()` not `open(path)`
- [ ] Use `logger.*` instead of `print()` for status (stderr only)
- [ ] Only JSON manifest goes to stdout
- [ ] Use specific exception handling (no bare `except:`)
- [ ] Return proper exit codes (0 = success, 1 = partial, 2 = failure)
- [ ] Validate inputs using `validate_symbol()` etc.
- [ ] Create directories with `ensure_directory()`

## Common Imports

### Standard Library
```python
import sys
import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
```

### Third-Party
```python
import pandas as pd
import numpy as np
from dotenv import load_dotenv
```

### Local
```python
# These must come AFTER the sys.path fix — add noqa to suppress E402
from config import (  # noqa: E402
    WORK_DIR,
    MAX_PEERS_TO_FETCH,
    PHASE_TIMEOUTS,
)
from utils import (  # noqa: E402
    setup_logging,
    create_work_directory,
    validate_symbol,
    ensure_directory,
    format_currency,
)
```

## Anti-Patterns to Avoid

❌ **Missing sys.path fix or noqa**
```python
# Wrong — local imports without path fix will fail at runtime
from config import WORK_DIR

# Wrong — missing noqa triggers linter E402 errors
sys.path.insert(0, str(_SKILLS_DIR))
from config import WORK_DIR          # linter flags this

# Correct
sys.path.insert(0, str(_SKILLS_DIR))
from config import WORK_DIR  # noqa: E402
```

❌ **Hardcoded Shebang**
```python
#!/opt/anaconda3/envs/mcpskills/bin/python3
```

❌ **Bare Except**
```python
try:
    code()
except:
    pass
```

❌ **Print for Logging**
```python
print("Processing...")                    # Use logger.info()
print("Processing...", file=sys.stderr)   # Also wrong — use logger.info()
```

❌ **os.path Usage**
```python
os.path.join(dir, file)  # Use Path(dir) / file
```

❌ **Built-in open() with Path objects**
```python
with open(output_path, 'w') as f:  # Use output_path.open('w')
```

❌ **Magic Numbers**
```python
limit = 15  # Use MAX_PEERS_TO_FETCH from config
```

❌ **No Type Hints**
```python
def func(x, y):  # Add type hints
```

❌ **Missing Docstrings**
```python
def func():  # Add docstring
    pass
```

## Resources

- **Reference Implementations:** `fetch_wikipedia/fetch_wikipedia.py`, `fetch_edgar/fetch_edgar.py` (best-conforming scripts)
- **Configuration:** `config.py`
- **Utilities:** `utils.py`

## Quick Examples

### Complete Function Example

```python
def fetch_company_data(
    symbol: str,
    work_dir: Path,
    use_cache: bool = True
) -> Tuple[bool, Optional[Dict[str, any]], Optional[str]]:
    """
    Fetch company fundamental data.

    Args:
        symbol: Stock ticker symbol (e.g., 'TSLA')
        work_dir: Working directory for output
        use_cache: Whether to use cached data if available

    Returns:
        Tuple containing:
            - success: True if fetch succeeded
            - data: Dictionary of company data or None
            - error: Error message or None

    Example:
        >>> success, data, err = fetch_company_data("TSLA", Path("work"))
        >>> if success:
        ...     print(f"Market cap: {data['market_cap']}")
    """
    try:
        logger.info(f"Fetching data for {symbol}")

        output_dir = ensure_directory(work_dir / 'artifacts')

        cache_file = output_dir / 'cache.json'

        if use_cache and cache_file.exists():
            logger.info("Using cached data")
            with cache_file.open('r') as f:
                return True, json.load(f), None

        # Fetch fresh data
        data = api_fetch(symbol)

        # Save cache
        with cache_file.open('w') as f:
            json.dump(data, f, indent=2)

        logger.info("✓ Data fetched successfully")
        return True, data, None

    except ValueError as e:
        logger.error(f"Invalid symbol: {e}")
        return False, None, f"Invalid symbol: {e}"
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        return False, None, f"Missing dependency: {e}"
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return False, None, str(e)
```

---

**Keep this cheatsheet handy when writing new skills or migrating existing ones!**
