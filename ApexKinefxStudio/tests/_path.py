"""Make ``apex_studio`` importable from the tests without installing it."""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY = os.path.join(ROOT, "scripts", "python")
if PY not in sys.path:
    sys.path.insert(0, PY)
os.environ.setdefault("APEX_KINEFX_STUDIO", ROOT)
