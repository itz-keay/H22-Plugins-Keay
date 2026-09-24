"""Vehicle rigs: car / truck / bike / tank, driven along a curve over terrain.

:func:`build_vehicle` creates ``/obj/<name>``::

    model_in -> (unpack) ----------------------------------------------+
    guides (auto-detected wheels/body/parts) -> REST_SKELETON           |
    path_in, ground_in                                                  |
    drive      (kinematic: path, terrain, wheels, steering, drift)      |
    dynamics   (SOP Solver: body springs, vibration, drift wheel-spin)  |
    part_vibration (loose parts)                                        |
    rigid_bind / rigid_skin  <-----------------------------------------+
    (tank) track_loops -> treads -> copy tread links

Model requirements: +Z forward, +X left, Y up, sitting on y = 0, pieces named
with a primitive ``name`` attribute. Wheels are pieces whose name contains
wheel/tire/tyre/rim; the body contains body/chassis/hull/frame/shell. Other
named pieces become rigid parts parented to the body (doors, antennae,
turret...). Pass ``wheels=[...]`` to skip auto-detection.

Wheel spin uses ``angle = distance / radius`` (radians), i.e. revolutions =
distance / (2*pi*radius), where "distance" is what *that wheel* travelled,
so inner and outer wheels spin at different rates in turns.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence, Tuple

from .. import compat, dynamics, network
from ..compat import LOG, require_hou
from ..core import guides, vehicle_math
from ..network import ParmSpec as P
from . import common

VEHICLE_TYPES = {"car": 0, "truck": 0, "bike": 1, "motorbike": 1, "tank": 2}


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def piece_bboxes(geo, attrib: str = "name") -> Dict[str, Tuple[Tuple[float, float, float], Tuple[float, float, float]]]:
    """{piece name: (min, max)} from a primitive string attribute."""
    h = require_hou()
    if geo.findPrimAttrib(attrib) is None:
        return {}
    boxes: Dict[str, "h.BoundingBox"] = {}
    for prim in geo.prims():
        name = prim.attribValue(attrib).split("/")[-1]
        if not name:
            continue
        bb = boxes.setdefault(name, h.BoundingBox())
        for vtx in prim.vertices():
            bb.enlargeToContain(vtx.point().position())
    return {k: (tuple(v.minvec()), tuple(v.maxvec())) for k, v in boxes.items()}


def detect(model_node, vehicle_type: str = "car"):
    """Return (wheels as dicts, body_center, extra_parts) for guides.vehicle."""
    geo = model_node.geometry()
    boxes = piece_bboxes(geo)
    if not boxes:
        raise compat.StudioError(
            f"{model_node.path()} has no primitive 'name' attribute; name the pieces "
            "(wheel_fl, wheel_fr, body...) or pass wheels=[...].")
    wheels, body, other = vehicle_math.classify_parts(boxes)
    if not wheels:
        raise compat.StudioError("No wheel pieces found (names containing wheel/tire/tyre/rim).")
    if vehicle_type in ("bike", "motorbike"):
        for w in wheels:
            w.steers = w.is_front
    if vehicle_type == "tank":
        for w in wheels:
            w.steers = False
    wheel_dicts = [dict(name=w.name, center=w.center, radius=w.radius, side=w.side,
                        steers=w.steers, drives=w.drives) for w in wheels]
    if body:
        mins = [boxes[b][0] for b in body]
        maxs = [boxes[b][1] for b in body]
        body_center = tuple(0.5 * (min(m[i] for m in mins) + max(m[i] for m in maxs)) for i in range(3))
    else:
        bb = geo.boundingBox()
        body_center = tuple(bb.center())
    parts = [(name, tuple(0.5 * (boxes[name][0][i] + boxes[name][1][i]) for i in range(3))) for name in other]
    LOG.info("Vehicle: %d wheels (%s), body pieces %s, %d parts", len(wheels),
             ", ".join(f"{w.name}{'*' if w.steers else ''}" for w in wheels), body, len(parts))
    return wheel_dicts, body_center, parts


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_vehicle(model=None, path=None, ground=None, vehicle_type: str = "car", name: str = "aks_vehicle",
                  wheels: Optional[Sequence[Dict[str, object]]] = None,
                  body_center: Optional[Tuple[float, float, float]] = None,
                  extra_parts: Optional[Sequence[Tuple[str, Tuple[float, float, float]]]] = None,
                  speed: float = 12.0, secondary: bool = True, tank_tracks: Optional[bool] = None):
    """Build a drivable vehicle rig. Returns the container OBJ node."""
    require_hou()
    vtype = VEHICLE_TYPES.get(vehicle_type, 0)
    geo = network.obj_container(name, clear=True)
    model_in = network.input_or_placeholder(geo, "model_in", model) if model is not None else None

    if model_in is not None and _has_packed(model_in):
        unpack = compat.create(geo, "unpack", "unpack")
        unpack.setInput(0, model_in)
        compat.set_parm(unpack, ("transfer_attributes", "transferattributes"), "name path", warn=False)
        model_in = unpack

    if wheels is None:
        if model_in is None:
            wheels, body_center, extra_parts = _demo_wheels(vehicle_type), (0.0, 0.8, 0.0), []
        else:
            wheels, auto_center, auto_parts = detect(model_in, vehicle_type)
            body_center = body_center or auto_center
            extra_parts = extra_parts if extra_parts is not None else auto_parts
    joints = guides.vehicle(wheels, body_center or (0.0, 0.8, 0.0), extra_parts or [])
    skel = common.skeleton_sop(geo, "guides", joints, template=f"vehicle_{vehicle_type}")
    rest = network.null(geo, "REST_SKELETON", skel)
    path_in = network.input_or_placeholder(geo, "path_in", path)
    ground_in = network.input_or_placeholder(geo, "ground_in", ground)

    drive = network.wrangle(geo, "drive", "vehicle_drive", "detail", inputs=[rest, path_in, ground_in],
                            parms=drive_parms(vtype, speed))
    anim = drive
    if secondary:
        anim = network.make_solver(geo, "dynamics", "vehicle_dynamics_step", inputs=[drive],
                                   run_over="detail", parms=dynamics_parms(vtype))
        if extra_parts:
            anim = dynamics.add_vibration(geo, anim, "part_*", amplitude=0.05, speed_gain=0.01,
                                          name="part_vibration")

    mesh_out = None
    if model_in is not None:
        mesh_out = common.skin(geo, model_in, rest, anim, method="rigid").deformed

    if tank_tracks or (tank_tracks is None and vtype == 2):
        treads = build_treads(geo, wheels, anim, ground_in)
        if mesh_out is not None and treads is not None:
            merge = compat.create(geo, "merge", "vehicle_with_treads")
            merge.setInput(0, mesh_out)
            merge.setInput(1, treads)
            mesh_out = merge
        elif treads is not None:
            mesh_out = treads

    outs = common.outputs(geo, rest, anim, mesh_out)
    network.note(geo, "Vehicle: wire a curve into path_in and a heightfield/mesh into ground_in.\n"
                      "Speed or a keyed 'Distance' channel drives everything (scrubbable);\n"
                      "only 'dynamics' (body springs, vibration, drift spin) is simulated.\n"
                      "Wheel points carry f@skid / f@spin_rate for skid marks and FX.", near=drive)
    network.finalize(geo, outs.get("mesh", outs["anim"]))
    return geo


def drive_parms(vtype: int, speed: float) -> List[P]:
    return [
        P("vehicle_type", "Vehicle Type", "menu", ["car", "bike", "tank"][vtype],
          menu=[("car", "Car / Truck"), ("bike", "Bike"), ("tank", "Tank (skid steer)")]),
        P("distance_mode", "Distance Mode", "menu", "speed",
          menu=[("speed", "Constant Speed"), ("keyed", "Keyed Distance Channel")]),
        P("speed", "Speed (m/s)", "float", speed, -40, 80),
        P("distance", "Distance (keyable)", "float", 0.0, 0, 1000),
        P("start_time", "Start Time", "float", 0.0, 0, 10),
        P("distance_offset", "Distance Offset", "float", 0.0, -100, 100),
        P("steer_lookahead", "Steer Look-ahead", "float", 1.0, 0, 10, folder="Steering"),
        P("ackermann", "Ackermann Steering", "toggle", True, folder="Steering"),
        P("max_steer", "Max Steer (deg)", "float", 38.0, 0, 70, folder="Steering"),
        P("wheelbase", "Wheelbase (0 = auto)", "float", 0.0, 0, 10, folder="Steering"),
        P("track_width", "Track Width (0 = auto)", "float", 0.0, 0, 5, folder="Steering"),
        P("drift_amount", "Drift Amount", "float", 0.0, 0, 1, folder="Drift"),
        P("grip", "Grip (m/s^2)", "float", 7.0, 0, 30, folder="Drift"),
        P("drift_gain", "Slip per m/s^2 (rad)", "float", 0.08, 0, 1, folder="Drift"),
        P("max_drift", "Max Drift Angle (deg)", "float", 35.0, 0, 90, folder="Drift"),
        P("countersteer", "Counter-steer", "float", 0.8, 0, 2, folder="Drift"),
        P("pitch_stiffness", "Pitch Stiffness (m/s^2 per rad)", "float", 120.0, 1, 1000, folder="Body"),
        P("max_pitch", "Max Body Pitch (deg)", "float", 4.0, 0, 30, folder="Body"),
        P("roll_stiffness", "Roll Stiffness (m/s^2 per rad)", "float", 90.0, 1, 1000, folder="Body"),
        P("max_roll", "Max Body Roll (deg)", "float", 5.0, 0, 30, folder="Body"),
        P("lean_gain", "Bike Lean Gain", "float", 1.0, 0, 2, folder="Body"),
        P("max_lean", "Bike Max Lean (deg)", "float", 50.0, 0, 70, folder="Body"),
        P("suspension_travel", "Suspension Travel", "float", 0.15, 0, 1, folder="Ground"),
        P("ride_height_offset", "Ride Height Offset", "float", 0.0, -1, 1, folder="Ground"),
        P("ray_probe", "Ground Ray Probe", "float", 50.0, 0, 500, folder="Ground"),
        P("sample_step", "Path Sample Step", "float", 0.1, 0.001, 2, folder="Ground"),
        P("curvature_window", "Curvature Window", "float", 1.5, 0.01, 20, folder="Ground"),
    ]


def dynamics_parms(vtype: int) -> List[P]:
    return [
        P("substeps", "Substeps", "int", 4, 1, 20),
        P("angular_stiffness", "Body Tilt Stiffness", "float", 60.0, 1, 500, folder="Body Springs"),
        P("angular_damping_ratio", "Body Tilt Damping Ratio", "float", 0.35, 0, 2, folder="Body Springs"),
        P("heave_stiffness", "Heave Stiffness", "float", 150.0, 1, 1000, folder="Body Springs"),
        P("heave_damping_ratio", "Heave Damping Ratio", "float", 0.3, 0, 2, folder="Body Springs"),
        P("bump_gain", "Bump Response", "float", 0.02 if vtype != 2 else 0.01, 0, 0.2, folder="Body Springs"),
        P("max_heave", "Max Heave", "float", 0.08, 0, 0.5, folder="Body Springs"),
        P("idle_amplitude", "Engine Idle Buzz", "float", 0.002 if vtype != 2 else 0.004, 0, 0.05, folder="Vibration"),
        P("idle_fade_speed", "Idle Fade Speed (m/s)", "float", 3.0, 0, 20, folder="Vibration"),
        P("road_amplitude", "Road Vibration per m/s", "float", 0.0004, 0, 0.01, folder="Vibration"),
        P("roughness_gain", "Terrain Roughness Gain", "float", 20.0, 0, 200, folder="Vibration"),
        P("vibration_frequency", "Vibration Frequency", "float", 22.0, 0, 120, folder="Vibration"),
        P("vibration_rotation", "Rotation per Unit", "float", 2.0, 0, 20, folder="Vibration"),
        P("drift_spin", "Drift Wheel Over-spin", "float", 1.5, 0, 10, folder="Drift"),
        P("max_drift_ref", "Drift Reference Angle (deg)", "float", 35.0, 1, 90, folder="Drift"),
    ]


def build_treads(geo, wheels: Sequence[Dict[str, object]], anim, ground_in, link_spacing: float = 0.12,
                 thickness: float = 0.03):
    """Track loops (Python SOP) -> tread link points -> copy a simple link shape."""
    loops = {"l": [], "r": []}
    xs = {"l": [], "r": []}
    for w in wheels:
        side = str(w.get("side", "c"))
        if side not in loops:
            continue
        c = w["center"]  # type: ignore[index]
        loops[side].append((c[2], c[1], float(w["radius"])))  # (z, y, r)
        xs[side].append(c[0])
    data = {}
    for side in ("l", "r"):
        if len(loops[side]) < 2:
            continue
        hull = vehicle_math.track_loop(loops[side], thickness)
        x = sum(xs[side]) / len(xs[side])
        data[side] = [[x, y, z] for z, y in hull]
    if not data:
        LOG.warning("Tank tracks need at least two wheels per side; skipping treads.")
        return None
    code = ("import json\nnode = hou.pwd()\ngeo = node.geometry()\n"
            "geo.addAttrib(hou.attribType.Prim, 'side', '')\n"
            f"loops = json.loads({json.dumps(data)!r})\n"
            "for side, pts in loops.items():\n"
            "    poly = geo.createPolygon(True)\n"
            "    for p in pts:\n"
            "        pt = geo.createPoint()\n"
            "        pt.setPosition(p)\n"
            "        poly.addVertex(pt)\n"
            "    poly.setAttribValue('side', side)\n")
    loops_node = network.python_sop(geo, "track_loops", code)
    treads = network.wrangle(geo, "treads", "tank_treads", "detail", inputs=[loops_node, anim, ground_in], parms=[
        P("link_spacing", "Link Spacing", "float", link_spacing, 0.01, 1),
        P("bottom_run_height", "Bottom Run Height (rest)", "float",
          min(float(w["radius"]) for w in wheels) * 0.5, 0, 2),
        P("link_thickness", "Link Thickness", "float", thickness, 0, 0.2),
        P("ray_probe", "Ground Ray Probe", "float", 50.0, 0, 500),
    ])
    link = compat.create(geo, "box", "tread_link")
    compat.set_parm(link, ("size",), (0.9 * 2 * 0.25, thickness, link_spacing * 0.85), warn=False)
    copy = compat.create(geo, "copytopoints", "copy_treads")
    copy.setInput(0, link)
    copy.setInput(1, treads)
    network.note(geo, "Tread link: replace 'tread_link' with your modelled link\n"
                      "(+Z along the track, Y out of the track).", near=link)
    return copy


def _has_packed(node) -> bool:
    geo = node.geometry()
    if geo is None:
        return False
    for prim in geo.prims():
        if "Packed" in prim.type().name() or prim.type().name() in ("PackedPrim", "AlembicRef", "PackedDisk"):
            return True
        break  # checking the first primitive is enough for typical imports
    return False


def _demo_wheels(vehicle_type: str) -> List[Dict[str, object]]:
    """Wheel layout used when no model is given (lets you test the drive)."""
    if vehicle_type in ("bike", "motorbike"):
        return [dict(name="front", center=(0.0, 0.33, 0.7), radius=0.33, side="c", steers=True),
                dict(name="rear", center=(0.0, 0.33, -0.7), radius=0.33, side="c", steers=False)]
    if vehicle_type == "tank":
        wheels = []
        for side, x in (("l", 1.4), ("r", -1.4)):
            for i, z in enumerate((-2.2, -1.2, -0.2, 0.8, 1.8)):
                wheels.append(dict(name=f"road_{side}{i}", center=(x, 0.35, z), radius=0.35, side=side,
                                   steers=False))
            wheels.append(dict(name=f"sprocket_{side}", center=(x, 0.6, 2.6), radius=0.3, side=side, steers=False))
            wheels.append(dict(name=f"idler_{side}", center=(x, 0.6, -2.9), radius=0.3, side=side, steers=False))
        return wheels
    return [dict(name="fl", center=(0.8, 0.34, 1.35), radius=0.34, side="l", steers=True),
            dict(name="fr", center=(-0.8, 0.34, 1.35), radius=0.34, side="r", steers=True),
            dict(name="rl", center=(0.8, 0.34, -1.35), radius=0.34, side="l", steers=False),
            dict(name="rr", center=(-0.8, 0.34, -1.35), radius=0.34, side="r", steers=False)]
