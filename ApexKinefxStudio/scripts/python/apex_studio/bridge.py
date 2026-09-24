"""Houdini-side bridge for the ApexKinefxStudio MCP server.

A tiny JSON-lines server on 127.0.0.1 that runs inside Houdini and executes
requests from ``mcp/server.py`` (which Claude talks to over MCP).

* GUI Houdini: ``import apex_studio.bridge as b; b.start()`` (or the shelf's
  *Start MCP Bridge*). Requests run on Houdini's main thread via hdefereval,
  so the UI keeps working.
* Headless: ``hython ApexKinefxStudio/mcp/start_bridge_hython.py``. Serves on
  the main thread, blocking.

Protocol: one JSON object per line ``{"id", "method", "params", "token"}``,
answered by ``{"id", "ok", "result" | "error"}``.

Security: it binds to localhost only, but ``run_python`` executes arbitrary
code inside Houdini. Set ``AKS_BRIDGE_TOKEN`` in both environments to require
a shared token, and don't expose the port.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import socketserver
import sys
import threading
import traceback
from typing import Any, Callable, Dict, Optional

DEFAULT_PORT = int(os.environ.get("AKS_BRIDGE_PORT", "18900"))
_SERVER: Optional[socketserver.BaseServer] = None
_THREAD: Optional[threading.Thread] = None


def _hou():
    import hou  # noqa: WPS433  (only available inside Houdini)
    return hou


# ---------------------------------------------------------------------------
# Methods
# ---------------------------------------------------------------------------

def m_ping(params):
    hou = _hou()
    import apex_studio
    from apex_studio import network
    return {"houdini": hou.applicationVersionString(), "hip": hou.hipFile.path(),
            "package_version": apex_studio.__version__, "package_root": network.PACKAGE_ROOT,
            "python": sys.version.split()[0], "ui": hou.isUIAvailable()}


def m_reload(params):
    """Re-import apex_studio so edited files take effect without restarting Houdini."""
    for name in [m for m in sys.modules if m == "apex_studio" or m.startswith("apex_studio.")]:
        if name != "apex_studio.bridge":
            del sys.modules[name]
    import apex_studio  # noqa: F401
    from apex_studio import crowd, dynamics, hda, retarget, selftest, validate  # noqa: F401
    from apex_studio.rigging import bipeds, creatures, vehicles  # noqa: F401
    return {"reloaded": sorted(m for m in sys.modules if m.startswith("apex_studio"))}


def m_selftest(params):
    from apex_studio import selftest
    return selftest.run(only=params.get("cases"), frames=params.get("frames") or selftest.DEFAULT_FRAMES,
                        retarget_source=params.get("retarget_source"),
                        retarget_target=params.get("retarget_target"),
                        agent_fbx=params.get("agent_fbx"), out_path=params.get("out_path"))


def m_clean(params):
    from apex_studio import selftest
    return {"deleted": selftest.clean()}


_BUILDERS = {
    "snake": ("apex_studio.rigging.creatures", "build_snake"),
    "insect": ("apex_studio.rigging.creatures", "build_insect"),
    "spider": ("apex_studio.rigging.creatures", "build_spider"),
    "quadruped": ("apex_studio.rigging.creatures", "build_quadruped"),
    "bird": ("apex_studio.rigging.creatures", "build_bird"),
    "jellyfish": ("apex_studio.rigging.creatures", "build_jellyfish"),
    "biped": ("apex_studio.rigging.bipeds", "build_biped"),
    "vehicle": ("apex_studio.rigging.vehicles", "build_vehicle"),
    "retarget": ("apex_studio.retarget", "build_retarget"),
    "agent": ("apex_studio.crowd", "build_agent"),
    "stadium": ("apex_studio.crowd", "build_stadium"),
    "crowd": ("apex_studio.crowd", "build_crowd"),
}


def m_build(params):
    import importlib
    tool = params["tool"]
    if tool not in _BUILDERS:
        raise ValueError(f"unknown tool {tool!r}; choose from {sorted(_BUILDERS)}")
    mod, fn = _BUILDERS[tool]
    node = getattr(importlib.import_module(mod), fn)(**(params.get("kwargs") or {}))
    result = {"path": node.path()}
    if params.get("check", True):
        from apex_studio import selftest
        container = node if node.type().name() == "geo" else node.parent()
        result["check"] = selftest.check_container(container, params.get("frames") or selftest.DEFAULT_FRAMES)
    return result


def m_check(params):
    hou = _hou()
    from apex_studio import selftest
    node = hou.node(params["path"])
    if node is None:
        raise ValueError(f"no node {params['path']}")
    return selftest.check_container(node, params.get("frames") or selftest.DEFAULT_FRAMES)


def m_node_info(params):
    hou = _hou()
    node = hou.node(params["path"])
    if node is None:
        raise ValueError(f"no node {params['path']}")
    info: Dict[str, Any] = {"path": node.path(), "type": node.type().name(),
                            "inputs": [i.path() if i else None for i in node.inputs()],
                            "children": [c.name() for c in node.children()]}
    try:
        info["errors"] = list(node.errors())
        info["warnings"] = list(node.warnings())
    except Exception:
        pass
    parms = {}
    for p in node.parms():
        try:
            if params.get("all_parms") or not p.isAtDefault():
                parms[p.name()] = p.expression() if _has_expr(p) else p.eval()
        except Exception:
            continue
    info["parms"] = parms
    snippet = node.parm("snippet")
    if snippet is not None and params.get("include_snippet", True):
        info["snippet"] = snippet.eval()
    if params.get("geometry", False) and hasattr(node, "geometry"):
        geo = node.geometry()
        if geo is not None:
            info["geometry"] = {
                "points": len(geo.points()), "prims": len(geo.prims()),
                "point_attribs": [a.name() for a in geo.pointAttribs()],
                "prim_attribs": [a.name() for a in geo.primAttribs()],
                "detail_attribs": {a.name(): _safe_detail(geo, a.name()) for a in geo.globalAttribs()},
            }
    return info


def _has_expr(p):
    try:
        p.expression()
        return True
    except Exception:
        return False


def _safe_detail(geo, name):
    try:
        v = geo.attribValue(name)
        json.dumps(v)
        return v
    except Exception:
        return "<unserialisable>"


def m_set_parm(params):
    hou = _hou()
    node = hou.node(params["path"])
    if node is None:
        raise ValueError(f"no node {params['path']}")
    parm = node.parm(params["parm"]) or node.parmTuple(params["parm"])
    if parm is None:
        raise ValueError(f"no parm {params['parm']} on {node.path()}")
    if params.get("expression"):
        parm.setExpression(params["expression"])
    else:
        parm.set(params["value"])
    return {"ok": True}


def m_run_python(params):
    """Execute code with ``hou`` in scope; returns stdout and ``result`` if set."""
    hou = _hou()
    ns: Dict[str, Any] = {"hou": hou, "result": None}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        exec(compile(params["code"], "<mcp>", "exec"), ns)
    result = ns.get("result")
    try:
        json.dumps(result)
    except TypeError:
        result = repr(result)
    return {"stdout": buf.getvalue()[-20000:], "result": result}


def m_probe(params):
    from apex_studio import compat
    return {"sop": compat.probe("sop", ("kinefx", "apex", "agent", "crowd", "ragdoll", "motion", "rig")),
            "dop": compat.probe("dop", ("crowd", "agent", "ragdoll")),
            "resolved": compat.resolution_report()}


def m_save_hip(params):
    hou = _hou()
    path = params.get("path")
    hou.hipFile.save(path) if path else hou.hipFile.save()
    return {"saved": hou.hipFile.path()}


METHODS: Dict[str, Callable[[dict], Any]] = {
    "ping": m_ping, "reload": m_reload, "selftest": m_selftest, "clean": m_clean,
    "build": m_build, "check": m_check, "node_info": m_node_info, "set_parm": m_set_parm,
    "run_python": m_run_python, "probe": m_probe, "save_hip": m_save_hip,
}


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def _dispatch(request: dict) -> dict:
    rid = request.get("id")
    token = os.environ.get("AKS_BRIDGE_TOKEN")
    if token and request.get("token") != token:
        return {"id": rid, "ok": False, "error": "bad token"}
    method = METHODS.get(request.get("method", ""))
    if method is None:
        return {"id": rid, "ok": False, "error": f"unknown method {request.get('method')!r}"}
    try:
        return {"id": rid, "ok": True, "result": method(request.get("params") or {})}
    except Exception:
        return {"id": rid, "ok": False, "error": traceback.format_exc()}


def _run_on_main(request: dict) -> dict:
    try:
        import hdefereval  # GUI Houdini only
        hou = _hou()
        if hou.isUIAvailable():
            return hdefereval.executeInMainThreadWithResult(_dispatch, request)
    except ImportError:
        pass
    return _dispatch(request)


class _Handler(socketserver.StreamRequestHandler):
    main_thread = False

    def handle(self):
        for line in self.rfile:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line.decode("utf-8"))
            except ValueError as exc:
                response = {"id": None, "ok": False, "error": f"bad json: {exc}"}
            else:
                response = _dispatch(request) if self.main_thread else _run_on_main(request)
            self.wfile.write((json.dumps(response, default=str) + "\n").encode("utf-8"))
            self.wfile.flush()


class _MainThreadHandler(_Handler):
    main_thread = True


class _ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _BlockingServer(socketserver.TCPServer):
    allow_reuse_address = True


def start(port: int = DEFAULT_PORT) -> int:
    """Start the bridge in a background thread (GUI Houdini). Returns the port."""
    global _SERVER, _THREAD
    if _SERVER is not None:
        return _SERVER.server_address[1]
    _SERVER = _ThreadingServer(("127.0.0.1", port), _Handler)
    _THREAD = threading.Thread(target=_SERVER.serve_forever, name="aks-mcp-bridge", daemon=True)
    _THREAD.start()
    print(f"[ApexKinefxStudio] MCP bridge listening on 127.0.0.1:{_SERVER.server_address[1]}")
    return _SERVER.server_address[1]


def stop() -> None:
    global _SERVER, _THREAD
    if _SERVER is not None:
        _SERVER.shutdown()
        _SERVER.server_close()
    _SERVER = None
    _THREAD = None


def serve_forever(port: int = DEFAULT_PORT) -> None:
    """Blocking server on the main thread (hython)."""
    server = _BlockingServer(("127.0.0.1", port), _MainThreadHandler)
    print(f"[ApexKinefxStudio] MCP bridge (hython) listening on 127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
