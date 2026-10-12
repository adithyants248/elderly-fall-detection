from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .models import FallEvent, EventStatus, InvalidTransitionError


@dataclass(frozen=True)
class CaregiverAlert:
    event_id: str
    person_id: str
    source_timestamp: float
    received_at: datetime
    detection_probability: float
    message: str


def format_alert(event):
    probability = "unavailable" if event.detection_probability is None else f"{event.detection_probability:.2f}"
    return CaregiverAlert(
        event.event_id, event.person_id, event.timestamp, event.created_at,
        event.detection_probability,
        f"FALL ALERT\nPerson: {event.person_id}\nEvent: {event.event_id}\n"
        f"Source time: {event.timestamp:.3f}s (not wall-clock time)\n"
        f"Received: {event.created_at.isoformat()}\nStatus: Confirmed Fall\n"
        f"Detection probability: {probability}\nPlease check the person.",
    )


class CaregiverNotifier(Protocol):
    """Return after acceptance or raise. Future providers must deduplicate event_id."""
    def send_alert(self, event: FallEvent) -> None: ...


class MockCaregiverNotifier:
    """Records alerts only. No person or external service is contacted."""
    def __init__(self):
        self._alerts = {}

    @property
    def sent_alerts(self):
        return list(self._alerts.values())

    def send_alert(self, event):
        if event.status != EventStatus.CONFIRMED:
            raise InvalidTransitionError("Only a confirmed event can generate a new alert.")
        if event.event_id not in self._alerts:
            self._alerts[event.event_id] = format_alert(event)
