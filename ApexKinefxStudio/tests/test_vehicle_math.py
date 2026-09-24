import math
import unittest

from tests import _path  # noqa: F401
from apex_studio.core import vehicle_math as vm


class TestVehicleMath(unittest.TestCase):
    def test_wheel_rotation_units(self):
        r = 0.35
        d = 2 * math.pi * r * 3  # three full revolutions
        self.assertAlmostEqual(vm.wheel_rotation(d, r, "revolutions"), 3.0)
        self.assertAlmostEqual(vm.wheel_rotation(d, r, "degrees"), 1080.0)
        self.assertAlmostEqual(vm.wheel_rotation(d, r, "radians"), d / r)
        self.assertAlmostEqual(vm.wheel_rotation(-d, r, "revolutions"), -3.0)
        with self.assertRaises(ValueError):
            vm.wheel_rotation(1.0, 0.0)

    def _circle(self, radius, n=720, turns=1.0):
        # counter-clockwise seen from +Y, heading starts along +Z: a left turn
        pts = []
        for i in range(n + 1):
            a = turns * 2 * math.pi * i / n
            pts.append((radius - radius * math.cos(a), 0.0, radius * math.sin(a)))
        return pts

    def test_offset_arc_length_on_circle(self):
        R, w = 10.0, 0.8
        pts = self._circle(R)
        centre = vm.offset_arc_lengths(pts, 0.0)[-1]
        inner = vm.offset_arc_lengths(pts, +w)[-1]   # left of path = inside of a left turn
        outer = vm.offset_arc_lengths(pts, -w)[-1]
        self.assertAlmostEqual(centre, 2 * math.pi * R, delta=0.01)
        self.assertAlmostEqual(inner, 2 * math.pi * (R - w), delta=0.05)
        self.assertAlmostEqual(outer, 2 * math.pi * (R + w), delta=0.05)

    def test_offset_arc_length_straight(self):
        pts = [(0.0, 0.0, float(z)) for z in range(11)]
        self.assertAlmostEqual(vm.offset_arc_lengths(pts, 0.7)[-1], 10.0)

    def test_ackermann(self):
        L, T = 2.7, 1.6
        left, right = vm.ackermann(L, T, 1 / 10.0)  # left turn, R = 10
        self.assertGreater(left, right)             # inner (left) wheel steers more
        self.assertAlmostEqual(left, math.atan(L / (10 - T / 2)))
        self.assertAlmostEqual(right, math.atan(L / (10 + T / 2)))
        l2, r2 = vm.ackermann(L, T, -1 / 10.0)      # right turn mirrors it
        self.assertAlmostEqual(l2, -right)
        self.assertAlmostEqual(r2, -left)
        self.assertEqual(vm.ackermann(L, T, 0.0), (0.0, 0.0))

    def test_bike_lean(self):
        self.assertAlmostEqual(vm.bike_lean(10.0, 1 / 20.0), math.atan(100 / 20 / 9.81))
        self.assertLessEqual(vm.bike_lean(100.0, 1.0), math.radians(55) + 1e-9)

    def test_drift(self):
        self.assertEqual(vm.drift_slip_angle(5.0, 7.0, 0.1, 0.6), 0.0)
        self.assertAlmostEqual(vm.drift_slip_angle(9.0, 7.0, 0.1, 0.6), 0.2)
        self.assertAlmostEqual(vm.drift_slip_angle(-9.0, 7.0, 0.1, 0.6), -0.2)
        self.assertAlmostEqual(vm.drift_slip_angle(100.0, 7.0, 0.1, 0.6), 0.6)

    def test_fit_plane(self):
        # h = 0.5 + 0.1 x + 0.2 z  (left side and front higher)
        contacts = [(x, z, 0.5 + 0.1 * x + 0.2 * z) for x, z in ((0.8, 1.3), (-0.8, 1.3), (0.8, -1.3), (-0.8, -1.3))]
        h, pitch, roll = vm.fit_ground_plane(contacts)
        self.assertAlmostEqual(h, 0.5)
        self.assertAlmostEqual(pitch, math.atan(0.2))
        self.assertAlmostEqual(roll, math.atan(0.1))

    def test_fit_plane_bike(self):
        h, pitch, roll = vm.fit_ground_plane([(0.0, 0.7, 1.0), (0.0, -0.7, 0.0)])
        self.assertAlmostEqual(pitch, math.atan(1.0 / 1.4))
        self.assertEqual(roll, 0.0)
        self.assertAlmostEqual(h, 0.5)

    def test_body_roll_leans_out_of_turn(self):
        self.assertGreater(vm.body_roll(5.0, 90.0, 0.2), 0.0)  # left turn lifts the left side

    def test_spring_converges_with_overshoot(self):
        s = vm.SpringDamper(stiffness=100.0, damping_ratio=0.3)
        peak = 0.0
        for _ in range(240):
            peak = max(peak, s.step(1.0, 1 / 24.0))
        self.assertGreater(peak, 1.0)            # underdamped: overshoots
        self.assertAlmostEqual(s.x, 1.0, places=3)

    def test_classify_parts(self):
        boxes = {
            "body": ((-0.9, 0.3, -2.2), (0.9, 1.4, 2.2)),
            "wheel_fl": ((0.7, 0.0, 1.0), (0.95, 0.68, 1.68)),
            "wheel_fr": ((-0.95, 0.0, 1.0), (-0.7, 0.68, 1.68)),
            "wheel_rl": ((0.7, 0.0, -1.68), (0.95, 0.68, -1.0)),
            "wheel_rr": ((-0.95, 0.0, -1.68), (-0.7, 0.68, -1.0)),
            "antenna": ((0.5, 1.4, -1.8), (0.52, 2.2, -1.78)),
        }
        wheels, body, other = vm.classify_parts(boxes)
        self.assertEqual(body, ["body"])
        self.assertEqual(other, ["antenna"])
        by = {w.name: w for w in wheels}
        self.assertAlmostEqual(by["wheel_fl"].radius, 0.34)
        self.assertEqual(by["wheel_fl"].axle_axis, 0)
        self.assertEqual(by["wheel_fl"].side, "l")
        self.assertEqual(by["wheel_rr"].side, "r")
        self.assertTrue(by["wheel_fl"].steers and by["wheel_fr"].steers)
        self.assertFalse(by["wheel_rl"].steers or by["wheel_rr"].steers)
        wb, tr = vm.wheelbase_and_track(wheels)
        self.assertAlmostEqual(wb, 2.68)
        self.assertAlmostEqual(tr, 1.65)

    def test_track_loop_wraps_wheels(self):
        wheels = [(-1.0, 0.3, 0.3), (0.0, 0.3, 0.3), (1.0, 0.3, 0.3), (1.4, 0.6, 0.25)]
        loop = vm.track_loop(wheels, thickness=0.02)
        for z, y, r in wheels:
            # every wheel centre is inside the loop: loop points keep >= r distance
            self.assertGreaterEqual(min(math.hypot(pz - z, py - y) for pz, py in loop), r - 1e-6)
        ys = [p[1] for p in loop]
        self.assertAlmostEqual(min(ys), 0.3 - 0.32, places=3)  # bottom run touches the ground plane


if __name__ == "__main__":
    unittest.main()
