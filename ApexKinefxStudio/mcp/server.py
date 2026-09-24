"""ApexKinefxStudio MCP server: lets Claude drive Houdini to build and test the tools.

Runs with a normal Python 3.10+ (not hython) and talks to the bridge inside
Houdini (apex_studio/bridge.py) over 127.0.0.1.

    pip install "mcp>=1.2"
    python ApexKinefxStudio/mcp/server.py          # stdio MCP server

Environment:
    AKS_BRIDGE_PORT   bridge port (default 18900)
    AKS_BRIDGE_TOKEN  optional shared token (set the same value for Houdini)
    AKS_HYTHON        path to hython(.exe); lets the launch_houdini_bridge tool
                      start a headless Houdini automatically
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from itertools import count
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGE_ROOT = os.path.abspath(os.path.join(HERE, ".."))

try:  # MCP Python SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server

PORT = int(os.environ.get("AKS_BRIDGE_PORT", "18900"))
TOKEN = os.environ.get("AKS_BRIDGE_TOKEN")
_ids = count(1)
_hython_proc: Optional[subprocess.Popen] = None


# ---------------------------------------------------------------------------
# Bridge client
# ---------------------------------------------------------------------------

class BridgeError(RuntimeError):
    pass


def call(method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 600.0) -> Any:
    """Send one request to the Houdini bridge and return its result."""
    request = {"id": next(_ids), "method": method, "params": params or {}}
    if TOKEN:
        request["token"] = TOKEN
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=10) as sock:
            sock.settimeout(timeout)
            sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = sock.recv(1 << 16)
                if not chunk:
                    break
                buf += chunk
    except ConnectionRefusedError:
        raise BridgeError(
            f"Houdini bridge not reachable on 127.0.0.1:{PORT}. In Houdini run the shelf tool "
            "'Start MCP Bridge' (or `import apex_studio.bridge as b; b.start()`), or call "
            "launch_houdini_bridge to start a headless hython.") from None
    except socket.timeout:
        raise BridgeError(f"Houdini did not answer '{method}' within {timeout:.0f}s") from None
    if not buf:
        raise BridgeError("empty response from the bridge")
    response = json.loads(buf.decode("utf-8"))
    if not response.get("ok"):
        raise BridgeError(response.get("error", "unknown bridge error"))
    return response.get("result")


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, default=str)


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

mcp = _Server("houdini-apex-kinefx-studio",
              instructions=(
                  "Tools to build and test the ApexKinefxStudio Houdini package in a live Houdini. "
                  "Typical loop: houdini_status -> run_selftest -> read errors -> fix files in the "
                  "package -> reload_package -> run_selftest again. Use node_info on failing nodes to "
                  "see VEX snippets and errors."))


@mcp.tool()
def houdini_status() -> str:
    """Check the Houdini connection: Houdini version, scene, package version and root."""
    return _json(call("ping", timeout=30))


@mcp.tool()
def launch_houdini_bridge(hython_path: str = "", wait_seconds: int = 90) -> str:
    """Start a headless hython running the bridge (uses AKS_HYTHON if hython_path is empty)."""
    global _hython_proc
    try:
        return "already running: " + _json(call("ping", timeout=5))
    except BridgeError:
        pass
    exe = hython_path or os.environ.get("AKS_HYTHON")
    if not exe:
        return ("No hython path. Pass hython_path, e.g. "
                r"'C:\Program Files\Side Effects Software\Houdini 22.0.xxx\bin\hython.exe', or set AKS_HYTHON.")
    script = os.path.join(HERE, "start_bridge_hython.py")
    log_path = os.path.join(HERE, "hython_bridge.log")
    # log to a file: an unread PIPE fills up and blocks hython on long runs
    log = open(log_path, "w", encoding="utf-8")
    _hython_proc = subprocess.Popen([exe, script, str(PORT)], cwd=PACKAGE_ROOT,
                                    stdout=log, stderr=subprocess.STDOUT)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if _hython_proc.poll() is not None:
            log.flush()
            with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
                out = fh.read()
            return f"hython exited with code {_hython_proc.returncode}:\n{out[-4000:]}"
        try:
            return "started: " + _json(call("ping", timeout=5))
        except BridgeError:
            time.sleep(2)
    return (f"hython started (pid {_hython_proc.pid}) but the bridge did not answer within "
            f"{wait_seconds}s; see {log_path}")


@mcp.tool()
def run_selftest(cases: Optional[List[str]] = None, frames: Optional[List[int]] = None,
                 retarget_source_fbx: str = "", retarget_target_fbx: str = "", agent_fbx: str = "",
                 report_path: str = "") -> str:
    """Build every tool in Houdini, cook it over frames and report errors.

    cases: subset of snake, insect, spider, quadruped, bird, jellyfish, biped, car,
    car_drift, bike, tank, retarget, biped_retarget, crowd (retarget/crowd need FBX paths).
    Returns per-case build exceptions, node errors/warnings (incl. VEX compile errors),
    package warnings (unresolved native parms) and skeleton sanity metrics.
    """
    params = {"cases": cases, "frames": frames, "out_path": report_path or None,
              "retarget_source": retarget_source_fbx or None, "retarget_target": retarget_target_fbx or None,
              "agent_fbx": agent_fbx or None}
    return _json(call("selftest", params, timeout=1800))


@mcp.tool()
def build_tool(tool: str, options: Optional[Dict[str, Any]] = None, check: bool = True) -> str:
    """Build one tool with keyword options and check it.

    tool: snake, insect, spider, quadruped, bird, jellyfish, biped, vehicle, retarget,
    agent, stadium, crowd. options: builder kwargs, e.g. {"vehicle_type": "tank",
    "path": "/obj/aks_test_track/OUT"}.
    """
    return _json(call("build", {"tool": tool, "kwargs": options or {}, "check": check}, timeout=900))


@mcp.tool()
def check_network(path: str, frames: Optional[List[int]] = None) -> str:
    """Cook an existing tool container (e.g. /obj/aks_car) and report errors/warnings/metrics."""
    return _json(call("check", {"path": path, "frames": frames}, timeout=900))


@mcp.tool()
def node_info(path: str, geometry: bool = False, all_parms: bool = False) -> str:
    """Type, inputs, children, errors, warnings, non-default parms and VEX snippet of a node."""
    return _json(call("node_info", {"path": path, "geometry": geometry, "all_parms": all_parms}))


@mcp.tool()
def set_parm(path: str, parm: str, value: Any = None, expression: str = "") -> str:
    """Set a parameter value (or an HScript expression) on a node."""
    return _json(call("set_parm", {"path": path, "parm": parm, "value": value, "expression": expression}))


@mcp.tool()
def run_houdini_python(code: str) -> str:
    """Run Python inside Houdini with `hou` available. Assign to `result` to return a value."""
    return _json(call("run_python", {"code": code}, timeout=900))


@mcp.tool()
def reload_package() -> str:
    """Re-import apex_studio inside Houdini after editing the package files."""
    return _json(call("reload"))


@mcp.tool()
def probe_node_types() -> str:
    """List KineFX/APEX/crowd node types in this Houdini and how the package resolved them."""
    return _json(call("probe"))


@mcp.tool()
def clean_test_scene() -> str:
    """Delete all aks_test_* containers from /obj."""
    return _json(call("clean"))


@mcp.tool()
def save_hip(path: str = "") -> str:
    """Save the current Houdini scene (to path if given), e.g. to inspect a failing setup by hand."""
    return _json(call("save_hip", {"path": path}))


@mcp.tool()
def run_unit_tests() -> str:
    """Run the package's pure-Python unit tests (no Houdini needed)."""
    proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                          cwd=PACKAGE_ROOT, capture_output=True, text=True, timeout=600)
    return f"exit code {proc.returncode}\n{proc.stdout[-6000:]}{proc.stderr[-6000:]}"


if __name__ == "__main__":
    mcp.run()
