"""Start the Houdini bridge against fake_hou (for MCP round-trip tests).

    python tests/run_fake_bridge.py PORT
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "python"))
sys.path.insert(0, HERE)
os.environ.setdefault("APEX_KINEFX_STUDIO", ROOT)

import fake_hou  # noqa: E402

sys.modules["hou"] = fake_hou
for mod in [m for m in sys.modules if m.startswith("apex_studio")]:
    del sys.modules[mod]

from apex_studio import bridge  # noqa: E402

bridge.serve_forever(int(sys.argv[1]))
