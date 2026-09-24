"""Guide skeleton templates (pure data).

Each template returns a list of :class:`Joint` in rest pose. Rest orientation
is the identity (world aligned), which KineFX handles fine and keeps the
animation VEX simple. Positions are in metres with Y up and +Z forward, and
the creature is centred on the origin, standing on Y=0.

Extra per-joint attributes (``attrs``) are written as point attributes by the
Houdini side (``rigging.common.skeleton_sop``). The animation VEX uses them:

* ``chain`` (s): chain name, e.g. ``leg_L1``, ``spine``, ``wing_l``, ``tentacle_3``
* ``chain_index`` (i): index of the joint along its chain, root = 0
* ``leg`` (i): leg number for gait-driven legs, -1 otherwise
* ``side`` (s): ``l``/``r``/``c``
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .profiles import CANONICAL_PARENTS

Vec3 = Tuple[float, float, float]


@dataclass
class Joint:
    name: str
    parent: Optional[str]
    pos: Vec3
    attrs: Dict[str, object] = field(default_factory=dict)


def _add(joints: List[Joint], name: str, parent: Optional[str], pos: Sequence[float], **attrs) -> Joint:
    j = Joint(name, parent, (float(pos[0]), float(pos[1]), float(pos[2])), dict(attrs))
    joints.append(j)
    return j


def validate(joints: Sequence[Joint]) -> None:
    """Raise ValueError on duplicate names, unknown parents or cycles."""
    names = [j.name for j in joints]
    if len(set(names)) != len(names):
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise ValueError(f"duplicate joint names: {dupes}")
    by_name = {j.name: j for j in joints}
    for j in joints:
        if j.parent is not None and j.parent not in by_name:
            raise ValueError(f"joint {j.name} has unknown parent {j.parent}")
    for j in joints:
        seen = set()
        cur: Optional[str] = j.name
        while cur is not None:
            if cur in seen:
                raise ValueError(f"cycle through {cur}")
            seen.add(cur)
            cur = by_name[cur].parent


# ---------------------------------------------------------------------------
# Biped (canonical names so retargeting maps 1:1)
# ---------------------------------------------------------------------------

def biped(height: float = 1.8, fingers: bool = False) -> List[Joint]:
    h = height
    j: List[Joint] = []
    _add(j, "root", None, (0, 0, 0), chain="root")
    _add(j, "hips", "root", (0, 0.53 * h, 0), chain="spine", chain_index=0)
    _add(j, "spine_01", "hips", (0, 0.60 * h, 0.0), chain="spine", chain_index=1)
    _add(j, "spine_02", "spine_01", (0, 0.67 * h, 0.0), chain="spine", chain_index=2)
    _add(j, "spine_03", "spine_02", (0, 0.74 * h, 0.0), chain="spine", chain_index=3)
    _add(j, "neck", "spine_03", (0, 0.83 * h, 0.0), chain="neck", chain_index=0)
    _add(j, "head", "neck", (0, 0.88 * h, 0.01 * h), chain="neck", chain_index=1)
    _add(j, "head_end", "head", (0, 1.0 * h, 0.01 * h), chain="neck", chain_index=2)
    for s, sx in (("l", 1.0), ("r", -1.0)):
        _add(j, f"{s}_clavicle", "spine_03", (sx * 0.02 * h, 0.80 * h, 0.02 * h), chain=f"arm_{s}", chain_index=0, side=s)
        _add(j, f"{s}_upperarm", f"{s}_clavicle", (sx * 0.10 * h, 0.80 * h, 0), chain=f"arm_{s}", chain_index=1, side=s)
        _add(j, f"{s}_forearm", f"{s}_upperarm", (sx * 0.26 * h, 0.80 * h, -0.01 * h), chain=f"arm_{s}", chain_index=2, side=s)
        _add(j, f"{s}_hand", f"{s}_forearm", (sx * 0.41 * h, 0.80 * h, 0), chain=f"arm_{s}", chain_index=3, side=s)
        _add(j, f"{s}_thigh", "hips", (sx * 0.055 * h, 0.51 * h, 0), chain=f"leg_{s}", chain_index=0, side=s, leg=0 if s == "l" else 1)
        _add(j, f"{s}_shin", f"{s}_thigh", (sx * 0.055 * h, 0.28 * h, 0.01 * h), chain=f"leg_{s}", chain_index=1, side=s)
        _add(j, f"{s}_foot", f"{s}_shin", (sx * 0.055 * h, 0.05 * h, -0.01 * h), chain=f"leg_{s}", chain_index=2, side=s)
        _add(j, f"{s}_toe", f"{s}_foot", (sx * 0.055 * h, 0.01 * h, 0.08 * h), chain=f"leg_{s}", chain_index=3, side=s)
        _add(j, f"{s}_toe_end", f"{s}_toe", (sx * 0.055 * h, 0.01 * h, 0.12 * h), chain=f"leg_{s}", chain_index=4, side=s)
        if fingers:
            for fi, finger in enumerate(("thumb", "index", "middle", "ring", "pinky")):
                z = (0.02 - 0.01 * fi) * h
                base_x = sx * (0.43 * h if finger != "thumb" else 0.42 * h)
                for k in range(3):
                    name = f"{s}_{finger}_0{k + 1}"
                    parent = f"{s}_hand" if k == 0 else f"{s}_{finger}_0{k}"
                    _add(j, name, parent, (base_x + sx * 0.022 * h * k, 0.80 * h - (0.01 * h if finger == "thumb" else 0), z),
                         chain=f"{finger}_{s}", chain_index=k, side=s)
    unknown = [jt.name for jt in j if jt.name not in CANONICAL_PARENTS]
    if unknown:
        raise AssertionError(f"biped template drifted from canonical names: {unknown}")
    _defaults(j)
    return j


# ---------------------------------------------------------------------------
# Quadruped
# ---------------------------------------------------------------------------

def quadruped(length: float = 1.6, height: float = 1.0, tail_joints: int = 5,
              neck_joints: int = 3) -> List[Joint]:
    L, H = length, height
    j: List[Joint] = []
    _add(j, "root", None, (0, 0, 0), chain="root")
    spine_n = 4
    hip_z, chest_z = -0.35 * L, 0.35 * L
    for i in range(spine_n):
        t = i / (spine_n - 1)
        z = hip_z + (chest_z - hip_z) * t
        _add(j, f"spine_{i:02d}", "root" if i == 0 else f"spine_{i - 1:02d}", (0, 0.62 * H, z),
             chain="spine", chain_index=i)
    for i in range(neck_joints):
        _add(j, f"neck_{i:02d}", f"spine_{spine_n - 1:02d}" if i == 0 else f"neck_{i - 1:02d}",
             (0, 0.62 * H + 0.12 * H * (i + 1), chest_z + 0.08 * L * (i + 1)), chain="neck", chain_index=i)
    _add(j, "head", f"neck_{neck_joints - 1:02d}", (0, 0.62 * H + 0.12 * H * (neck_joints + 1), chest_z + 0.08 * L * (neck_joints + 1)),
         chain="neck", chain_index=neck_joints)
    for i in range(tail_joints):
        _add(j, f"tail_{i:02d}", "spine_00" if i == 0 else f"tail_{i - 1:02d}",
             (0, 0.62 * H - 0.04 * H * i, hip_z - 0.1 * L * (i + 1)), chain="tail", chain_index=i)
    leg_index = 0
    for s, sx in (("l", 1.0), ("r", -1.0)):
        for tag, z, attach in (("front", chest_z, f"spine_{spine_n - 1:02d}"), ("hind", hip_z, "spine_00")):
            chain = f"leg_{s}_{tag}"
            x = sx * 0.14 * L
            # 4 joints: upper, lower, ankle (digitigrade), toe
            pts = [(x, 0.58 * H, z), (x, 0.34 * H, z + (0.04 if tag == "front" else -0.06) * L),
                   (x, 0.10 * H, z - (0.0 if tag == "front" else 0.06) * L), (x, 0.0, z + 0.03 * L)]
            parent = attach
            for k, p in enumerate(pts):
                name = f"{chain}_{k:02d}"
                _add(j, name, parent, p, chain=chain, chain_index=k, side=s,
                     leg=leg_index if k == 0 else -1)
                parent = name
            leg_index += 1
    _defaults(j)
    return j


# ---------------------------------------------------------------------------
# Insects / arachnids (N legs, 3 segments + foot tip)
# ---------------------------------------------------------------------------

def insect(num_legs: int = 6, body_length: float = 1.0, leg_span: float = 1.4,
           body_height: float = 0.25, antennae: bool = True) -> List[Joint]:
    if num_legs % 2:
        raise ValueError("num_legs must be even")
    j: List[Joint] = []
    L = body_length
    _add(j, "root", None, (0, 0, 0), chain="root")
    _add(j, "thorax", "root", (0, body_height, 0.0), chain="body", chain_index=0)
    _add(j, "abdomen", "thorax", (0, body_height * 1.05, -0.35 * L), chain="body", chain_index=1)
    _add(j, "abdomen_end", "abdomen", (0, body_height * 0.9, -0.75 * L), chain="body", chain_index=2)
    _add(j, "head", "thorax", (0, body_height * 1.1, 0.30 * L), chain="head", chain_index=0)
    if antennae:
        for s, sx in (("l", 1.0), ("r", -1.0)):
            prev = "head"
            for k in range(4):
                name = f"antenna_{s}_{k:02d}"
                _add(j, name, prev, (sx * (0.04 + 0.05 * k) * L, body_height * (1.2 + 0.25 * k), (0.36 + 0.12 * k) * L),
                     chain=f"antenna_{s}", chain_index=k, side=s)
                prev = name
    per_side = num_legs // 2
    leg = 0
    for s, sx in (("l", 1.0), ("r", -1.0)):
        for i in range(per_side):
            t = 0.5 if per_side == 1 else i / (per_side - 1)
            z = (0.18 - 0.36 * t) * L  # front to back along the thorax
            spread = (0.35 - 0.7 * t)  # legs fan forward/back
            reach = 0.5 * leg_span
            coxa = (sx * 0.08 * L, body_height, z)
            femur_end = (sx * (0.08 * L + 0.35 * reach), body_height + 0.35 * reach, z + spread * 0.25 * reach)
            tibia_end = (sx * (0.08 * L + 0.75 * reach), body_height * 0.5, z + spread * 0.55 * reach)
            tip = (sx * (0.08 * L + 0.95 * reach), 0.0, z + spread * 0.7 * reach)
            chain = f"leg_{s.upper()}{i + 1}"
            names = [f"{chain}_coxa", f"{chain}_femur", f"{chain}_tibia", f"{chain}_tip"]
            parent = "thorax"
            for k, (n, p) in enumerate(zip(names, (coxa, femur_end, tibia_end, tip))):
                _add(j, n, parent, p, chain=chain, chain_index=k, side=s, leg=leg if k == 0 else -1)
                parent = n
            leg += 1
    _defaults(j)
    return j


# ---------------------------------------------------------------------------
# Snake / worm / fish spine
# ---------------------------------------------------------------------------

def snake(num_joints: int = 40, length: float = 4.0, radius: float = 0.06) -> List[Joint]:
    """Head at +Z, tail toward -Z, lying on the ground (Y = radius)."""
    if num_joints < 2:
        raise ValueError("snake needs at least 2 joints")
    j: List[Joint] = []
    _add(j, "root", None, (0, 0, 0), chain="root")
    seg = length / (num_joints - 1)
    prev = "root"
    for i in range(num_joints):
        name = f"spine_{i:03d}"
        _add(j, name, prev, (0, radius, -i * seg), chain="spine", chain_index=i,
             arclen=i * seg)
        prev = name
    _add(j, "jaw", "spine_000", (0, radius * 0.6, 0.08 * length / 4.0), chain="jaw", chain_index=0)
    _defaults(j)
    return j


# ---------------------------------------------------------------------------
# Bird
# ---------------------------------------------------------------------------

def bird(wingspan: float = 1.2, body_length: float = 0.4, tail_feathers: int = 3) -> List[Joint]:
    j: List[Joint] = []
    W, L = wingspan, body_length
    _add(j, "root", None, (0, 0, 0), chain="root")
    _add(j, "body", "root", (0, 0.3, 0), chain="body", chain_index=0)
    _add(j, "chest", "body", (0, 0.32, 0.25 * L), chain="body", chain_index=1)
    _add(j, "neck", "chest", (0, 0.40, 0.40 * L), chain="neck", chain_index=0)
    _add(j, "head", "neck", (0, 0.46, 0.55 * L), chain="neck", chain_index=1)
    _add(j, "tail", "body", (0, 0.30, -0.45 * L), chain="tail", chain_index=0)
    for k in range(tail_feathers):
        ang = (k - (tail_feathers - 1) / 2.0) * 0.35
        _add(j, f"tail_feather_{k:02d}", "tail", (math.sin(ang) * 0.3 * L, 0.30, -0.45 * L - math.cos(ang) * 0.3 * L),
             chain="tail_feathers", chain_index=k)
    for s, sx in (("l", 1.0), ("r", -1.0)):
        seg = [0.06, 0.20, 0.36, 0.5]  # fractions of wingspan
        names = ["shoulder", "humerus", "forearm", "hand", "tip"]
        prev = "chest"
        xs = [0.04] + seg
        for k, n in enumerate(names):
            name = f"wing_{s}_{n}"
            _add(j, name, prev, (sx * xs[k] * W, 0.34, 0.2 * L - 0.05 * k * L),
                 chain=f"wing_{s}", chain_index=k, side=s)
            prev = name
        # legs (simple 3-joint, folded)
        prev = "body"
        for k, (y, z) in enumerate(((0.24, 0.0), (0.12, 0.02), (0.02, 0.04))):
            name = f"leg_{s}_{k:02d}"
            _add(j, name, prev, (sx * 0.05, y, z), chain=f"leg_{s}", chain_index=k, side=s,
                 leg=(0 if s == "l" else 1) if k == 0 else -1)
            prev = name
    _defaults(j)
    return j


# ---------------------------------------------------------------------------
# Jellyfish / octopus
# ---------------------------------------------------------------------------

def jellyfish(bell_radius: float = 0.5, bell_spokes: int = 8, spoke_joints: int = 3,
              tentacles: int = 8, tentacle_joints: int = 12, tentacle_length: float = 1.6) -> List[Joint]:
    """Bell = radial spokes from the apex; tentacles hang from the bell rim."""
    j: List[Joint] = []
    R = bell_radius
    _add(j, "root", None, (0, 0, 0), chain="root")
    _add(j, "bell", "root", (0, R, 0), chain="bell", chain_index=0)
    for s in range(bell_spokes):
        a = 2.0 * math.pi * s / bell_spokes
        prev = "bell"
        for k in range(1, spoke_joints + 1):
            t = k / float(spoke_joints)  # 0 = apex, 1 = rim
            theta = t * math.pi * 0.5
            r = R * math.sin(theta)
            y = R * math.cos(theta)
            name = f"spoke_{s:02d}_{k:02d}"
            _add(j, name, prev, (r * math.cos(a), y, r * math.sin(a)), chain=f"spoke_{s:02d}",
                 chain_index=k - 1, angle=a)
            prev = name
    seg = tentacle_length / tentacle_joints
    for t_i in range(tentacles):
        a = 2.0 * math.pi * (t_i + 0.5) / tentacles
        rim = (0.9 * R * math.cos(a), 0.0, 0.9 * R * math.sin(a))
        prev = "bell"
        for k in range(tentacle_joints):
            name = f"tentacle_{t_i:02d}_{k:02d}"
            _add(j, name, prev, (rim[0], -k * seg, rim[2]), chain=f"tentacle_{t_i:02d}",
                 chain_index=k, angle=a, arclen=k * seg)
            prev = name
    _defaults(j)
    return j


# ---------------------------------------------------------------------------
# Vehicle
# ---------------------------------------------------------------------------

def vehicle(wheels: Sequence[Dict[str, object]], body_center: Vec3 = (0.0, 0.8, 0.0),
            extra_parts: Sequence[Tuple[str, Vec3]] = ()) -> List[Joint]:
    """Vehicle hierarchy: root > body > susp_<w> > steer_<w> > wheel_<w>.

    ``wheels`` items: name, center (vec3), radius, side ('l'/'r'/'c'),
    steers (bool), drives (bool). ``extra_parts`` are (name, pivot) rigid parts
    parented to the body (doors, antenna, turret...).
    """
    j: List[Joint] = []
    _add(j, "root", None, (0, 0, 0), chain="root")
    _add(j, "body", "root", body_center, chain="body", role="body")
    for i, w in enumerate(wheels):
        wn = str(w["name"])
        c = w["center"]  # type: ignore[index]
        common = dict(side=w.get("side", "c"), wheel=i, radius=float(w["radius"]),  # type: ignore[arg-type]
                      steers=int(bool(w.get("steers", False))), drives=int(bool(w.get("drives", True))),
                      part=wn)
        _add(j, f"susp_{wn}", "body", c, chain=f"wheel_{wn}", chain_index=0, role="suspension", **common)
        _add(j, f"steer_{wn}", f"susp_{wn}", c, chain=f"wheel_{wn}", chain_index=1, role="steer", **common)
        _add(j, f"wheel_{wn}", f"steer_{wn}", c, chain=f"wheel_{wn}", chain_index=2, role="wheel", **common)
    for name, pivot in extra_parts:
        _add(j, f"part_{name}", "body", pivot, chain=f"part_{name}", role="part", part=name)
    for jt in j:
        jt.attrs.setdefault("wheel", -1)
        jt.attrs.setdefault("role", "root" if jt.parent is None else "part")
    _defaults(j)
    return j


def _defaults(joints: List[Joint]) -> None:
    for jt in joints:
        jt.attrs.setdefault("side", "c")
        jt.attrs.setdefault("leg", -1)
        jt.attrs.setdefault("chain", jt.name)
        jt.attrs.setdefault("chain_index", 0)
    validate(joints)


TEMPLATES = {
    "biped": biped,
    "quadruped": quadruped,
    "insect": insect,
    "spider": lambda **kw: insect(num_legs=8, antennae=False, **kw),
    "snake": snake,
    "bird": bird,
    "jellyfish": jellyfish,
}


def to_dicts(joints: Sequence[Joint]) -> List[Dict[str, object]]:
    """JSON-friendly representation (embedded into Python SOPs)."""
    return [{"name": j.name, "parent": j.parent, "pos": list(j.pos), "attrs": dict(j.attrs)} for j in joints]
