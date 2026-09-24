"""Distance-driven gait cycles for N-legged creatures.

Feet are driven by *distance travelled*, not time, so they never slide and
the animation is fully procedural (scrubbable, no simulation cache):

* phase ``p = frac(d / stride + offset)``
* stance while ``p < duty``: the foot is planted at the body's "home" foot
  position evaluated at distance ``d_plant = (d - p*stride) + duty*stride/2``
  (mid-stance), so as the body moves on, the foot stays put.
* swing otherwise: the foot travels from ``d_plant`` to ``d_plant + stride``
  (the next plant) along an eased arc with height ``h*sin(pi*t)``.

``vex/include/aks_gait.h`` implements the same thing per frame.

Leg ordering convention: left legs front-to-back, then right legs
front-to-back. For a hexapod: L1 L2 L3 R1 R2 R3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

#: gait -> (duty factor, {legs: offsets})
GAITS: Dict[str, Tuple[float, Dict[int, List[float]]]] = {
    # Hexapods / insects
    "tripod": (0.5, {6: [0.0, 0.5, 0.0, 0.5, 0.0, 0.5]}),
    "tetrapod": (2.0 / 3.0, {6: [0.0, 1 / 3, 2 / 3, 2 / 3, 0.0, 1 / 3]}),
    "wave": (5.0 / 6.0, {6: [2 / 6, 1 / 6, 0.0, 5 / 6, 4 / 6, 3 / 6]}),
    # Arachnids (alternating tetrapod)
    "alternating_tetrapod": (0.55, {8: [0.0, 0.5, 0.0, 0.5, 0.5, 0.0, 0.5, 0.0]}),
    # Quadrupeds: L-front, L-hind, R-front, R-hind
    "walk": (0.75, {4: [0.25, 0.0, 0.75, 0.5]}),
    "trot": (0.5, {4: [0.0, 0.5, 0.5, 0.0]}),
    "pace": (0.5, {4: [0.0, 0.0, 0.5, 0.5]}),
    "canter": (0.4, {4: [0.3, 0.0, 0.5, 0.3]}),
    "gallop": (0.35, {4: [0.5, 0.0, 0.6, 0.1]}),
    "bound": (0.35, {4: [0.5, 0.0, 0.5, 0.0]}),
    # Bipeds
    "biped_walk": (0.6, {2: [0.0, 0.5]}),
    "biped_run": (0.35, {2: [0.0, 0.5]}),
}


def gait_offsets(num_legs: int, gait: str = "auto") -> Tuple[float, List[float]]:
    """Return (duty, per-leg phase offsets) for ``num_legs`` legs.

    ``auto`` picks tripod (6), alternating tetrapod (8), trot (4), biped walk
    (2), or a metachronal wave for any other count.
    """
    if gait == "auto":
        gait = {2: "biped_walk", 4: "trot", 6: "tripod", 8: "alternating_tetrapod"}.get(num_legs, "metachronal")
    if gait in GAITS and num_legs in GAITS[gait][1]:
        duty, table = GAITS[gait]
        return duty, list(table[num_legs])
    # Metachronal wave (centipedes, custom counts): back-to-front ripple per
    # side, right side half a cycle behind the left.
    per_side = max(1, (num_legs + 1) // 2)
    offsets = []
    for i in range(num_legs):
        side = 0 if i < per_side else 1
        idx = i if side == 0 else i - per_side
        offsets.append(((per_side - 1 - idx) / float(per_side) + 0.5 * side) % 1.0)
    duty = GAITS.get(gait, (0.7, {}))[0] if gait in GAITS else 0.7
    return duty, offsets


@dataclass
class FootState:
    phase: float
    in_stance: bool
    swing_t: float  # 0..1 during swing, 0 during stance
    plant_distance: float  # where the current/last stance is planted
    next_plant_distance: float  # where the swing will land
    lift: float  # 0..1 swing height factor


def foot_state(distance: float, stride: float, offset: float, duty: float) -> FootState:
    """Closed-form foot state for a given travelled ``distance`` (see module doc)."""
    if stride <= 0.0:
        raise ValueError("stride must be > 0")
    duty = min(max(duty, 0.05), 0.95)
    u = distance / stride + offset
    phase = u - math.floor(u)
    cycle_start = distance - phase * stride
    plant = cycle_start + duty * stride * 0.5
    if phase < duty:
        return FootState(phase, True, 0.0, plant, plant, 0.0)
    t = (phase - duty) / (1.0 - duty)
    return FootState(phase, False, t, plant, plant + stride, math.sin(math.pi * t))


def ease(t: float) -> float:
    """Smoothstep used for the horizontal swing interpolation."""
    t = min(max(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def foot_distance(distance: float, stride: float, offset: float, duty: float) -> Tuple[float, float]:
    """(path distance to evaluate the foot's home at, lift 0..1).

    Convenience wrapper: during stance returns the plant distance; during swing
    an eased blend between plants.
    """
    st = foot_state(distance, stride, offset, duty)
    if st.in_stance:
        return st.plant_distance, 0.0
    return st.plant_distance + ease(st.swing_t) * stride, st.lift
