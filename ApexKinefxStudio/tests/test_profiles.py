import unittest

from tests import _path  # noqa: F401
from apex_studio.core import profiles

MIXAMO = ["mixamorig:" + n for n in profiles.PROFILES["mixamo"].values()]
UE5 = list(profiles.PROFILES["ue5"].values())
CASCADEUR = list(profiles.PROFILES["cascadeur"].values())


class TestProfiles(unittest.TestCase):
    def test_detect_mixamo_with_namespace(self):
        name, score = profiles.detect_profile(MIXAMO)
        self.assertEqual(name, "mixamo")
        self.assertEqual(score, 1.0)

    def test_detect_ue5(self):
        name, score = profiles.detect_profile(UE5)
        self.assertIn(name, ("ue5", "cascadeur"))  # identical core naming
        self.assertEqual(score, 1.0)

    def test_side_detection(self):
        cases = {"mixamorig:LeftArm": "l", "RightUpLeg": "r", "thigh_l": "l", "calf_r": "r",
                 "DEF-forearm.L": "l", "L_hand": "l", "Hips": None, "spine_01": None, "pelvis": None}
        for name, side in cases.items():
            self.assertEqual(profiles.detect_side(name), side, name)

    def test_classify_generic_names(self):
        cases = {"LeftUpLeg": "l_thigh", "LeftLeg": "l_shin", "LeftFoot": "l_foot",
                 "RightForeArm": "r_forearm", "RightArm": "r_upperarm", "LeftShoulder": "l_clavicle",
                 "Hips": "hips", "pelvis": "hips", "Neck": "neck", "Head": "head",
                 "calf_l": "l_shin", "ball_r": "r_toe", "LeftHandIndex2": "l_index_02"}
        for name, canon in cases.items():
            self.assertEqual(profiles.classify(name), canon, name)

    def test_mixamo_to_ue5_core_map(self):
        mapping = profiles.auto_map(MIXAMO, UE5)
        self.assertEqual(mapping["pelvis"], "mixamorig:Hips")
        self.assertEqual(mapping["thigh_l"], "mixamorig:LeftUpLeg")
        self.assertEqual(mapping["calf_r"], "mixamorig:RightLeg")
        self.assertEqual(mapping["hand_l"], "mixamorig:LeftHand")
        self.assertEqual(profiles.missing_core(mapping, UE5), [])

    def test_mixamo_to_cascadeur(self):
        mapping = profiles.auto_map(MIXAMO, CASCADEUR, target_profile="cascadeur")
        self.assertEqual(mapping["spine_03"], "mixamorig:Spine2")
        self.assertEqual(mapping["upperarm_r"], "mixamorig:RightArm")

    def test_mapping_is_one_to_one(self):
        mapping = profiles.auto_map(MIXAMO, UE5)
        self.assertEqual(len(set(mapping.values())), len(mapping))

    def test_unknown_rig_uses_fuzzy_classification(self):
        src = ["Root", "Pelvis", "L_Thigh", "L_Knee", "L_Ankle", "R_Thigh", "R_Knee", "R_Ankle"]
        tgt = ["hips", "l_thigh", "l_shin", "l_foot", "r_thigh", "r_shin", "r_foot"]
        mapping = profiles.auto_map(src, tgt)
        self.assertEqual(mapping["l_shin"], "L_Knee")
        self.assertEqual(mapping["r_foot"], "R_Ankle")
        self.assertEqual(mapping["hips"], "Pelvis")


if __name__ == "__main__":
    unittest.main()
