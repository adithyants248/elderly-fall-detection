"""Integration with the real decision layer; no inference/model dependencies."""
import unittest

from src.core.fall_verification.post_fall import PostFallVerifier
from src.caregiver.adapter import consume_verification_result
from src.caregiver.models import EventStatus
from src.caregiver.notifier import MockCaregiverNotifier
from src.caregiver.repository import InMemoryFallEventRepository
from src.caregiver.service import CaregiverResponseService


class VerifierAdapterTests(unittest.TestCase):
    def test_real_verifier_episode_alert_and_response(self):
        verifier = PostFallVerifier()
        notifier = MockCaregiverNotifier()
        service = CaregiverResponseService(InMemoryFallEventRepository(), notifier)
        motion = dict.fromkeys(verifier.config.motion_limits(), 0.0)
        motion["person_detected"] = 1
        confirmed_result = None
        for i in range(121):
            result = verifier.update(17, 0.30, motion, timestamp=i / 30)
            received = consume_verification_result(result, service)
            if result["state"] != "CONFIRMED_FALL":
                self.assertIsNone(received)
                self.assertEqual(notifier.sent_alerts, [])
            if received is not None:
                confirmed_result = result
        self.assertEqual(len(notifier.sent_alerts), 1)
        e = consume_verification_result(confirmed_result, service)
        self.assertEqual(len(notifier.sent_alerts), 1)
        acknowledged = service.acknowledge_event(e.event_id, "caregiver-17")
        self.assertEqual(acknowledged.status, EventStatus.ACKNOWLEDGED)
        self.assertEqual(service.get_active_alerts(), [])
        # Caregiver handling must not change the ML episode/latch.
        self.assertEqual(verifier.update(17, 0.1, motion, timestamp=5)["state"], "CONFIRMED_FALL")


if __name__ == "__main__":
    unittest.main()
