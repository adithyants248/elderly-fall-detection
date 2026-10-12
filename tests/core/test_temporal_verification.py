"""Deterministic synthetic sequences; elapsed seconds, no camera or model."""

import unittest
from unittest.mock import patch

from src.core.fall_detection.detector import FallDetector
from src.core.fall_verification.verifier import FallVerifier
from test_fall_features import person


def observation(track_id=1, lying=False, y=None, x=0):
    y = (180 if lying else 100) if y is None else y
    result = person(track_id, y, horizontal=lying)
    if lying:
        result["bbox"] = (x, y - 40, x + 240, y + 40)
    else:
        result["bbox"] = (x, y - 100, x + 100, y + 100)
    return result


class TemporalVerificationTests(unittest.TestCase):
    def test_continuous_candidate_without_captured_transition(self):
        detector = FallDetector()
        detector.analyze(observation(lying=True), timestamp=0)
        for i in range(1, 24):
            result = detector.analyze(observation(lying=True), timestamp=i / 10)
            self.assertTrue(result["fall_candidate"])
            if i < 21:
                self.assertFalse(result["fall_verified"])
        self.assertTrue(result["fall_verified"])
        self.assertEqual(result["verification"]["verification_start_time"], 0.1)

    def test_live_monotonic_candidate_without_transition(self):
        detector = FallDetector(inactivity_frames=2)
        with patch("src.core.fall_detection.detector.time.monotonic", side_effect=[i / 10 for i in range(25)]):
            for i in range(25):
                result = detector.analyze(observation(lying=True))
        self.assertTrue(result["fall_verified"])
        self.assertTrue(result["fall_confirmed"])
        self.assertEqual(result["verification"]["verification_start_time"], 0.1)

    def test_candidate_gap_restarts_full_window(self):
        detector = FallDetector()
        self.start_fall(detector)
        result = detector.analyze(observation(lying=True), timestamp=0.8)
        diagnostic = result["verification"]
        self.assertEqual(diagnostic["reset_reason"], "observation_gap")
        self.assertEqual(diagnostic["verification_start_time"], 0.8)
        self.assertEqual(diagnostic["elapsed_verification_seconds"], 0)
        for t in (1.0, 1.4, 1.8, 2.2, 2.6, 2.79):
            self.assertFalse(detector.analyze(observation(lying=True), timestamp=t)["fall_verified"])
        self.assertTrue(detector.analyze(observation(lying=True), timestamp=2.81)["fall_verified"])

    def test_upright_reports_reset_and_clears_timer(self):
        detector = FallDetector()
        self.start_fall(detector)
        result = detector.analyze(observation(), timestamp=0.3)
        self.assertFalse(result["verification"]["verification_active"])
        self.assertIsNone(result["verification"]["verification_start_time"])
        self.assertEqual(result["verification"]["reset_reason"], "not_lying")

    def test_candidate_without_lying_reports_posture_gate(self):
        detector = FallDetector()
        detector.analyze(person(), timestamp=0)
        for i in range(1, 25):
            # Torso + drop qualify, but the box stays tall.
            result = detector.analyze(person(hip_y=100 + 60 * i, horizontal=True), timestamp=i / 10)
            self.assertTrue(result["fall_candidate"])
            self.assertFalse(result["fall_verified"])
            self.assertEqual(result["verification"]["reason"], "not_lying")

    def start_fall(self, detector, track_id=1):
        detector.analyze(observation(track_id), timestamp=0)
        return detector.analyze(observation(track_id, True), timestamp=0.2)

    def reach_verified(self, detector, track_id=1):
        self.start_fall(detector, track_id)
        for i in range(3, 23):
            result = detector.analyze(observation(track_id, True), timestamp=i / 10)
        self.assertTrue(result["fall_verified"])
        return result

    def test_normal_walking(self):
        detector = FallDetector()
        for i in range(121):
            result = detector.analyze(
                observation(y=100 + i % 3, x=i * 2), timestamp=i / 30,
            )
            self.assertFalse(result["fall_verified"])
            self.assertFalse(result["fall_confirmed"])

    def test_sitting_down_with_downward_motion(self):
        detector = FallDetector()
        detector.analyze(observation(), timestamp=0)
        for i in range(1, 81):
            # Large hip drop, but upright torso and a tall box.
            result = detector.analyze(observation(y=180), timestamp=i / 20)
            self.assertFalse(result["fall_verified"])

    def test_brief_noise_and_immediate_recovery(self):
        detector = FallDetector(inactivity_frames=1)
        result = self.start_fall(detector)
        self.assertTrue(result["fall_candidate"])
        self.assertFalse(result["fall_verified"])
        for i in range(3, 41):
            result = detector.analyze(observation(), timestamp=i / 10)
            self.assertFalse(result["fall_verified"])
            self.assertFalse(result["fall_confirmed"])

    def test_fall_then_stillness_and_repeated_candidates(self):
        detector = FallDetector(inactivity_frames=3)
        result = self.reach_verified(detector)
        self.assertFalse(result["post_fall_inactive"])
        for i in range(23, 27):
            result = detector.analyze(observation(lying=True), timestamp=i / 10)
            self.assertTrue(result["fall_candidate"])
            self.assertTrue(result["fall_verified"])
            self.assertEqual(result["fall_confirmed"], i >= 25)
        self.assertEqual(detector.inactivity_state[1]["inactive_frames"], 3)

    def test_standing_clears_confirmed_state(self):
        detector = FallDetector(inactivity_frames=1)
        self.reach_verified(detector)
        result = detector.analyze(observation(lying=True), timestamp=2.3)
        self.assertTrue(result["fall_confirmed"])
        result = detector.analyze(observation(), timestamp=2.4)
        self.assertFalse(result["fall_verified"])
        self.assertFalse(result["post_fall_inactive"])
        self.assertFalse(result["fall_confirmed"])
        self.assertNotIn(1, detector.verifier.started_at)

    def test_movement_clears_inactivity_confirmation(self):
        detector = FallDetector(inactivity_frames=1)
        self.reach_verified(detector)
        self.assertTrue(detector.analyze(observation(lying=True), timestamp=2.3)["fall_confirmed"])
        result = detector.analyze(observation(lying=True, x=100), timestamp=2.4)
        self.assertTrue(result["fall_verified"])
        self.assertFalse(result["post_fall_inactive"])
        self.assertFalse(result["fall_confirmed"])

    def test_configured_seconds_at_different_fps(self):
        for window in (2.0, 2.5, 3.0):
            for fps in (15, 30, 60):
                with self.subTest(window=window, fps=fps):
                    detector = FallDetector(verification_window_seconds=window)
                    detector.analyze(observation(), timestamp=0)
                    onset = 1 / fps
                    first_verified = None
                    for i in range(1, int((window + 0.3) * fps) + 1):
                        t = i / fps
                        result = detector.analyze(observation(lying=True), timestamp=t)
                        if t - onset < window:
                            self.assertFalse(result["fall_verified"])
                        if result["fall_verified"] and first_verified is None:
                            first_verified = t
                    self.assertIsNotNone(first_verified)
                    self.assertGreaterEqual(first_verified - onset, window)
                    self.assertLessEqual(first_verified - onset, window + 1 / fps + 1e-9)

    def test_irregular_timestamps(self):
        detector = FallDetector()
        self.start_fall(detector)
        for t in (0.27, 0.6, 0.99, 1.1, 1.45, 1.8, 2.19):
            self.assertFalse(detector.analyze(observation(lying=True), timestamp=t)["fall_verified"])
        self.assertTrue(detector.analyze(observation(lying=True), timestamp=2.21)["fall_verified"])

    def test_many_frames_do_not_replace_elapsed_time(self):
        detector = FallDetector()
        self.start_fall(detector)
        for i in range(1, 101):
            result = detector.analyze(observation(lying=True), timestamp=0.2 + i / 1000)
            self.assertFalse(result["fall_verified"])

    def test_multiple_tracks_are_independent(self):
        detector = FallDetector()
        self.start_fall(detector, 1)
        for i in range(3, 24):
            a = detector.analyze(observation(1, True), timestamp=i / 10)
            b = detector.analyze(observation(2), timestamp=i / 10)
            self.assertFalse(b["fall_verified"])
        self.assertTrue(a["fall_verified"])

    def test_already_lying_requires_full_candidate_window(self):
        detector = FallDetector()
        for i in range(81):
            result = detector.analyze(observation(lying=True), timestamp=i / 20)
            self.assertEqual(result["fall_verified"], i / 20 - 0.05 >= 2.0)

    def test_slow_posture_change_starts_timer_only_when_lying(self):
        verifier = FallVerifier()
        for i in range(101):
            features = {
                "torso_angle": min(i, 90),
                "aspect_ratio": 1.5 if i >= 90 else 0.5,
                "hip_vertical_position": 100,
            }
            result = verifier.update(1, 2 / 3, timestamp=i / 10, fall_candidate=True, features=features)
            self.assertFalse(result["fall_verified"])
        self.assertEqual(result["verification_start_time"], 9.0)

    def test_missing_observations_cancel_verification(self):
        detector = FallDetector(inactivity_frames=1)
        self.reach_verified(detector)
        self.assertTrue(detector.analyze(observation(lying=True), timestamp=2.3)["fall_confirmed"])
        result = detector.analyze(observation(lying=True), timestamp=4)
        self.assertFalse(result["fall_verified"])
        self.assertFalse(result["fall_confirmed"])
        self.assertEqual(len(detector.verifier.history[1]), 1)

    def test_window_is_pruned_by_time_and_keeps_features(self):
        detector = FallDetector()
        self.reach_verified(detector)
        for i in range(23, 61):
            detector.analyze(observation(lying=True), timestamp=i / 10)
        history = detector.verifier.history[1]
        self.assertTrue(all(entry["timestamp"] >= 4 for entry in history))
        self.assertIn("fall_candidate", history[-1])
        for key in ("movement", "torso_angle", "hip_vertical_position", "vertical_velocity", "vertical_acceleration", "aspect_ratio"):
            self.assertIn(key, history[-1]["features"])

    def test_mixed_clock_sources_are_rejected(self):
        detector = FallDetector()
        detector.analyze(observation(), timestamp=0)
        with self.assertRaises(ValueError):
            detector.analyze(observation())
        detector.reset(1)
        with patch("src.core.fall_detection.detector.time.monotonic", return_value=10):
            detector.analyze(observation())
        with self.assertRaises(ValueError):
            detector.analyze(observation(), timestamp=11)

    def test_stale_cleanup_clears_all_stages(self):
        detector = FallDetector(stale_track_seconds=3)
        self.start_fall(detector)
        detector.analyze(observation(2), timestamp=2)
        self.assertEqual(detector.cleanup_stale_tracks(timestamp=4), [1])
        for mapping in (detector.history, detector.inactivity_state, detector.clock_sources, detector.verifier.history, detector.verifier.started_at):
            self.assertNotIn(1, mapping)
        self.assertIn(2, detector.history)

    def test_verifier_rejects_invalid_timestamps(self):
        verifier = FallVerifier()
        kwargs = {"fall_candidate": False, "features": {"torso_angle": 0, "aspect_ratio": 0.5}}
        verifier.update(1, 0, timestamp=1, **kwargs)
        for timestamp in (0, 1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                verifier.update(1, 0, timestamp=timestamp, **kwargs)
        self.assertEqual(len(verifier.history[1]), 1)

    def test_invalid_configuration(self):
        for window in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                FallDetector(verification_window_seconds=window)
        with self.assertRaises(ValueError):
            FallDetector(max_observation_gap_seconds=0)


if __name__ == "__main__":
    unittest.main()
