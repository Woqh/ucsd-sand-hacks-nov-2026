import unittest

import numpy as np

from posture.core import LANDMARK_NAMES, correct_world_camera_roll, measure_pose, normalize_world


def front_pose():
    points = np.full((33, 2), np.nan)
    scores = np.zeros(33)
    positions = {7: (460, 180), 8: (540, 180), 11: (400, 300), 12: (600, 300),
                 23: (430, 500), 24: (570, 500), 25: (430, 700), 26: (570, 700),
                 27: (430, 900), 28: (570, 900)}
    for index, point in positions.items():
        points[index], scores[index] = point, 0.95
    return points / 1000, scores


def side_pose():
    points, scores = front_pose()
    points *= 1000
    positions = {0: (540, 190), 7: (500, 200), 8: (505, 200),
                 11: (500, 300), 12: (505, 300), 23: (500, 500), 24: (505, 500),
                 25: (500, 700), 26: (505, 700), 27: (500, 900), 28: (505, 900),
                 29: (480, 900), 30: (485, 900), 31: (530, 900), 32: (535, 900)}
    for index, point in positions.items():
        points[index], scores[index] = point, 0.95
    return points / 1000, scores


class NormalizationTests(unittest.TestCase):
    def setUp(self):
        xy, _ = front_pose()
        self.world = np.column_stack((xy, np.zeros(33)))

    def test_translation_and_positive_scale_invariant_with_gravity_retained(self):
        first = normalize_world(self.world)
        second = normalize_world(self.world * 3 + [4, -2, 7])
        self.assertTrue(first["valid"])
        np.testing.assert_allclose(first["xyz"], second["xyz"], atol=1e-6)
        np.testing.assert_allclose(first["xyz"][[23, 24]].mean(axis=0), 0, atol=1e-6)
        self.assertLess(first["xyz"][11, 1], 0)
        self.assertEqual(float(first["confidence"].sum()), 0)
        self.assertEqual(float(first["confidence_known"].sum()), 0)
        self.assertEqual(first["mask"][11], 1)
        self.assertEqual(first["mask"][0], 0)
        np.testing.assert_array_equal(first["xyz"][0], 0)

    def test_rotation_signal_is_preserved(self):
        first = normalize_world(self.world)
        angle = np.radians(20)
        rotation = np.array([[np.cos(angle), -np.sin(angle), 0],
                             [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
        rotated = normalize_world(self.world @ rotation.T)
        np.testing.assert_allclose(rotated["xyz"], first["xyz"] @ rotation.T, atol=1e-6)
        self.assertNotAlmostEqual(float(first["xyz"][11, 0]), float(rotated["xyz"][11, 0]))

    def test_one_valid_torso_side_can_supply_scale_but_both_hips_required(self):
        scores = np.ones(33)
        scores[12] = 0.1
        result = normalize_world(self.world, scores)
        self.assertTrue(result["valid"])
        self.assertEqual(result["mask"][12], 0)
        scores[23] = 0.1
        result = normalize_world(self.world, scores)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "missing_or_low_confidence_hip_reference")

    def test_degenerate_torso_and_bad_shapes_are_explicit(self):
        self.world[11], self.world[12] = self.world[23], self.world[24]
        result = normalize_world(self.world)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "missing_or_degenerate_torso_scale")
        with self.assertRaises(ValueError):
            normalize_world(np.zeros((32, 3)))
        with self.assertRaises(ValueError):
            normalize_world(self.world, np.full(33, 2.0))

    def test_supplied_world_camera_roll_matches_image_convention_and_preserves_depth(self):
        xy, confidence = front_pose()
        xy[[7, 8, 11, 12], 0] += 0.08
        world = np.column_stack((xy - 0.5, np.linspace(-0.2, 0.2, 33)))
        theta = np.radians(11)
        rotation = np.array([[np.cos(theta), -np.sin(theta)],
                             [np.sin(theta), np.cos(theta)]])
        rolled_world = world.copy()
        rolled_world[:, :2] = world[:, :2] @ rotation.T
        corrected = correct_world_camera_roll(rolled_world, 11)
        np.testing.assert_allclose(corrected, world, atol=1e-12, equal_nan=True)
        np.testing.assert_array_equal(corrected[:, 2], rolled_world[:, 2])
        original_image = measure_pose(xy, confidence, 1000, 1000, "front")
        corrected_image = measure_pose(corrected[:, :2] + 0.5, confidence, 1000, 1000, "front")
        self.assertAlmostEqual(corrected_image["measurements"]["torso_inclination_deg"],
                               original_image["measurements"]["torso_inclination_deg"])
        self.assertGreater(corrected_image["measurements"]["torso_inclination_deg"], 20)
        np.testing.assert_allclose(normalize_world(corrected)["xyz"],
                                   normalize_world(world)["xyz"], atol=1e-6)

    def test_world_roll_zero_is_independent_copy_and_invalid_arguments_fail(self):
        corrected = correct_world_camera_roll(self.world)
        np.testing.assert_array_equal(corrected, self.world)
        self.assertFalse(np.shares_memory(corrected, self.world))
        with self.assertRaises(ValueError):
            correct_world_camera_roll(np.zeros((32, 3)), 1)
        with self.assertRaises(ValueError):
            correct_world_camera_roll(self.world, float("nan"))


class MeasurementTests(unittest.TestCase):
    def test_upright_front_and_viewpoint_restrictions(self):
        xy, confidence = front_pose()
        result = measure_pose(xy, confidence, 1000, 1000, viewpoint="front")
        for key in ("torso_inclination_deg", "neck_inclination_deg", "shoulder_alignment_deg",
                    "hip_alignment_deg", "lateral_trunk_inclination_deg"):
            self.assertAlmostEqual(result["measurements"][key], 0)
        for key in ("hip_flexion_deg", "knee_flexion_deg", "sagittal_torso_inclination_deg"):
            self.assertIsNone(result["measurements"][key])
            self.assertEqual(result["measurement_details"][key]["reason"], "requires_side_view")

    def test_anatomical_forward_changes_with_facing_not_image_sign(self):
        xy, confidence = side_pose()
        xy[[11, 12], 0] += 0.1
        right = measure_pose(xy, confidence, 1000, 1000, "side", "right")
        left = measure_pose(xy, confidence, 1000, 1000, "side", "left")
        expected = float(np.degrees(np.arctan2(100, 200)))
        self.assertAlmostEqual(right["measurements"]["torso_inclination_deg"], expected)
        self.assertAlmostEqual(right["measurements"]["sagittal_torso_inclination_deg"], expected)
        self.assertAlmostEqual(left["measurements"]["sagittal_torso_inclination_deg"], -expected)
        self.assertIsNone(right["measurements"]["lateral_trunk_inclination_deg"])
        self.assertEqual(left["quality"]["facing_source"], "supplied")

    def test_pixel_aspect_ratio_is_respected(self):
        xy, confidence = front_pose()
        xy[[11, 12], 0] += 0.1
        wide = measure_pose(xy, confidence, 2000, 1000, "front")
        self.assertAlmostEqual(wide["measurements"]["torso_inclination_deg"], 45.0)

    def test_roll_calibration_restores_lean_without_rotating_it_away(self):
        xy, confidence = front_pose()
        xy[[7, 8, 11, 12], 0] += 0.08
        original = measure_pose(xy, confidence, 1000, 1000, "front")
        theta = np.radians(11)
        rotation = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
        rotated_xy = (xy - 0.5) @ rotation.T + 0.5
        corrected = measure_pose(rotated_xy, confidence, 1000, 1000, "front", camera_roll_deg=11)
        uncorrected = measure_pose(rotated_xy, confidence, 1000, 1000, "front")
        for key in ("torso_inclination_deg", "lateral_trunk_inclination_deg", "neck_inclination_deg",
                    "shoulder_alignment_deg", "hip_alignment_deg"):
            self.assertAlmostEqual(corrected["measurements"][key], original["measurements"][key])
        self.assertGreater(corrected["measurements"]["torso_inclination_deg"], 20)
        self.assertAlmostEqual(uncorrected["measurements"]["torso_inclination_deg"],
                               original["measurements"]["torso_inclination_deg"] + 11)

    def test_visibility_and_presence_min_and_missing_pose_confidence(self):
        xy, scores = front_pose()
        confidence = np.column_stack([scores, np.ones(33)])
        confidence[11, 1] = 0.2
        confidence[24] = np.nan
        result = measure_pose(xy, confidence, 1000, 1000, "front")
        self.assertAlmostEqual(result["quality"]["pose_confidence"], (0.2 + 0.95 + 0.95 + 0) / 4, places=6)
        self.assertIsNone(result["measurements"]["torso_inclination_deg"])
        unknown = measure_pose(xy, None, 1000, 1000, "front")
        self.assertEqual(unknown["quality"]["pose_confidence"], 0)
        self.assertTrue(all(value is None for value in unknown["measurements"].values()))

    def test_facing_inference_requires_face_and_both_feet_consensus(self):
        xy, confidence = side_pose()
        agreed = measure_pose(xy, confidence, 1000, 1000, "side")
        self.assertEqual(agreed["quality"]["facing"], "right")
        xy[31, 0] = 0.43
        disputed = measure_pose(xy, confidence, 1000, 1000, "side")
        self.assertEqual(disputed["quality"]["facing"], "unknown")
        self.assertIsNone(disputed["measurements"]["sagittal_torso_inclination_deg"])
        self.assertEqual(disputed["quality"]["facing_reason"], "face_and_feet_disagree")
        supplied = measure_pose(xy, confidence, 1000, 1000, "side", "left")
        self.assertEqual(supplied["quality"]["facing"], "left")
        confidence[32] = 0.4
        missing = measure_pose(xy, confidence, 1000, 1000, "side")
        self.assertEqual(missing["quality"]["facing_reason"], "insufficient_high_confidence_face_and_both_feet")

    def test_side_joint_bends_and_degenerate_segments(self):
        xy, confidence = side_pose()
        straight = measure_pose(xy, confidence, 1000, 1000, "side", "right")
        self.assertAlmostEqual(straight["measurements"]["hip_flexion_deg"], 0)
        self.assertAlmostEqual(straight["measurements"]["knee_flexion_deg"], 0)
        xy[[25, 26]] = [[0.7, 0.5], [0.705, 0.5]]
        xy[[27, 28]] = [[0.7, 0.7], [0.705, 0.7]]
        bent = measure_pose(xy, confidence, 1000, 1000, "side", "right")
        self.assertAlmostEqual(bent["measurements"]["hip_flexion_deg"], 90)
        self.assertAlmostEqual(bent["measurements"]["knee_flexion_deg"], 90)
        xy[[25, 26]] = xy[[23, 24]]
        degenerate = measure_pose(xy, confidence, 1000, 1000, "side", "right")
        self.assertIsNone(degenerate["measurements"]["hip_flexion_deg"])
        self.assertEqual(degenerate["measurement_details"]["hip_flexion_deg"]["reason"],
                         "degenerate_or_too_short_projected_segment")

    def test_occluded_far_side_uses_visible_side_but_no_front_lateral_guess(self):
        xy, confidence = side_pose()
        confidence[[12, 24]] = 0.1
        side = measure_pose(xy, confidence, 1000, 1000, "side", "right")
        self.assertAlmostEqual(side["measurements"]["torso_inclination_deg"], 0)
        self.assertEqual(side["measurement_details"]["torso_inclination_deg"]["selected_body_side"], "left")
        front = measure_pose(xy, confidence, 1000, 1000, "front")
        self.assertIsNone(front["measurements"]["lateral_trunk_inclination_deg"])

    def test_offscreen_and_no_pose_return_json_safe_nulls(self):
        xy, confidence = front_pose()
        xy[11] = [-0.1, 0.2]
        result = measure_pose(xy, confidence, 1000, 1000, "front")
        self.assertEqual(result["measurement_details"]["torso_inclination_deg"]["reason"], "landmark_outside_image")
        no_pose = measure_pose(np.full((33, 2), np.nan), None, 1000, 1000)
        self.assertTrue(all(value is None for value in no_pose["measurements"].values()))
        self.assertEqual(no_pose["quality"]["pose_confidence"], 0)
        import json
        json.dumps(no_pose, allow_nan=False)

    def test_alignment_sign_is_independent_of_anatomical_landmark_order(self):
        xy, confidence = front_pose()
        xy[12, 1] -= 0.1
        result = measure_pose(xy, confidence, 1000, 1000, "front")
        self.assertAlmostEqual(result["measurements"]["shoulder_alignment_deg"], np.degrees(np.arctan2(100, 200)))
        xy[[11, 12]] = xy[[12, 11]]
        swapped = measure_pose(xy, confidence, 1000, 1000, "front")
        self.assertAlmostEqual(swapped["measurements"]["shoulder_alignment_deg"],
                               result["measurements"]["shoulder_alignment_deg"])

    def test_landmark_order_and_validation(self):
        self.assertEqual(len(LANDMARK_NAMES), 33)
        self.assertEqual(LANDMARK_NAMES[23], "left_hip")
        xy, confidence = front_pose()
        with self.assertRaises(ValueError):
            measure_pose(xy, confidence, 0, 1000)
        with self.assertRaises(ValueError):
            measure_pose(xy, confidence, 1000, 1000, viewpoint="automatic")


if __name__ == "__main__":
    unittest.main()
