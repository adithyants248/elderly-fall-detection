from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock

from src.caregiver.adapter import consume_verification_result, event_from_payload
from src.caregiver.models import (FallEvent, EventStatus, CaregiverError,
    DuplicateEventError, EventNotFoundError, InvalidTransitionError)
from src.caregiver.notifier import MockCaregiverNotifier
from src.caregiver.repository import InMemoryFallEventRepository
from src.caregiver.service import CaregiverResponseService

NOW = datetime(2026, 9, 14, tzinfo=timezone.utc)


def event(event_id="event-1", person_id="1"):
    return FallEvent(event_id, person_id, 3.0, 0.87, created_at=NOW)


def result(event_id="event-1", track_id=1):
    return {"state": "CONFIRMED_FALL", "event": {
        "type": "confirmed_fall", "event_id": event_id, "track_id": track_id,
        "timestamp": 3.0, "suspected_at": 0.0, "fall_probability": 0.87,
    }}


class CaregiverTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryFallEventRepository()
        self.notifier = MockCaregiverNotifier()
        self.service = CaregiverResponseService(self.repository, self.notifier, lambda: NOW + timedelta(seconds=10))

    def test_event_creation(self):
        self.assertEqual(event().status, EventStatus.CONFIRMED)
        self.assertIsNone(event().acknowledged_at)

    def test_invalid_required_information(self):
        for changes in ({"event_id": ""}, {"person_id": " "}, {"timestamp": float("nan")},
                        {"detection_probability": 2}, {"created_at": datetime(2026, 1, 1)}):
            with self.subTest(changes=changes), self.assertRaises(CaregiverError):
                replace(event(), **changes)

    def test_repository_create_get(self):
        self.repository.create(event())
        self.assertEqual(self.repository.get("event-1"), event())

    def test_unknown_event(self):
        for operation in (lambda: self.service.get_event("missing"),
                          lambda: self.service.send_alert("missing"),
                          lambda: self.service.acknowledge_event("missing", "c1"),
                          lambda: self.repository.update(event())):
            with self.assertRaises(EventNotFoundError):
                operation()

    def test_repository_duplicate(self):
        self.repository.create(event())
        with self.assertRaises(DuplicateEventError):
            self.repository.create(event())

    def test_repository_snapshots(self):
        e = replace(event(), metadata={"nested": {"value": 1}})
        self.repository.create(e)
        e.metadata["nested"]["value"] = 2
        fetched = self.repository.get(e.event_id)
        fetched.metadata["nested"]["value"] = 3
        self.assertEqual(self.repository.get(e.event_id).metadata["nested"]["value"], 1)

    def test_confirmed_creates_and_sends(self):
        e = consume_verification_result(result(), self.service)
        self.assertEqual(e.status, EventStatus.ALERT_SENT)
        self.assertEqual(len(self.notifier.sent_alerts), 1)
        self.assertEqual(len(self.repository.list_all()), 1)

    def test_normal_no_alert(self):
        self.assertIsNone(consume_verification_result({**result(), "state": "NORMAL"}, self.service))
        self.assertEqual(self.notifier.sent_alerts, [])

    def test_suspected_no_alert(self):
        self.assertIsNone(consume_verification_result({**result(), "state": "FALL_SUSPECTED"}, self.service))
        self.assertEqual(self.repository.list_all(), [])

    def test_latched_frame_no_alert(self):
        self.assertIsNone(consume_verification_result({"state": "CONFIRMED_FALL", "event": None}, self.service))

    def test_confirmed_to_sent(self):
        self.repository.create(event())
        self.assertEqual(self.service.send_alert("event-1").status, EventStatus.ALERT_SENT)

    def test_acknowledgement_records_identity_and_time(self):
        self.service.handle_confirmed_fall(event())
        e = self.service.acknowledge_event("event-1", "caregiver-1")
        self.assertEqual(e.status, EventStatus.ACKNOWLEDGED)
        self.assertEqual(e.acknowledged_by, "caregiver-1")
        self.assertEqual(e.acknowledged_at, NOW + timedelta(seconds=10))

    def test_cannot_acknowledge_unsent(self):
        self.repository.create(event())
        with self.assertRaises(InvalidTransitionError):
            self.service.acknowledge_event("event-1", "c1")

    def test_cannot_resend_acknowledged(self):
        self.service.handle_confirmed_fall(event())
        self.service.acknowledge_event("event-1", "c1")
        with self.assertRaises(InvalidTransitionError):
            self.service.send_alert("event-1")

    def test_no_repository_backward_transition(self):
        self.service.handle_confirmed_fall(event())
        self.service.acknowledge_event("event-1", "c1")
        with self.assertRaises(InvalidTransitionError):
            self.repository.update(event())

    def test_duplicate_acknowledgement_preserves_original(self):
        self.service.handle_confirmed_fall(event())
        first = self.service.acknowledge_event("event-1", "c1")
        self.service.clock = lambda: NOW + timedelta(days=1)
        self.assertEqual(self.service.acknowledge_event("event-1", "c1"), first)
        with self.assertRaises(InvalidTransitionError):
            self.service.acknowledge_event("event-1", "c2")

    def test_invalid_caregiver(self):
        self.service.handle_confirmed_fall(event())
        for caregiver in (None, "", " "):
            with self.assertRaises(CaregiverError):
                self.service.acknowledge_event("event-1", caregiver)

    def test_duplicate_delivery_before_and_after_ack(self):
        for _ in range(3):
            consume_verification_result(result(), self.service)
        self.service.acknowledge_event("event-1", "c1")
        consume_verification_result(result(), self.service)
        self.assertEqual(len(self.notifier.sent_alerts), 1)
        self.assertEqual(len(self.repository.list_all()), 1)

    def test_conflicting_duplicate_rejected(self):
        consume_verification_result(result(), self.service)
        with self.assertRaises(DuplicateEventError):
            consume_verification_result(result(track_id=2), self.service)

    def test_multiple_events_and_active_list(self):
        consume_verification_result(result(), self.service)
        consume_verification_result(result("event-2", 2), self.service)
        self.service.acknowledge_event("event-1", "c1")
        self.assertEqual([e.event_id for e in self.service.get_active_alerts()], ["event-2"])
        self.assertEqual(len(self.repository.list_all()), 2)

    def test_unsent_event_is_active(self):
        self.repository.create(event())
        self.assertEqual(len(self.repository.list_active()), 1)

    def test_mock_content_and_idempotency(self):
        self.notifier.send_alert(event())
        self.notifier.send_alert(event())
        self.assertEqual(len(self.notifier.sent_alerts), 1)
        alert = self.notifier.sent_alerts[0]
        for text in ("Person: 1", "event-1", "0.87", "not wall-clock time", "Please check"):
            self.assertIn(text, alert.message)

    def test_missing_probability_supported(self):
        self.notifier.send_alert(replace(event(), detection_probability=None))
        self.assertIn("unavailable", self.notifier.sent_alerts[0].message)

    def test_notifier_failure_retains_retryable_state(self):
        notifier = Mock()
        notifier.send_alert.side_effect = OSError("delivery unavailable")
        service = CaregiverResponseService(self.repository, notifier)
        with self.assertRaises(OSError):
            service.handle_confirmed_fall(event())
        self.assertEqual(self.repository.get("event-1").status, EventStatus.CONFIRMED)
        notifier.send_alert.side_effect = None
        self.assertEqual(service.send_alert("event-1").status, EventStatus.ALERT_SENT)

    def test_save_failure_after_delivery_does_not_duplicate_mock(self):
        original = self.repository.update
        self.repository.update = Mock(side_effect=OSError("save failed"))
        with self.assertRaises(OSError):
            self.service.handle_confirmed_fall(event())
        self.repository.update = original
        self.service.send_alert("event-1")
        self.assertEqual(len(self.notifier.sent_alerts), 1)

    def test_payload_validation(self):
        for payload in ({}, {"type": "suspected_fall"}, {"type": "confirmed_fall"}):
            with self.assertRaises(CaregiverError):
                event_from_payload(payload)

    def test_person_mapping_and_source_time_preserved(self):
        e = event_from_payload(result()["event"], person_id="registered-person", received_at=NOW)
        self.assertEqual(e.person_id, "registered-person")
        self.assertEqual(e.timestamp, 3.0)
        self.assertEqual(e.created_at, NOW)
        self.assertEqual(e.metadata["track_id"], 1)

    def test_no_ml_imports_required(self):
        # Contract fixture matches PostFallVerifier's event without importing it.
        self.assertEqual(consume_verification_result(result(), self.service).event_id, "event-1")


if __name__ == "__main__":
    unittest.main()
