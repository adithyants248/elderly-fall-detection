"""Synthetic geometry and time-series tests; no model or camera required."""

import unittest
from unittest.mock import patch

from src.core.fall_detection.detector import FallDetector
from src.core.fall_detection.features import (
    bounding_box_aspect_ratio,
    bounding_box_height,
    bounding_box_width,
    body_center,
    body_center_movement,
    extract_features,
    torso_angle,
    vertical_acceleration,
    vertical_position,
    vertical_velocity,
)


def pose(hip_y=100.0, horizontal=False):
    points = [[0.0, 0.0, 1.0] for _ in range(17)]
    points[11] = [40.0, hip_y, 1.0]
    points[12] = [60.0, hip_y, 1.0]
    if horizontal:
        points[5] = [0.0, hip_y - 10, 1.0]
        points[6] = [0.0, hip_y + 10, 1.0]
    else:
        points[5] = [40.0, hip_y - 50, 1.0]
        points[6] = [60.0, hip_y - 50, 1.0]
    return points


def person(track_id=1, hip_y=100.0, horizontal=False):
    return {
        "track_id": track_id,
        "keypoints": pose(hip_y, horizontal),
        "bbox": (0, hip_y - 100, 100, hip_y + 100),
    }


class FeatureTests(unittest.TestCase):
    def test_posture_and_box_geometry(self):
        self.assertEqual(torso_angle(pose()), 0)
        self.assertEqual(torso_angle(pose(horizontal=True)), 90)
        self.assertEqual(vertical_position(pose(150)), 150)
        bbox = (10, 20, 70, 100)
        self.assertEqual(bounding_box_width(bbox), 60)
        self.assertEqual(bounding_box_height(bbox), 80)
        self.assertEqual(bounding_box_aspect_ratio(bbox), 0.75)
        self.assertEqual(body_center(bbox), (40, 60))
        self.assertEqual(body_center_movement((3, 4), (0, 0)), 5)

    def test_degenerate_box_preserves_existing_ratio_guard(self):
        self.assertEqual(bounding_box_aspect_ratio((0, 0, 10, 0)), 0)
        self.assertEqual(bounding_box_aspect_ratio((0, 10, 10, 0)), 0)

    def test_signed_derivatives(self):
        self.assertEqual(vertical_velocity(110, 100, 0.5), 20)
        self.assertEqual(vertical_velocity(90, 100, 0.5), -20)
        self.assertEqual(vertical_acceleration(10, 20, 0.5), -20)

    def test_missing_history_and_stationary_motion(self):
        first = extract_features(pose(), (0, 0, 100, 200))
        second = extract_features(pose(), (0, 0, 100, 200), first, dt=0.1)
        third = extract_features(pose(), (0, 0, 100, 200), second, dt=0.1)
        self.assertEqual(first.keys(), third.keys())
        self.assertIsNone(first["vertical_velocity"])
        self.assertIsNone(first["vertical_acceleration"])
        self.assertEqual(second["vertical_velocity"], 0)
        self.assertIsNone(second["vertical_acceleration"])
        self.assertEqual(third["vertical_acceleration"], 0)
        self.assertEqual(third["movement"], 0)

    def test_unequal_intervals_constant_acceleration(self):
        # y = 100 + 5*t**2: acceleration is 10 px/s**2.
        first = extract_features(pose(100), (0, 0, 100, 200))
        second = extract_features(pose(105), (0, 5, 100, 205), first, dt=1)
        third = extract_features(pose(145), (0, 45, 100, 245), second, dt=2)
        self.assertEqual(second["vertical_velocity"], 5)
        self.assertEqual(third["vertical_velocity"], 20)
        self.assertEqual(third["vertical_acceleration"], 10)
        self.assertEqual(third["vertical_drop"], 40)
        self.assertEqual(third["movement"], 40)
        self.assertIsNone(first["vertical_velocity"])  # Input was not mutated.

    def test_invalid_intervals(self):
        first = extract_features(pose(), (0, 0, 100, 200))
        for dt in (0, -1, float("nan"), float("inf")):
            with self.subTest(dt=dt):
                with self.assertRaises(ValueError):
                    vertical_velocity(1, 0, dt)
                with self.assertRaises(ValueError):
                    vertical_acceleration(1, 0, dt)
                with self.assertRaises(ValueError):
                    extract_features(pose(), (0, 0, 100, 200), first, dt=dt)
        with self.assertRaises(ValueError):
            extract_features(pose(), (0, 0, 100, 200), first)


class DetectorFeatureTests(unittest.TestCase):
    def test_matches_reusable_extraction(self):
        detector = FallDetector(history_size=2)
        previous = None
        for timestamp, y in ((0, 100), (1, 105), (3, 145), (4, 180)):
            observation = person(hip_y=y)
            dt = None if previous is None else timestamp - previous_time
            expected = extract_features(
                observation["keypoints"], observation["bbox"], previous, dt=dt,
            )
            actual = detector.analyze(observation, timestamp=timestamp)
            self.assertEqual(actual["features"], expected)
            previous, previous_time = expected, timestamp
        self.assertEqual(len(detector.history[1]), 2)

    def test_tracks_have_independent_motion_history(self):
        detector = FallDetector()
        detector.analyze(person(1, 100), timestamp=0)
        detector.analyze(person(2, 500), timestamp=0)
        first = detector.analyze(person(1, 110), timestamp=1)
        second = detector.analyze(person(2, 480), timestamp=2)
        self.assertEqual(first["features"]["vertical_velocity"], 10)
        self.assertEqual(second["features"]["vertical_velocity"], -10)

    def test_existing_fall_rule_does_not_bypass_verification(self):
        detector = FallDetector(inactivity_frames=2)
        self.assertEqual(detector.analyze(person(), timestamp=0)["score"], 0)
        result = detector.analyze(person(hip_y=160, horizontal=True), timestamp=1)
        self.assertTrue(result["fall_detected"])
        self.assertEqual(result["score"], 2 / 3)
        self.assertFalse(result["post_fall_inactive"])
        detector.analyze(person(hip_y=160), timestamp=2)
        result = detector.analyze(person(hip_y=160), timestamp=3)
        self.assertFalse(result["post_fall_inactive"])
        self.assertFalse(result["fall_confirmed"])

    def test_bad_timestamp_does_not_append_history(self):
        detector = FallDetector()
        detector.analyze(person(), timestamp=1)
        for timestamp in (1, 0, float("nan"), float("inf")):
            with self.subTest(timestamp=timestamp):
                with self.assertRaises(ValueError):
                    detector.analyze(person(), timestamp=timestamp)
                self.assertEqual(len(detector.history[1]), 1)

    def test_live_clock_default(self):
        detector = FallDetector()
        with patch("src.core.fall_detection.detector.time.monotonic", side_effect=[10, 10.5]):
            detector.analyze(person(hip_y=100))
            result = detector.analyze(person(hip_y=110))
        self.assertEqual(result["features"]["vertical_velocity"], 20)

    def test_returned_features_do_not_mutate_history(self):
        detector = FallDetector()
        result = detector.analyze(person(), timestamp=0)
        result["features"]["hip_vertical_position"] = -1000
        next_result = detector.analyze(person(), timestamp=1)
        self.assertEqual(next_result["features"]["vertical_velocity"], 0)

    def test_history_must_support_temporal_features(self):
        with self.assertRaises(ValueError):
            FallDetector(history_size=1)


if __name__ == "__main__":
    unittest.main()
