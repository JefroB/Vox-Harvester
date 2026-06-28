import sys
from pathlib import Path

# Add .subagentcoder/ to sys.path so tests can import local_coder, orchestrator, models
_INTERNAL_DIR = str(Path(__file__).parent.parent)
if _INTERNAL_DIR not in sys.path:
    sys.path.insert(0, _INTERNAL_DIR)
