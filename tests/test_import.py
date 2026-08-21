"""Import-only smoke test for the FastAPI app."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import app

print("App routes:")
for r in app.routes:
    if hasattr(r, "path"):
        methods = getattr(r, "methods", None) or "-"
        print(f"  {methods} {r.path}")
print("OK startup import works")
