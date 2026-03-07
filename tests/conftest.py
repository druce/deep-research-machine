import sys
from pathlib import Path

import pytest

# Allow imports from skills/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills"))


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires real API keys and network access")
