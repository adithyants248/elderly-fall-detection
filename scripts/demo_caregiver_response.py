"""Software-only demonstration. No real caregiver or emergency service contacted."""
from src.caregiver.adapter import consume_verification_result
from src.caregiver.notifier import MockCaregiverNotifier
from src.caregiver.repository import InMemoryFallEventRepository
from src.caregiver.service import CaregiverResponseService


def main():
    repository = InMemoryFallEventRepository()
    notifier = MockCaregiverNotifier()
    service = CaregiverResponseService(repository, notifier)
    print("CAREGIVER RESPONSE DEMO (mock only)")
    result = {"state": "CONFIRMED_FALL", "event": {
        "type": "confirmed_fall", "event_id": "DEMO-001", "track_id": 1,
        "timestamp": 8.0, "suspected_at": 5.0, "fall_probability": 0.87,
    }}
    event = consume_verification_result(result, service)
    print("Confirmed fall received: CONFIRMED ->", event.status.value)
    print(notifier.sent_alerts[0].message)
    event = service.acknowledge_event(event.event_id, "demo-caregiver")
    print(f"Response: {event.status.value} by {event.acknowledged_by} at {event.acknowledged_at.isoformat()}")
    print("No real notifications sent. Workflow ends at acknowledgement.")


if __name__ == "__main__":
    main()
