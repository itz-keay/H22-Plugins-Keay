"""Headless Houdini running the MCP bridge.

    hython ApexKinefxStudio/mcp/start_bridge_hython.py [port]

Works without installing the package: it puts scripts/python on sys.path.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
os.environ.setdefault("APEX_KINEFX_STUDIO", ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts", "python"))

from apex_studio import bridge  # noqa: E402

bridge.serve_forever(int(sys.argv[1]) if len(sys.argv) > 1 else bridge.DEFAULT_PORT)
