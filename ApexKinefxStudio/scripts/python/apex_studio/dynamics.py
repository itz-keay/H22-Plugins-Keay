"""Secondary motion: spring chains, jiggle, vibration, velocity drag.

Each function takes an animated skeleton SOP and returns the new last node,
so they chain::

    anim = dynamics.add_spring_chain(geo, anim, "tail_*")
    anim = dynamics.add_vibration(geo, anim, "part_* body", amplitude=0.2)
    anim = dynamics.add_velocity_drag(geo, anim, "ear_*")

* ``add_spring_chain`` - verlet chain in a SOP Solver: goal stiffness toward
  the animation, damping, gravity, air drag, bone-length constraint, parent
  re-aiming. ``mode="jiggle"`` = lag/overshoot without length constraints.
* ``add_native_secondary`` - SideFX's KineFX Secondary Motion SOP (when you
  prefer the stock tool; parameters vary by build).
* ``add_vibration`` - stateless band-limited noise, amplitude can follow the
  vehicle speed.
* ``add_velocity_drag`` - stateless lag from velocity (uses a Time Shift).

Joint selection uses Houdini wildcard patterns separated by spaces. A point
attribute ``f@secondary_amount`` (0..1), e.g. painted or set by a wrangle,
scales the spring chain per joint.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from . import compat, network
from .compat import LOG
from .network import ParmSpec as P


def add_spring_chain(parent, anim, joints: str, mode: str = "chain", goal_stiffness: float = 150.0,
                     damping: float = 10.0, air_drag: float = 0.2,
                     gravity: Tuple[float, float, float] = (0.0, -9.81, 0.0), amount: float = 1.0,
                     substeps: int = 4, pin_chain_root: bool = True, name: str = "spring_chain"):
    return network.make_solver(parent, name, "spring_chain_step", inputs=[anim], run_over="detail", parms=[
        P("joints", "Joints", "string", joints),
        P("mode", "Mode", "menu", mode, menu=[("chain", "Chain (length preserving)"), ("jiggle", "Jiggle")]),
        P("amount", "Amount", "float", amount, 0, 1),
        P("goal_stiffness", "Goal Stiffness", "float", goal_stiffness, 0, 1000),
        P("damping", "Damping", "float", damping, 0, 100),
        P("air_drag", "Air Drag", "float", air_drag, 0, 5),
        P("gravity", "Gravity", "vector", gravity, -20, 20),
        P("substeps", "Substeps", "int", substeps, 1, 20),
        P("pin_chain_root", "Pin Chain Root", "toggle", pin_chain_root),
    ])


def add_native_secondary(parent, anim, joints: str, name: str = "secondary_motion"):
    """KineFX Secondary Motion SOP (stock). Returns ``anim`` unchanged if missing."""
    node = compat.create(parent, "secondary_motion", name, required=False)
    if node is None:
        LOG.warning("KineFX Secondary Motion SOP not available; use add_spring_chain instead.")
        return anim
    node.setInput(0, anim)
    compat.set_parm(node, ("group", "joints", "jointgroup"), joints)
    return node


def add_vibration(parent, anim, joints: str, amplitude: float = 0.1, frequency: float = 18.0,
                  speed_gain: float = 0.02, rotation_degrees: float = 1.5, translation: float = 0.005,
                  speed_attrib: str = "speed", name: str = "vibration"):
    return network.wrangle(parent, name, "vibration", "detail", inputs=[anim], parms=[
        P("joints", "Joints", "string", joints),
        P("amplitude", "Base Amplitude", "float", amplitude, 0, 1),
        P("speed_attrib", "Speed Detail Attribute", "string", speed_attrib),
        P("speed_gain", "Amplitude per m/s", "float", speed_gain, 0, 0.5),
        P("frequency", "Frequency", "float", frequency, 0, 100),
        P("rotation_degrees", "Rotation (deg at amplitude 1)", "float", rotation_degrees, 0, 20),
        P("translation", "Translation (at amplitude 1)", "float", translation, 0, 0.2),
    ])


def add_velocity_drag(parent, anim, joints: str, degrees_per_unit_speed: float = 4.0,
                      max_degrees: float = 35.0, name: str = "velocity_drag"):
    prev = compat.create(parent, "timeshift", f"{name}_prev_frame")
    prev.setInput(0, anim)
    compat.set_expression(prev, "frame", "$F - 1")
    return network.wrangle(parent, name, "velocity_drag", "detail", inputs=[anim, prev], parms=[
        P("joints", "Joints", "string", joints),
        P("degrees_per_unit_speed", "Degrees per m/s", "float", degrees_per_unit_speed, 0, 30),
        P("max_degrees", "Max Degrees", "float", max_degrees, 0, 90),
    ])
