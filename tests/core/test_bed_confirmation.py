"""End-to-end synthetic posture, timing and display contract tests."""
import unittest

from scripts.run_pipeline import display_status
from src.core.fall_detection.detector import FallDetector
from test_temporal_verification import observation


class BedConfirmationTests(unittest.TestCase):
    def test_safe_bed_sequence_at_different_rates(self):
        for fps in (3, 10, 30):
            with self.subTest(fps=fps):
                detector = FallDetector(inactivity_seconds=2.0)
                for i in range(3 * fps):
                    # Standing, then upright sitting with a lower hip position.
                    result = detector.analyze(observation(y=100 if i < fps else 150), timestamp=i / fps)
                    self.assertFalse(result["fall_confirmed"])
                verified_at = None
                confirmed_at = None
                for i in range(3 * fps, 9 * fps):
                    t = i / fps
                    # No abrupt hip drop required: safely lie at the same height.
                    result = detector.analyze(observation(lying=True, y=150), timestamp=t)
                    if result["fall_verified"] and verified_at is None:
                        verified_at = t
                    if result["fall_confirmed"] and confirmed_at is None:
                        confirmed_at = t
                self.assertIsNotNone(confirmed_at)
                self.assertGreaterEqual(confirmed_at - verified_at, 2)
                self.assertLessEqual(confirmed_at - verified_at, 2 + 1 / fps + 1e-9)
                self.assertIn("ID 1 FALL CONFIRMED", display_status(1, result))

    def test_movement_restarts_seconds_and_recovery_clears_state(self):
        detector = FallDetector(inactivity_seconds=2.0)
        for i in range(46):
            result = detector.analyze(observation(lying=True), timestamp=i / 10)
        self.assertTrue(result["fall_confirmed"])
        result = detector.analyze(observation(lying=True, x=100), timestamp=4.6)
        self.assertFalse(result["fall_confirmed"])
        self.assertEqual(result["inactivity"]["reason"], "movement")
        self.assertEqual(result["inactivity"]["elapsed_seconds"], 0)
        result = detector.analyze(observation(), timestamp=4.7)
        self.assertEqual(result["inactivity"]["reason"], "waiting_for_verification")
        self.assertIn("NORMAL", display_status(1, result))

    def test_gap_remains_visible_and_cannot_count_as_stillness(self):
        detector = FallDetector(inactivity_seconds=2.0)
        for i in range(46):
            detector.analyze(observation(lying=True), timestamp=i / 10)
        result = detector.analyze(observation(lying=True), timestamp=6)
        self.assertFalse(result["fall_confirmed"])
        self.assertEqual(result["inactivity"]["elapsed_seconds"], 0)
        self.assertIn("observation_gap", display_status(1, result))

    def test_display_states_follow_actual_flags(self):
        detector = FallDetector(inactivity_seconds=2.0)
        result = detector.analyze(observation(), timestamp=0)
        self.assertIn("ID 7 NORMAL", display_status(7, result))
        for i in range(1, 46):
            result = detector.analyze(observation(lying=True), timestamp=i / 10)
            expected = (
                "FALL CONFIRMED" if result["fall_confirmed"]
                else "FALL VERIFIED" if result["fall_verified"]
                else "FALL CANDIDATE"
            )
            self.assertIn(f"ID 7 {expected}", display_status(7, result))

    def test_invalid_inactivity_duration(self):
        for duration in (0, -1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                FallDetector(inactivity_seconds=duration)


if __name__ == "__main__":
    unittest.main()
