"""In-Houdini self test: build every tool, cook it over several frames, report problems.

Run it three ways:

* from the MCP bridge (``run_selftest`` tool) - Claude reads the report;
* headless: ``hython ApexKinefxStudio/mcp/selftest_hython.py [report.json]``;
* in the Python Shell: ``import apex_studio.selftest as t; t.run()``.

For every case it collects:

* exceptions raised while *building* the network (Python bugs),
* ``node.errors()`` / ``node.warnings()`` of every node after cooking
  (VEX compile errors, missing inputs, bad parameters...),
* package warnings logged by ``compat`` (native parm/node names that did not
  resolve in this Houdini build),
* sanity metrics on the output skeleton: same joint count as the rest pose,
  no NaN/inf positions, and that it actually moves between the first and
  last test frame.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
import traceback
from typing import Callable, Dict, List, Optional, Sequence

from . import compat, network
from .compat import LOG, require_hou

DEFAULT_FRAMES = (1, 12, 24, 48)
TEST_ROOT_PREFIX = "aks_test_"


class _Collector(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.records: List[str] = []

    def emit(self, record):
        self.records.append(f"{record.levelname}: {record.getMessage()}")


# ---------------------------------------------------------------------------
# Test environment
# ---------------------------------------------------------------------------

def _curve(name: str, points, closed: bool = False):
    geo = network.obj_container(name, clear=True)
    code = ("node = hou.pwd()\ngeo = node.geometry()\n"
            f"pts = {[list(p) for p in points]!r}\n"
            f"poly = geo.createPolygon({closed})\n"
            "for p in pts:\n"
            "    pt = geo.createPoint()\n"
            "    pt.setPosition(p)\n"
            "    poly.addVertex(pt)\n")
    out = network.null(geo, "OUT", network.python_sop(geo, "points", code))
    network.finalize(geo, out)
    return out


def environment() -> Dict[str, object]:
    """Terrain + curves shared by the test cases (rebuilt every run)."""
    geo = network.obj_container(TEST_ROOT_PREFIX + "terrain", clear=True)
    hf = compat.create(geo, "heightfield", "heightfield")
    compat.set_parm(hf, "size", (120.0, 120.0), warn=False)
    compat.set_parm(hf, "gridspacing", 0.5, warn=False)
    noise = compat.create(geo, "heightfield_noise", "noise", required=False)
    last = hf
    if noise is not None:
        noise.setInput(0, hf)
        compat.set_parm(noise, "amp", 1.0, warn=False)
        compat.set_parm(noise, "elementsize", 20.0, warn=False)
        last = noise
    ground = network.null(geo, "OUT", last)
    network.finalize(geo, ground)
    loop = [(math.cos(a) * 30, 0.0, math.sin(a) * 18) for a in [i * 2 * math.pi / 48 for i in range(48)]]
    track = _curve(TEST_ROOT_PREFIX + "track", loop, closed=True)
    wiggle = _curve(TEST_ROOT_PREFIX + "wiggle", [(math.sin(z * 0.3) * 3, 0.0, z * 1.0) for z in range(-30, 31)])
    return {"ground": ground, "track": track, "wiggle": wiggle}


def cases(env: Dict[str, object], retarget_source: Optional[str] = None,
          retarget_target: Optional[str] = None, agent_fbx: Optional[str] = None) -> Dict[str, Callable]:
    from . import crowd, retarget
    from .rigging import bipeds, creatures, vehicles

    g, track, wiggle = env["ground"], env["track"], env["wiggle"]
    p = TEST_ROOT_PREFIX
    out: Dict[str, Callable] = {
        "snake": lambda: creatures.build_snake(path=wiggle, ground=g, name=p + "snake"),
        "insect": lambda: creatures.build_insect(path=wiggle, ground=g, name=p + "insect"),
        "spider": lambda: creatures.build_spider(path=wiggle, ground=g, name=p + "spider"),
        "quadruped": lambda: creatures.build_quadruped(path=wiggle, ground=g, name=p + "quadruped"),
        "bird": lambda: creatures.build_bird(path=track, name=p + "bird"),
        "jellyfish": lambda: creatures.build_jellyfish(name=p + "jellyfish"),
        "biped": lambda: bipeds.build_biped(name=p + "biped"),
        "car": lambda: vehicles.build_vehicle(path=track, ground=g, vehicle_type="car", name=p + "car"),
        "car_drift": lambda: _drifting_car(vehicles, track, g),
        "bike": lambda: vehicles.build_vehicle(path=track, ground=g, vehicle_type="bike", name=p + "bike",
                                               speed=15.0),
        "tank": lambda: vehicles.build_vehicle(path=track, ground=g, vehicle_type="tank", name=p + "tank",
                                               speed=5.0),
    }
    if retarget_source and retarget_target:
        out["retarget"] = lambda: retarget.build_retarget(retarget_source, retarget_target, name=p + "retarget")
        out["biped_retarget"] = lambda: bipeds.build_biped(name=p + "biped_anim", animation_fbx=retarget_source)
    if agent_fbx:
        def _crowds():
            agent = crowd.build_agent(agent_fbx, name=p + "agent")
            crowd.build_stadium(agent, name=p + "stadium", rows=3, seats_per_row=12)
            return crowd.build_crowd(agent, count=25, name=p + "crowd", ground=g)
        out["crowd"] = _crowds
    return out


def _drifting_car(vehicles, track, g):
    geo = vehicles.build_vehicle(path=track, ground=g, vehicle_type="car", name=TEST_ROOT_PREFIX + "car_drift",
                                 speed=22.0)
    compat.set_parm(geo.node("drive"), "drift_amount", 1.0)
    return geo


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def _positions(geo) -> List[float]:
    try:
        return list(geo.pointFloatAttribValues("P"))
    except Exception:
        return []


def check_container(container, frames: Sequence[int] = DEFAULT_FRAMES) -> Dict[str, object]:
    """Cook ``container``'s outputs over ``frames`` and collect problems."""
    h = require_hou()
    report: Dict[str, object] = {"path": container.path(), "errors": [], "warnings": [], "metrics": {}}
    outs = [n for n in container.children() if n.name().startswith("OUT_")]
    if not outs:  # fall back to the display node
        outs = [n for n in container.children()
                if hasattr(n, "isDisplayFlagSet") and n.isDisplayFlagSet()]
    first_last: Dict[str, List[List[float]]] = {}
    for f in frames:
        h.setFrame(f)
        for out in outs:
            try:
                out.cook(force=True)
                geo = out.geometry()
                if geo is not None:
                    pos = _positions(geo)
                    if any(math.isnan(v) or math.isinf(v) for v in pos):
                        report["errors"].append({"node": out.path(), "frame": f,
                                                 "messages": ["NaN/inf point positions"]})
                    first_last.setdefault(out.name(), []).append(pos)
            except h.OperationFailed as exc:
                report["errors"].append({"node": out.path(), "frame": f, "messages": [str(exc)]})
    seen = set()
    for node in container.allSubChildren():
        try:
            errs = list(node.errors())
            warns = list(node.warnings())
        except Exception:
            continue
        key = node.path()
        if errs and key not in seen:
            report["errors"].append({"node": key, "type": node.type().name(), "messages": errs})
            seen.add(key)
        if warns:
            report["warnings"].append({"node": key, "type": node.type().name(), "messages": warns})
    rest = container.node("OUT_REST_SKELETON")
    anim = container.node("OUT_ANIM_SKELETON")
    metrics = report["metrics"]
    if rest is not None and anim is not None:
        try:
            nr = len(rest.geometry().points())
            na = len(anim.geometry().points())
            metrics["joints_rest"] = nr
            metrics["joints_anim"] = na
            if nr != na:
                report["errors"].append({"node": anim.path(), "messages": [f"joint count {na} != rest {nr}"]})
        except Exception as exc:
            report["errors"].append({"node": anim.path(), "messages": [f"metric failure: {exc}"]})
    samples = first_last.get("OUT_ANIM_SKELETON") or []
    if len(samples) >= 2 and samples[0] and len(samples[0]) == len(samples[-1]):
        move = max(abs(a - b) for a, b in zip(samples[0], samples[-1]))
        metrics["max_motion"] = round(move, 5)
        if move < 1e-5:
            report["warnings"].append({"node": anim.path() if anim else container.path(),
                                       "messages": ["skeleton does not move between first and last frame"]})
    report["ok"] = not report["errors"]
    return report


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(only: Optional[Sequence[str]] = None, frames: Sequence[int] = DEFAULT_FRAMES,
        retarget_source: Optional[str] = None, retarget_target: Optional[str] = None,
        agent_fbx: Optional[str] = None, out_path: Optional[str] = None) -> Dict[str, object]:
    """Build and check every case (or ``only`` these). Returns a JSON-able report."""
    h = require_hou()
    collector = _Collector()
    LOG.addHandler(collector)
    started = time.time()
    results: Dict[str, object] = {}
    try:
        env = environment()
        table = cases(env, retarget_source, retarget_target, agent_fbx)
        for name, build in table.items():
            if only and name not in only:
                continue
            collector.records.clear()
            entry: Dict[str, object] = {}
            t0 = time.time()
            try:
                container = build()
                entry.update(check_container(container, frames))
            except Exception:
                entry = {"ok": False, "build_exception": traceback.format_exc(), "errors": [], "warnings": []}
            entry["package_warnings"] = list(collector.records)
            entry["seconds"] = round(time.time() - t0, 2)
            results[name] = entry
    finally:
        LOG.removeHandler(collector)
    summary = {
        "houdini": ".".join(str(v) for v in compat.houdini_version()),
        "frames": list(frames),
        "passed": sorted(k for k, v in results.items() if v.get("ok")),
        "failed": sorted(k for k, v in results.items() if not v.get("ok")),
        "seconds": round(time.time() - started, 2),
        "cases": results,
    }
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, default=str)
    return summary


def clean() -> int:
    """Delete every test container from /obj."""
    h = require_hou()
    n = 0
    for node in list(h.node("/obj").children()):
        if node.name().startswith(TEST_ROOT_PREFIX):
            node.destroy()
            n += 1
    return n
