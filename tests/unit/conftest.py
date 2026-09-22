import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

for subdir in ("src", "scripts"):
    candidate = str(ROOT / subdir)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)
