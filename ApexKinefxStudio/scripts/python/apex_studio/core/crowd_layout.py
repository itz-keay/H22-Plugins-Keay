"""Crowd layouts and the declarative state machine definition (pure data).

The state machine is evaluated per agent per frame by
``vex/snippets/crowd_state_machine.vfl`` inside a SOP Solver. This module
defines the data model and a reference Python implementation of one step,
used by the tests and to serialise the machine into detail attributes.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]


# ---------------------------------------------------------------------------
# Layouts
# ---------------------------------------------------------------------------

def stadium_seats(rows: int = 12, seats_per_row: int = 60, inner_radius: float = 30.0,
                  row_depth: float = 0.9, row_height: float = 0.45, arc_degrees: float = 120.0,
                  seat_jitter: float = 0.05, seed: int = 7) -> List[Tuple[Vec3, float]]:
    """Tiered arc of seats facing the arena centre.

    Returns [(position, yaw_radians)] where yaw turns +Z toward the centre.
    Row r sits at radius ``inner_radius + r*row_depth`` and height ``r*row_height``.
    """
    rng = random.Random(seed)
    out: List[Tuple[Vec3, float]] = []
    arc = math.radians(arc_degrees)
    for r in range(rows):
        radius = inner_radius + r * row_depth
        count = max(1, int(round(seats_per_row * radius / inner_radius)))
        for s in range(count):
            t = 0.5 if count == 1 else s / (count - 1)
            a = -arc * 0.5 + arc * t
            x = math.sin(a) * radius + rng.uniform(-seat_jitter, seat_jitter)
            z = math.cos(a) * radius + rng.uniform(-seat_jitter, seat_jitter)
            yaw = math.atan2(-x, -z)  # face the origin
            out.append(((x, r * row_height, z), yaw))
    return out


def grid_layout(count: int, spacing: float = 1.2, jitter: float = 0.3, seed: int = 3) -> List[Vec3]:
    rng = random.Random(seed)
    side = max(1, int(math.ceil(math.sqrt(count))))
    pts = []
    for i in range(count):
        gx, gz = i % side, i // side
        pts.append(((gx - side / 2.0) * spacing + rng.uniform(-jitter, jitter), 0.0,
                    (gz - side / 2.0) * spacing + rng.uniform(-jitter, jitter)))
    return pts


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

@dataclass
class CrowdState:
    name: str
    clip: str
    speed: float = 0.0  # m/s the agent moves while in this state
    loop: bool = True
    ragdoll: bool = False


@dataclass
class CrowdTransition:
    src: str  # state name or "*" for any
    dst: str
    trigger: str  # "volume:<name>", "time:<frame>", "random:<prob_per_sec>", "near:<radius>", "clip_end"
    blend: float = 0.3  # seconds


@dataclass
class StateMachine:
    states: List[CrowdState]
    transitions: List[CrowdTransition]
    initial: str

    def index(self, name: str) -> int:
        for i, s in enumerate(self.states):
            if s.name == name:
                return i
        raise KeyError(name)

    def to_detail(self) -> Dict[str, list]:
        """Flatten to parallel arrays for detail attributes read by the VEX."""
        return {
            "sm_state_names": [s.name for s in self.states],
            "sm_state_clips": [s.clip for s in self.states],
            "sm_state_speeds": [float(s.speed) for s in self.states],
            "sm_state_loop": [int(s.loop) for s in self.states],
            "sm_state_ragdoll": [int(s.ragdoll) for s in self.states],
            "sm_tr_src": [(-1 if t.src == "*" else self.index(t.src)) for t in self.transitions],
            "sm_tr_dst": [self.index(t.dst) for t in self.transitions],
            "sm_tr_kind": [t.trigger.split(":", 1)[0] for t in self.transitions],
            "sm_tr_arg": [(t.trigger.split(":", 1) + [""])[1] for t in self.transitions],
            "sm_tr_blend": [float(t.blend) for t in self.transitions],
            "sm_initial": [self.index(self.initial)],
        }


def default_walk_run_ragdoll() -> StateMachine:
    """Walk -> run inside a 'panic' volume, run -> ragdoll inside a 'hazard' volume."""
    return StateMachine(
        states=[
            CrowdState("walk", "walk", speed=1.4),
            CrowdState("run", "run", speed=4.0),
            CrowdState("ragdoll", "run", speed=0.0, loop=False, ragdoll=True),
        ],
        transitions=[
            CrowdTransition("walk", "run", "volume:panic", blend=0.4),
            CrowdTransition("run", "ragdoll", "volume:hazard", blend=0.0),
            CrowdTransition("walk", "ragdoll", "volume:hazard", blend=0.0),
        ],
        initial="walk",
    )


def default_stadium() -> StateMachine:
    """Idle -> cheer on a random/time trigger, cheer -> idle when the clip ends."""
    return StateMachine(
        states=[CrowdState("idle", "idle"), CrowdState("cheer", "cheer", loop=False)],
        transitions=[
            CrowdTransition("idle", "cheer", "random:0.08", blend=0.25),
            CrowdTransition("cheer", "idle", "clip_end", blend=0.4),
        ],
        initial="idle",
    )


def step_reference(sm: StateMachine, state: int, time_in_state: float, dt: float,
                   in_volumes: Sequence[str], rand01: float, clip_length: float,
                   frame: float) -> Tuple[int, float, float]:
    """Reference step: returns (new_state, new_time_in_state, blend_seconds).

    First matching transition wins (declaration order), mirroring the VEX.
    """
    cur = sm.states[state]
    for t in sm.transitions:
        if t.src != "*" and t.src != cur.name:
            continue
        kind, _, arg = t.trigger.partition(":")
        fire = False
        if kind == "volume":
            fire = arg in in_volumes
        elif kind == "time":
            fire = frame >= float(arg)
        elif kind == "random":
            fire = rand01 < float(arg) * dt
        elif kind == "clip_end":
            fire = (not cur.loop) and time_in_state >= clip_length
        if fire:
            return sm.index(t.dst), 0.0, t.blend
    return state, time_in_state + dt, 0.0
