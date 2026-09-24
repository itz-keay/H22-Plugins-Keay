import math
import unittest

from tests import _path  # noqa: F401
from apex_studio.core import crowd_layout, guides, profiles


class TestGuides(unittest.TestCase):
    def test_all_templates_valid(self):
        for name, fn in guides.TEMPLATES.items():
            joints = fn()
            guides.validate(joints)
            self.assertEqual(sum(1 for j in joints if j.parent is None), 1, name)

    def test_biped_uses_canonical_names(self):
        names = {j.name for j in guides.biped(fingers=True)}
        self.assertTrue(set(profiles.CORE_JOINTS) <= names)
        self.assertTrue(names <= set(profiles.CANONICAL_JOINTS))

    def test_insect_leg_chains(self):
        joints = guides.insect(num_legs=6)
        legs = [j for j in joints if j.attrs["leg"] >= 0]
        self.assertEqual(sorted(j.attrs["leg"] for j in legs), list(range(6)))
        for leg in legs:
            chain = [j for j in joints if j.attrs["chain"] == leg.attrs["chain"]]
            self.assertEqual(sorted(j.attrs["chain_index"] for j in chain), [0, 1, 2, 3])
        with self.assertRaises(ValueError):
            guides.insect(num_legs=5)

    def test_leg_order_left_then_right(self):
        joints = guides.insect(num_legs=6)
        legs = sorted((j for j in joints if j.attrs["leg"] >= 0), key=lambda j: j.attrs["leg"])
        self.assertEqual([j.attrs["side"] for j in legs], ["l"] * 3 + ["r"] * 3)
        self.assertGreater(legs[0].pos[2], legs[2].pos[2])  # front to back

    def test_snake_arclen(self):
        joints = [j for j in guides.snake(num_joints=11, length=5.0) if j.attrs["chain"] == "spine"]
        self.assertAlmostEqual(joints[-1].attrs["arclen"], 5.0)

    def test_vehicle_hierarchy(self):
        wheels = [dict(name="fl", center=(0.8, 0.3, 1.3), radius=0.3, side="l", steers=True)]
        joints = {j.name: j for j in guides.vehicle(wheels)}
        self.assertEqual(joints["wheel_fl"].parent, "steer_fl")
        self.assertEqual(joints["steer_fl"].parent, "susp_fl")
        self.assertEqual(joints["susp_fl"].parent, "body")
        self.assertEqual(joints["wheel_fl"].attrs["steers"], 1)

    def test_duplicate_detection(self):
        with self.assertRaises(ValueError):
            guides.validate([guides.Joint("a", None, (0, 0, 0)), guides.Joint("a", None, (0, 0, 0))])


class TestCrowd(unittest.TestCase):
    def test_seats_face_centre(self):
        for pos, yaw in crowd_layout.stadium_seats(rows=2, seats_per_row=5, seat_jitter=0.0):
            fwd = (math.sin(yaw), math.cos(yaw))
            to_c = (-pos[0], -pos[2])
            n = math.hypot(*to_c)
            self.assertAlmostEqual(fwd[0] * to_c[0] / n + fwd[1] * to_c[1] / n, 1.0, places=6)

    def test_rows_rise(self):
        seats = crowd_layout.stadium_seats(rows=3, seats_per_row=4, row_height=0.5)
        self.assertEqual(sorted({round(p[1], 6) for p, _ in seats}), [0.0, 0.5, 1.0])

    def test_state_machine_detail_roundtrip(self):
        sm = crowd_layout.default_walk_run_ragdoll()
        d = sm.to_detail()
        self.assertEqual(d["sm_state_names"], ["walk", "run", "ragdoll"])
        self.assertEqual(d["sm_tr_kind"], ["volume", "volume", "volume"])
        self.assertEqual(d["sm_tr_arg"], ["panic", "hazard", "hazard"])
        self.assertEqual(d["sm_state_ragdoll"], [0, 0, 1])

    def test_state_machine_step(self):
        sm = crowd_layout.default_walk_run_ragdoll()
        st, t, blend = crowd_layout.step_reference(sm, 0, 1.0, 1 / 24, [], 0.5, 1.0, 10)
        self.assertEqual((st, blend), (0, 0.0))
        self.assertAlmostEqual(t, 1.0 + 1 / 24)
        st, t, blend = crowd_layout.step_reference(sm, 0, 1.0, 1 / 24, ["panic"], 0.5, 1.0, 10)
        self.assertEqual(sm.states[st].name, "run")
        st, _, _ = crowd_layout.step_reference(sm, st, 0.0, 1 / 24, ["hazard"], 0.5, 1.0, 10)
        self.assertTrue(sm.states[st].ragdoll)

    def test_clip_end_transition(self):
        sm = crowd_layout.default_stadium()
        st, _, _ = crowd_layout.step_reference(sm, 1, 2.5, 1 / 24, [], 0.99, 2.0, 10)
        self.assertEqual(sm.states[st].name, "idle")


if __name__ == "__main__":
    unittest.main()
