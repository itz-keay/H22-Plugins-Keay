import math
import unittest

from tests import _path  # noqa: F401
from apex_studio.core import gait


class TestGait(unittest.TestCase):
    def test_tripod_groups(self):
        duty, off = gait.gait_offsets(6, "tripod")
        self.assertEqual(duty, 0.5)
        # L1, R2, L3 together; R1, L2, R3 together
        self.assertEqual(off[0], off[4])
        self.assertEqual(off[0], off[2])
        self.assertEqual(off[3], off[1])
        self.assertNotEqual(off[0], off[3])

    def test_auto_and_metachronal(self):
        self.assertEqual(gait.gait_offsets(8)[1], gait.GAITS["alternating_tetrapod"][1][8])
        duty, off = gait.gait_offsets(20)
        self.assertEqual(len(off), 20)
        self.assertTrue(all(0.0 <= o < 1.0 for o in off))

    def test_stance_foot_does_not_slide(self):
        stride, duty = 0.5, 0.6
        d = 0.0
        prev = None
        while d < 3.0:
            st = gait.foot_state(d, stride, 0.25, duty)
            if st.in_stance and prev is not None and prev.in_stance:
                self.assertAlmostEqual(st.plant_distance, prev.plant_distance, places=9)
            prev = st
            d += 0.001

    def test_foot_path_is_continuous(self):
        stride, duty = 0.4, 0.5
        prev_pos, _ = gait.foot_distance(0.0, stride, 0.1, duty)
        d = 0.0
        while d < 4.0:
            d += 0.0005
            pos, lift = gait.foot_distance(d, stride, 0.1, duty)
            self.assertLess(abs(pos - prev_pos), 0.02, f"jump at d={d}")
            self.assertGreaterEqual(lift, 0.0)
            prev_pos = pos

    def test_foot_advances_one_stride_per_cycle(self):
        a = gait.foot_state(0.1, 0.5, 0.0, 0.5).plant_distance
        b = gait.foot_state(0.6, 0.5, 0.0, 0.5).plant_distance
        self.assertAlmostEqual(b - a, 0.5)

    def test_lift_peaks_mid_swing(self):
        st = gait.foot_state(0.75 * 1.0, 1.0, 0.0, 0.5)  # phase 0.75 = middle of swing
        self.assertFalse(st.in_stance)
        self.assertAlmostEqual(st.lift, 1.0)


if __name__ == "__main__":
    unittest.main()
