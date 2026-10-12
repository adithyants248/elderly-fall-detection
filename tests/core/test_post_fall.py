import math
from pathlib import Path
import unittest
from unittest.mock import patch

from src.core.fall_verification.post_fall import (
    FEATURE_NAMES, PostFallConfig, PostFallVerifier,
)
from src.core.fall_detection.model_schema import ArtifactPaths


def still(**changes):
    values = dict.fromkeys(PostFallConfig().motion_limits(), 0.0)
    values["person_detected"] = 1
    values.update(changes)
    return values


class PostFallTests(unittest.TestCase):
    def confirm(self, verifier, track_id=1):
        events = []
        for i in range(101):
            result = verifier.update(track_id, 0.3, still(), i / 30)
            if i < 90:
                self.assertFalse(result["fall_confirmed"])
            if result["event"]:
                events.append(result["event"])
        self.assertTrue(result["fall_confirmed"])
        return events

    def test_normal(self):
        verifier = PostFallVerifier()
        for i in range(100):
            self.assertEqual(verifier.update(1, 0.29, still(), i / 30)["state"], "NORMAL")

    def test_threshold_inclusive_and_initial_motion_allowed(self):
        result = PostFallVerifier().update(1, 0.3, still(body_center_movement=100), 0)
        self.assertEqual(result["state"], "FALL_SUSPECTED")
        self.assertIsNone(result["event"])

    def test_three_seconds_and_one_event(self):
        events = self.confirm(PostFallVerifier())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["timestamp"], 3)
        self.assertEqual(events[0]["track_id"], 1)

    def test_each_motion_signal_cancels_in_either_direction(self):
        for name, limit in PostFallConfig().motion_limits().items():
            for sign in (-1, 1):
                verifier = PostFallVerifier()
                verifier.update(1, 0.3, still(), 0)
                result = verifier.update(1, 0.9, still(**{name: sign * (limit + 1)}), 0.1)
                self.assertEqual(result["state"], "NORMAL")
                self.assertEqual(result["reason"], "movement_resumed")

    def test_low_probability_does_not_cancel_still_suspect(self):
        verifier = PostFallVerifier()
        verifier.update(1, 0.5, still(), 0)
        for i in range(1, 31):
            result = verifier.update(1, 0.1, still(), i / 10)
        self.assertTrue(result["fall_confirmed"])

    def test_missing_motion_and_missing_person_cancel(self):
        for features in ({}, still(person_detected=0), still(torso_angle_change=math.nan)):
            verifier = PostFallVerifier()
            verifier.update(1, 0.3, still(), 0)
            self.assertEqual(verifier.update(1, 0.3, features, 0.1)["state"], "NORMAL")

    def test_gap_cannot_confirm(self):
        verifier = PostFallVerifier()
        verifier.update(1, 0.3, still(), 0)
        result = verifier.update(1, 0.3, still(), 4)
        self.assertEqual(result["reason"], "observation_gap")
        self.assertEqual(result["state"], "NORMAL")

    def test_warmup_without_probability(self):
        result = PostFallVerifier().update(1, None, still(), 0)
        self.assertEqual(result["state"], "NORMAL")

    def test_tracks_and_explicit_reset(self):
        verifier = PostFallVerifier()
        first_event = self.confirm(verifier)[0]
        self.assertEqual(verifier.update(2, 0.1, still(), 4)["state"], "NORMAL")
        result = verifier.update(1, 0.1, still(body_center_movement=50), 4)
        self.assertEqual(result["state"], "CONFIRMED_FALL")
        self.assertIsNone(result["event"])
        verifier.reset(1)
        second_event = self.confirm(verifier)[0]
        self.assertNotEqual(first_event["event_id"], second_event["event_id"])

    def test_cleanup_preserves_unhandled_confirmation(self):
        verifier = PostFallVerifier()
        self.confirm(verifier)
        verifier.update(2, 0.2, still(), 0)
        self.assertEqual(verifier.cleanup_stale_tracks(timestamp=20), [2])
        self.assertEqual(verifier.update(1, None, {}, 21)["state"], "CONFIRMED_FALL")

    def test_clock_and_probability_validation(self):
        verifier = PostFallVerifier()
        verifier.update(1, 0.3, still(), 1)
        for timestamp in (1, 0, math.inf, math.nan):
            with self.assertRaises(ValueError):
                verifier.update(1, 0.3, still(), timestamp)
        with self.assertRaises(ValueError):
            verifier.update(1, 0.3, still())
        for probability in (-0.1, 1.1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                verifier.update(1, probability, still(), 2)

    def test_monotonic_default(self):
        with patch("src.core.fall_verification.post_fall.time.monotonic", side_effect=[0, 0.1]):
            verifier = PostFallVerifier()
            verifier.update(1, 0.3, still())
            self.assertEqual(verifier.update(1, 0.3, still())["elapsed_seconds"], 0.1)

    def test_vector_order_and_shape(self):
        vector = [0.0] * 20
        vector[19] = 1
        verifier = PostFallVerifier()
        self.assertEqual(verifier.update_vector(1, 0.3, vector, 0)["state"], "FALL_SUSPECTED")
        vector[15] = 20  # hip_horizontal_velocity
        self.assertEqual(verifier.update_vector(1, 0.3, vector, 0.1)["state"], "NORMAL")
        self.assertEqual(FEATURE_NAMES[15], "hip_horizontal_velocity")
        with self.assertRaises(ValueError):
            verifier.update_vector(1, 0.3, [0] * 19, 0.2)

    def test_saved_threshold_is_used_and_cannot_change(self):
        path = ArtifactPaths().threshold
        PostFallVerifier(threshold_path=path)
        with patch.object(Path, "read_text", return_value="0.5"):
            with self.assertRaises(ValueError):
                PostFallVerifier(threshold_path=path)

    def test_config_validation(self):
        with self.assertRaises(ValueError):
            PostFallConfig(inactivity_seconds=0)

    def test_elapsed_duration_at_multiple_fps(self):
        for fps in (10, 15, 30):
            verifier = PostFallVerifier()
            for i in range(3 * fps + 1):
                result = verifier.update(1, 0.3, still(), i / fps)
                self.assertEqual(result["fall_confirmed"], i == 3 * fps)


if __name__ == "__main__":
    unittest.main()
