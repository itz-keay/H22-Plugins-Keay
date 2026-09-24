"""Vehicle kinematics: the reference math behind ``vex/snippets/vehicle_*.vfl``.

Conventions (match the VEX): Y is up, +Z is the vehicle's forward axis, +X is
its left side. Curvature ``kappa`` is signed: positive = turning left.
Units are Houdini units (metres) and seconds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]
TWO_PI = 2.0 * math.pi


# ---------------------------------------------------------------------------
# Wheels
# ---------------------------------------------------------------------------

def wheel_rotation(delta_distance: float, radius: float, unit: str = "radians") -> float:
    """Rotation of a wheel that rolled ``delta_distance`` without slipping.

    ``revolutions = d / (2 * pi * r)`` (the brief's formula);
    ``radians = d / r``; ``degrees = 360 * d / (2 * pi * r)``.
    """
    if radius <= 0.0:
        raise ValueError("wheel radius must be > 0")
    revolutions = delta_distance / (TWO_PI * radius)
    if unit == "revolutions":
        return revolutions
    if unit == "degrees":
        return revolutions * 360.0
    if unit == "radians":
        return revolutions * TWO_PI
    raise ValueError(f"unknown unit {unit!r}")


def offset_arc_lengths(points: Sequence[Vec3], lateral_offset: float) -> List[float]:
    """Cumulative distance travelled by a point ``lateral_offset`` left of a path.

    For a path with signed curvature k, a point offset by w to the left moves
    ``ds' = (1 - k*w) ds``, and ``k ds`` is the heading change, so
    ``ds' = ds - w * dtheta``. Inner wheels therefore travel less than outer
    wheels in a turn, which is what makes their spin rates differ. Only XZ is
    used for heading; segment length is the full 3D length.
    """
    n = len(points)
    if n == 0:
        return []
    out = [0.0]
    prev_heading: Optional[float] = None
    for i in range(1, n):
        a, b = points[i - 1], points[i]
        seg = math.dist(a, b)
        heading = math.atan2(b[0] - a[0], b[2] - a[2])  # yaw around +Y, 0 = +Z
        dtheta = 0.0
        if prev_heading is not None:
            dtheta = _wrap_pi(heading - prev_heading)
        prev_heading = heading
        # yaw is measured from +Z toward +X (left), so a left turn is +dtheta
        out.append(out[-1] + seg - lateral_offset * dtheta)
    return out


def _wrap_pi(a: float) -> float:
    return (a + math.pi) % TWO_PI - math.pi


# ---------------------------------------------------------------------------
# Steering / lean / drift
# ---------------------------------------------------------------------------

def ackermann(wheelbase: float, track: float, kappa: float) -> Tuple[float, float]:
    """(left, right) front-wheel steer angles in radians for curvature ``kappa``.

    ``delta = atan(L / (R -+ T/2))`` rewritten as ``atan(L*k / (1 -+ k*T/2))`` so
    it is well-defined when driving straight (k = 0). The inner wheel steers more.
    """
    left = math.atan2(wheelbase * kappa, 1.0 - kappa * track * 0.5)
    right = math.atan2(wheelbase * kappa, 1.0 + kappa * track * 0.5)
    # atan2 with a negative denominator flips to the far quadrant on extreme
    # curvature (turning radius smaller than half-track); clamp to +-90 deg.
    return _clamp_half_pi(left), _clamp_half_pi(right)


def _clamp_half_pi(a: float) -> float:
    lim = math.pi * 0.5
    if a > lim:
        return a - math.pi
    if a < -lim:
        return a + math.pi
    return a


def lateral_acceleration(speed: float, kappa: float) -> float:
    """Centripetal acceleration ``v^2 * k`` (signed like ``kappa``)."""
    return speed * speed * kappa


def bike_lean(speed: float, kappa: float, gravity: float = 9.81,
              max_lean: float = math.radians(55.0)) -> float:
    """Balanced lean angle ``atan(v^2 k / g)``, clamped. Positive leans left
    (into a left turn), i.e. a roll of ``-lean`` in the ``fit_ground_plane`` convention."""
    lean = math.atan(speed * speed * kappa / gravity)
    return max(-max_lean, min(max_lean, lean))


def drift_slip_angle(lat_accel: float, grip: float, gain: float, max_angle: float,
                     amount: float = 1.0) -> float:
    """Body slip angle (radians) once lateral acceleration exceeds tyre grip.

    Zero below ``grip`` (m/s^2), then grows by ``gain`` rad per m/s^2 up to
    ``max_angle``. The sign follows the turn: the tail swings outward, so the
    body yaws further *into* the turn than the path tangent.
    """
    excess = abs(lat_accel) - grip
    if excess <= 0.0:
        return 0.0
    return math.copysign(min(max_angle, excess * gain) * amount, lat_accel)


def body_roll(lat_accel: float, roll_stiffness: float, max_roll: float) -> float:
    """Static body roll from lateral acceleration, in the ``fit_ground_plane`` roll
    convention (positive = left side higher). A car leans *out* of the turn, so
    a left turn (positive ``lat_accel``) lifts the left side: positive roll.
    """
    roll = lat_accel / max(roll_stiffness, 1e-6)
    return max(-max_roll, min(max_roll, roll))


def body_pitch(long_accel: float, pitch_stiffness: float, max_pitch: float) -> float:
    """Squat (accelerating, nose up) / dive (braking, nose down). Positive = nose up."""
    pitch = long_accel / max(pitch_stiffness, 1e-6)
    return max(-max_pitch, min(max_pitch, pitch))


# ---------------------------------------------------------------------------
# Ground plane fit (chassis pitch/roll from wheel contacts)
# ---------------------------------------------------------------------------

def fit_ground_plane(contacts: Sequence[Tuple[float, float, float]]) -> Tuple[float, float, float]:
    """Least-squares plane ``h = a + b*x + c*z`` through (x, z, h) wheel contacts.

    Returns (height, pitch, roll) in radians. ``pitch`` is the nose-up angle
    (front higher); because a positive right-handed rotation about +X tips +Z
    *down*, apply it as a rotation of ``-pitch`` about +X. ``roll`` is a
    rotation about +Z (positive = left side higher). With colinear contacts
    (bikes) roll is 0; with 1 contact both are 0.
    """
    n = len(contacts)
    if n == 0:
        return 0.0, 0.0, 0.0
    if n == 1:
        return contacts[0][2], 0.0, 0.0
    sx = sum(c[0] for c in contacts)
    sz = sum(c[1] for c in contacts)
    sh = sum(c[2] for c in contacts)
    mx, mz, mh = sx / n, sz / n, sh / n
    cxx = sum((c[0] - mx) ** 2 for c in contacts)
    czz = sum((c[1] - mz) ** 2 for c in contacts)
    cxz = sum((c[0] - mx) * (c[1] - mz) for c in contacts)
    cxh = sum((c[0] - mx) * (c[2] - mh) for c in contacts)
    czh = sum((c[1] - mz) * (c[2] - mh) for c in contacts)
    det = cxx * czz - cxz * cxz
    if abs(det) < 1e-12:
        # colinear contacts (bike / single axle): fit along the dominant axis
        b = cxh / cxx if cxx > 1e-12 else 0.0
        c = czh / czz if czz > 1e-12 else 0.0
        if czz >= cxx:
            b = 0.0
        else:
            c = 0.0
    else:
        b = (cxh * czz - czh * cxz) / det
        c = (czh * cxx - cxh * cxz) / det
    height = mh - b * mx - c * mz
    return height, math.atan(c), math.atan(b)


# ---------------------------------------------------------------------------
# Springs
# ---------------------------------------------------------------------------

def critical_damping(stiffness: float, mass: float = 1.0) -> float:
    return 2.0 * math.sqrt(stiffness * mass)


@dataclass
class SpringDamper:
    """1D spring-damper integrated with semi-implicit Euler (matches the VEX)."""

    stiffness: float = 180.0
    damping_ratio: float = 0.35
    x: float = 0.0
    v: float = 0.0

    def step(self, target: float, dt: float, substeps: int = 4) -> float:
        c = self.damping_ratio * critical_damping(self.stiffness)
        h = dt / max(1, substeps)
        for _ in range(max(1, substeps)):
            a = self.stiffness * (target - self.x) - c * self.v
            self.v += a * h
            self.x += self.v * h
        return self.x


# ---------------------------------------------------------------------------
# Parts classification (used when auto-rigging an imported vehicle)
# ---------------------------------------------------------------------------

WHEEL_TOKENS = ("wheel", "tire", "tyre", "rim", "whl")
STEER_TOKENS = ("front", "fl", "fr", "steer", "fork")
TRACK_TOKENS = ("track", "tread")
BODY_TOKENS = ("body", "chassis", "hull", "frame", "shell")


@dataclass
class WheelInfo:
    name: str
    center: Vec3
    radius: float
    axle_axis: int  # 0 = X, 1 = Y, 2 = Z (smallest bbox extent)
    side: str  # "l", "r" or "c"
    is_front: bool
    steers: bool
    drives: bool = True


def classify_parts(bboxes: Dict[str, Tuple[Vec3, Vec3]], forward_axis: int = 2,
                   center_tolerance: float = 0.05) -> Tuple[List[WheelInfo], List[str], List[str]]:
    """Split named parts into (wheels, body_parts, other_parts).

    A part is a wheel when its name contains a wheel token. Radius is half the
    larger of the two non-axle extents; the axle is the smallest extent.
    Front wheels (ahead of the wheel centroid along ``forward_axis``) steer
    unless the vehicle has only one axle.
    """
    wheels: List[WheelInfo] = []
    body: List[str] = []
    other: List[str] = []
    for name, (bmin, bmax) in bboxes.items():
        low = name.lower()
        if any(t in low for t in WHEEL_TOKENS):
            size = [bmax[i] - bmin[i] for i in range(3)]
            axle = min(range(3), key=lambda i: size[i])
            radius = 0.5 * max(size[i] for i in range(3) if i != axle)
            center = tuple(0.5 * (bmin[i] + bmax[i]) for i in range(3))
            wheels.append(WheelInfo(name, center, radius, axle, "c", False, False))  # type: ignore[arg-type]
        elif any(t in low for t in BODY_TOKENS):
            body.append(name)
        else:
            other.append(name)
    if wheels:
        side_axis = 0 if forward_axis == 2 else 2
        mean_f = sum(w.center[forward_axis] for w in wheels) / len(wheels)
        mean_s = sum(w.center[side_axis] for w in wheels) / len(wheels)
        span_f = max(w.center[forward_axis] for w in wheels) - min(w.center[forward_axis] for w in wheels)
        for w in wheels:
            ds = w.center[side_axis] - mean_s
            w.side = "c" if abs(ds) < center_tolerance else ("l" if ds > 0 else "r")
            w.is_front = w.center[forward_axis] > mean_f + center_tolerance * max(span_f, 1.0)
            named_front = any(t in w.name.lower() for t in STEER_TOKENS)
            w.steers = (w.is_front or named_front) and span_f > center_tolerance
    return wheels, body, other


def wheelbase_and_track(wheels: Sequence[WheelInfo]) -> Tuple[float, float]:
    """(wheelbase along Z, track width along X) from wheel centres."""
    if not wheels:
        return 0.0, 0.0
    zs = [w.center[2] for w in wheels]
    xs = [w.center[0] for w in wheels]
    return max(zs) - min(zs), max(xs) - min(xs)


# ---------------------------------------------------------------------------
# Tank track loops
# ---------------------------------------------------------------------------

def convex_hull(points: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Andrew's monotone chain; returns the hull counter-clockwise, no repeats."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return list(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: List[Tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: List[Tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def track_loop(wheels_zyr: Sequence[Tuple[float, float, float]], thickness: float = 0.03,
               samples_per_wheel: int = 24) -> List[Tuple[float, float]]:
    """Closed tread path (z, y) wrapping road wheels / sprockets of one side.

    Each wheel is sampled as a circle of radius ``r + thickness`` and the
    convex hull of all samples is the track loop (taut belt model).
    """
    samples: List[Tuple[float, float]] = []
    for z, y, r in wheels_zyr:
        rr = r + thickness
        for i in range(samples_per_wheel):
            a = TWO_PI * i / samples_per_wheel
            samples.append((round(z + rr * math.cos(a), 9), round(y + rr * math.sin(a), 9)))
    return convex_hull(samples)
