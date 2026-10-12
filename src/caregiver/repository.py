from copy import deepcopy
from typing import Protocol

from .models import FallEvent, EventStatus, DuplicateEventError, EventNotFoundError, InvalidTransitionError


class FallEventRepository(Protocol):
    def create(self, event: FallEvent) -> FallEvent: ...
    def get(self, event_id: str) -> FallEvent: ...
    def update(self, event: FallEvent) -> FallEvent: ...
    def list_all(self) -> list[FallEvent]: ...
    def list_active(self) -> list[FallEvent]: ...


class InMemoryFallEventRepository:
    """Owns snapshots; callers cannot mutate stored metadata or bypass lifecycle."""
    def __init__(self):
        self._events = {}

    def create(self, event):
        if event.event_id in self._events:
            raise DuplicateEventError(event.event_id)
        if event.status != EventStatus.CONFIRMED:
            raise InvalidTransitionError("New events must be CONFIRMED.")
        self._events[event.event_id] = deepcopy(event)
        return self.get(event.event_id)

    def get(self, event_id):
        if event_id not in self._events:
            raise EventNotFoundError(event_id)
        return deepcopy(self._events[event_id])

    def update(self, event):
        old = self.get(event.event_id)
        if (old.person_id, old.timestamp, old.detection_probability, old.created_at, old.metadata) != (
            event.person_id, event.timestamp, event.detection_probability, event.created_at, event.metadata
        ):
            raise InvalidTransitionError("Event identity/details are immutable.")
        expected = {EventStatus.CONFIRMED: EventStatus.ALERT_SENT,
                    EventStatus.ALERT_SENT: EventStatus.ACKNOWLEDGED}
        if expected.get(old.status) != event.status:
            raise InvalidTransitionError(f"Invalid transition {old.status.value} -> {event.status.value}")
        self._events[event.event_id] = deepcopy(event)
        return self.get(event.event_id)

    def list_all(self):
        return deepcopy(list(self._events.values()))

    def list_active(self):
        return [e for e in self.list_all() if e.status != EventStatus.ACKNOWLEDGED]
