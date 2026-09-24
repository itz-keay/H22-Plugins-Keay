"""Procedural creature rigs: snake, insect/arachnid, quadruped, bird, jellyfish.

Every builder creates ``/obj/<name>`` containing::

    guides (Python SOP + init)          -> REST_SKELETON
    path / ground inputs (optional)
    <creature>_motion (wrangle, closed-form, scrubbable)
    secondary (spring chains on tails / antennae / tentacles, optional)
    skin (optional mesh)                -> OUT_ANIM_SKELETON / OUT_MESH

All motion parameters are spare parameters on the ``*_motion`` wrangle, and
all of them can be keyframed. Motion is driven by distance travelled (or time
for flight/swimming), so nothing needs a simulation cache except the optional
secondary spring chains.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .. import compat, dynamics, network
from ..compat import require_hou
from ..core import guides
from ..network import ParmSpec as P
from . import common

GAIT_MENU = [("auto", "Auto"), ("tripod", "Tripod"), ("wave", "Wave"), ("tetrapod", "Tetrapod"),
             ("walk", "Quadruped Walk"), ("trot", "Trot / Alternating"), ("gallop", "Gallop"),
             ("metachronal", "Metachronal (centipede)")]

_PATH_GROUND_PARMS = [
    P("ray_probe", "Ground Ray Probe", "float", 50.0, 0, 200, folder="Ground"),
    P("sample_step", "Path Sample Step", "float", 0.05, 0.001, 1, folder="Ground"),
]


def _setup(name: str, joints, template: str, path=None, ground=None,
           want_path: bool = True, want_ground: bool = True):
    geo = network.obj_container(name, clear=True)
    skel = common.skeleton_sop(geo, "guides", joints, template=template)
    rest = network.null(geo, "REST_SKELETON", skel)
    path_in = network.input_or_placeholder(geo, "path_in", path) if want_path else None
    ground_in = network.input_or_placeholder(geo, "ground_in", ground) if want_ground else None
    return geo, rest, path_in, ground_in


def _finish(geo, rest, anim, mesh, capture_method: str, note: str, near):
    mesh_out = None
    if mesh is not None:
        mesh_in = network.input_or_placeholder(geo, "mesh_in", mesh)
        mesh_out = common.skin(geo, mesh_in, rest, anim, method=capture_method).deformed
    outs = common.outputs(geo, rest, anim, mesh_out)
    network.note(geo, note, near=near)
    network.finalize(geo, outs.get("mesh", outs["anim"]))
    return geo


# ---------------------------------------------------------------------------
# Snake
# ---------------------------------------------------------------------------

def build_snake(path=None, ground=None, mesh=None, name: str = "aks_snake", num_joints: int = 40,
                length: float = 4.0, radius: float = 0.06, speed: float = 0.8,
                secondary: bool = True, capture_method: str = "biharmonic"):
    require_hou()
    geo, rest, path_in, ground_in = _setup(name, guides.snake(num_joints, length, radius), "snake", path, ground)
    motion = network.wrangle(geo, "snake_motion", "snake_drive", "detail",
                             inputs=[rest, path_in, ground_in], parms=[
        P("speed", "Speed (m/s)", "float", speed, -5, 5),
        P("start_time", "Start Time", "float", 0.0, 0, 10),
        P("distance_offset", "Distance Offset", "float", length, -10, 10,
          help="Head starts this far along the path (default = body length, so the tail starts on the path)."),
        P("amplitude", "Undulation Amplitude", "float", 0.18 * length / 4.0, 0, 1, folder="Undulation"),
        P("wavelength", "Wavelength", "float", 0.45 * length, 0.05, 5, folder="Undulation"),
        P("phase_speed", "Wave Phase Speed", "float", 0.0, -20, 20, folder="Undulation",
          help="0 = pure serpentine (body follows one track). >0 adds swimming-like slip."),
        P("head_ramp", "Head Ramp Length", "float", 0.1 * length, 0, 2, folder="Undulation"),
        P("tail_taper", "Tail Taper", "float", 0.3, 0, 1, folder="Undulation"),
        P("twist", "Twist (deg)", "float", 12.0, 0, 90, folder="Undulation"),
        P("bank_gain", "Bank Gain", "float", 0.3, 0, 2, folder="Undulation"),
        P("head_lift", "Head Lift", "float", 0.05, 0, 1, folder="Head"),
        P("head_lift_length", "Head Lift Length", "float", 0.12 * length, 0, 2, folder="Head"),
        P("body_radius", "Body Radius", "float", radius, 0, 1, folder="Ground"),
        P("ground_follow", "Ground Follow", "float", 1.0, 0, 1, folder="Ground"),
    ] + _PATH_GROUND_PARMS)
    anim = motion
    if secondary:
        anim = dynamics.add_spring_chain(geo, anim, "spine_*", mode="jiggle",
                                         goal_stiffness=320.0, damping=18.0, amount=0.35, name="body_jiggle")
    return _finish(geo, rest, anim, mesh, capture_method,
                   "Snake: wire a curve into path_in and a heightfield or mesh into ground_in.\n"
                   "Every spine joint follows the track the head already travelled.", motion)


# ---------------------------------------------------------------------------
# Insects / arachnids / quadrupeds (shared legged solver)
# ---------------------------------------------------------------------------

def _legged(name, joints, template, path, ground, mesh, speed, stride, gait, step_height,
            pole_mode, secondary_joints, capture_method):
    geo, rest, path_in, ground_in = _setup(name, joints, template, path, ground)
    motion = network.wrangle(geo, f"{template}_motion", "insect_walk", "detail",
                             inputs=[rest, path_in, ground_in], parms=[
        P("speed", "Speed (m/s)", "float", speed, -5, 5),
        P("start_time", "Start Time", "float", 0.0, 0, 10),
        P("distance_offset", "Distance Offset", "float", 0.0, -10, 10),
        P("stride", "Stride Length", "float", stride, 0.01, 5, folder="Gait"),
        P("gait", "Gait", "menu", gait, menu=GAIT_MENU, folder="Gait"),
        P("duty_override", "Duty Factor Override (0 = gait default)", "float", 0.0, 0, 0.95, folder="Gait"),
        P("step_height", "Step Height", "float", step_height, 0, 1, folder="Gait"),
        P("body_bob", "Body Bob", "float", 0.02, 0, 0.3, folder="Gait"),
        P("slope_align", "Align Body to Slope", "float", 0.7, 0, 1, folder="Ground"),
        P("pole_mode", "Knee Mode", "menu", "insect" if pole_mode == 0 else "quadruped",
          menu=[("insect", "Insect (knees up/out)"), ("quadruped", "Quadruped (knees fore/aft)")], folder="Legs"),
        P("front_knee_direction", "Front Knee Direction", "float", 1.0, -1, 1, folder="Legs"),
        P("hind_knee_direction", "Hind Knee Direction", "float", -1.0, -1, 1, folder="Legs"),
    ] + _PATH_GROUND_PARMS)
    anim = motion
    if secondary_joints:
        anim = dynamics.add_spring_chain(geo, anim, secondary_joints, mode="chain",
                                         goal_stiffness=120.0, damping=8.0, amount=0.8)
    return _finish(geo, rest, anim, mesh, capture_method,
                   f"{template.capitalize()}: feet plant by distance travelled (no sliding).\n"
                   "Change gait, stride and step height on the motion node.", motion)


def build_insect(path=None, ground=None, mesh=None, name: str = "aks_insect", num_legs: int = 6,
                 body_length: float = 1.0, leg_span: float = 1.4, speed: float = 0.6,
                 gait: str = "tripod", capture_method: str = "proximity"):
    """Ant/beetle style hexapod (or any even leg count with the metachronal gait)."""
    require_hou()
    joints = guides.insect(num_legs=num_legs, body_length=body_length, leg_span=leg_span)
    return _legged(name, joints, "insect", path, ground, mesh, speed, 0.35 * leg_span, gait,
                   0.12 * leg_span, 0, "antenna_*", capture_method)


def build_spider(path=None, ground=None, mesh=None, name: str = "aks_spider", leg_span: float = 1.6,
                 speed: float = 0.7, capture_method: str = "proximity"):
    require_hou()
    joints = guides.insect(num_legs=8, body_length=0.8, leg_span=leg_span, antennae=False)
    return _legged(name, joints, "spider", path, ground, mesh, speed, 0.3 * leg_span, "trot",
                   0.1 * leg_span, 0, "", capture_method)


def build_quadruped(path=None, ground=None, mesh=None, name: str = "aks_quadruped", length: float = 1.6,
                    height: float = 1.0, speed: float = 1.4, gait: str = "walk",
                    capture_method: str = "biharmonic"):
    require_hou()
    joints = guides.quadruped(length=length, height=height)
    return _legged(name, joints, "quadruped", path, ground, mesh, speed, 0.6 * length, gait,
                   0.12 * height, 1, "tail_*", capture_method)


# ---------------------------------------------------------------------------
# Bird
# ---------------------------------------------------------------------------

def build_bird(path=None, mesh=None, name: str = "aks_bird", wingspan: float = 1.2,
               speed: float = 6.0, capture_method: str = "biharmonic"):
    require_hou()
    geo, rest, path_in, _ = _setup(name, guides.bird(wingspan=wingspan), "bird", path, None,
                                   want_ground=False)
    motion = network.wrangle(geo, "bird_motion", "bird_flap", "detail", inputs=[rest, path_in], parms=[
        P("speed", "Speed (m/s)", "float", speed, 0, 30),
        P("start_time", "Start Time", "float", 0.0, 0, 10),
        P("distance_offset", "Distance Offset", "float", 0.0, -10, 10),
        P("cruise_height", "Cruise Height (no path)", "float", 3.0, 0, 50),
        P("flap_frequency", "Flap Frequency (Hz)", "float", 3.0, 0, 20, folder="Wings"),
        P("flap_amplitude", "Flap Amplitude (deg)", "float", 55.0, 0, 90, folder="Wings"),
        P("segment_lag", "Segment Lag (deg)", "float", 35.0, 0, 90, folder="Wings"),
        P("flap_amount", "Flap Amount (0 = glide)", "float", 1.0, 0, 1, folder="Wings"),
        P("fold", "Fold", "float", 0.0, 0, 1, folder="Wings"),
        P("drag_sweep", "Velocity Drag Sweep (deg)", "float", 20.0, 0, 90, folder="Wings"),
        P("glide_dihedral", "Glide Dihedral (deg)", "float", 8.0, -30, 30, folder="Wings"),
        P("body_bob", "Body Bob", "float", 0.03, 0, 0.3, folder="Body"),
        P("bank_gain", "Bank Gain", "float", 1.0, 0, 2, folder="Body"),
        P("max_bank", "Max Bank (deg)", "float", 60.0, 0, 90, folder="Body"),
        P("tail_spread", "Tail Spread (deg)", "float", 25.0, 0, 60, folder="Body"),
        P("sample_step", "Path Sample Step", "float", 0.1, 0.001, 1, folder="Body"),
    ])
    anim = dynamics.add_velocity_drag(geo, motion, "tail_feather_* wing_*_hand", name="feather_drag")
    return _finish(geo, rest, anim, mesh, capture_method,
                   "Bird: key 'Flap Amount' and 'Fold' for take-off, glide and landing.\n"
                   "Wing segments flap with automatic follow-through lag.", motion)


# ---------------------------------------------------------------------------
# Jellyfish / octopus
# ---------------------------------------------------------------------------

def build_jellyfish(mesh=None, name: str = "aks_jellyfish", bell_radius: float = 0.5,
                    tentacles: int = 8, tentacle_joints: int = 12, tentacle_length: float = 1.6,
                    capture_method: str = "proximity"):
    require_hou()
    joints = guides.jellyfish(bell_radius=bell_radius, tentacles=tentacles,
                              tentacle_joints=tentacle_joints, tentacle_length=tentacle_length)
    geo, rest, _, _ = _setup(name, joints, "jellyfish", want_path=False, want_ground=False)
    motion = network.wrangle(geo, "jellyfish_motion", "jellyfish_swim", "detail", inputs=[rest], parms=[
        P("start_time", "Start Time", "float", 0.0, 0, 10),
        P("pulse_frequency", "Pulse Frequency (Hz)", "float", 0.6, 0, 5),
        P("contract_ratio", "Contraction Ratio", "float", 0.3, 0.05, 0.95),
        P("bell_squeeze", "Bell Squeeze", "float", 0.35, 0, 1),
        P("bell_radius", "Bell Radius", "float", bell_radius, 0.01, 5),
        P("thrust", "Thrust per Pulse", "float", 0.35, 0, 5),
        P("drift", "Drift (m/s)", "float", 0.02, -1, 1),
        P("swim_direction", "Swim Direction", "vector", (0.0, 1.0, 0.0), -1, 1),
        P("tentacle_lag", "Tentacle Lag (s/joint)", "float", 0.06, 0, 0.5, folder="Tentacles"),
        P("curl", "Curl Sway", "float", 0.12, 0, 1, folder="Tentacles"),
        P("curl_frequency", "Curl Frequency", "float", 0.4, 0, 5, folder="Tentacles"),
    ])
    return _finish(geo, rest, motion, mesh, capture_method,
                   "Jellyfish: pulses are closed form (fast contraction, slow relax).\n"
                   "Tentacles trail by sampling the bell motion back in time.", motion)


BUILDERS = {
    "snake": build_snake,
    "insect": build_insect,
    "spider": build_spider,
    "quadruped": build_quadruped,
    "bird": build_bird,
    "jellyfish": build_jellyfish,
}
