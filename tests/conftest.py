import sys
from pathlib import Path

# Allow imports from skills/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills"))
