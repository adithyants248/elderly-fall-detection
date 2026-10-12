import logging
from threading import RLock

from .models import (EventStatus, EventNotFoundError, DuplicateEventError,
                     InvalidTransitionError, require_id, utc_now)

logger = logging.getLogger(__name__)


class CaregiverResponseService:
    """Business logic only. Share one service instance for serialized operations.

    A notifier failure leaves CONFIRMED for explicit retry. A future notifier
    must use event_id for idempotent delivery if delivery succeeds but saving
    ALERT_SENT fails. No exactly-once external delivery guarantee is claimed.
    """
    def __init__(self, repository, notifier, clock=utc_now):
        self.repository = repository
        self.notifier = notifier
        self.clock = clock
        self._lock = RLock()

    def handle_confirmed_fall(self, event):
        with self._lock:
            if event.status != EventStatus.CONFIRMED:
                raise InvalidTransitionError("Input must be a confirmed fall event.")
            try:
                existing = self.repository.get(event.event_id)
            except EventNotFoundError:
                existing = self.repository.create(event)
                logger.info("Confirmed fall event created: %s", event.event_id)
            else:
                if (existing.person_id, existing.timestamp, existing.detection_probability, existing.metadata) != (
                    event.person_id, event.timestamp, event.detection_probability, event.metadata
                ):
                    raise DuplicateEventError("Conflicting payload for an existing event_id.")
            if existing.status == EventStatus.CONFIRMED:
                return self.send_alert(existing.event_id)
            return existing  # Idempotent replay, including after acknowledgement.

    def send_alert(self, event_id):
        with self._lock:
            event = self.repository.get(event_id)
            if event.status == EventStatus.ALERT_SENT:
                return event
            if event.status != EventStatus.CONFIRMED:
                raise InvalidTransitionError("Cannot send an acknowledged event.")
            self.notifier.send_alert(event)
            updated = self.repository.update(event.mark_alert_sent())
            logger.info("Caregiver alert accepted: %s", event_id)
            return updated

    def get_event(self, event_id):
        with self._lock:
            return self.repository.get(event_id)

    def get_active_alerts(self):
        with self._lock:
            return self.repository.list_active()

    def acknowledge_event(self, event_id, caregiver_id):
        require_id(caregiver_id, "caregiver_id")
        with self._lock:
            event = self.repository.get(event_id)
            if event.status == EventStatus.ACKNOWLEDGED:
                if event.acknowledged_by == caregiver_id:
                    return event  # Preserve original response timestamp.
                raise InvalidTransitionError("Event was already acknowledged by another caregiver.")
            updated = self.repository.update(event.acknowledge(caregiver_id, self.clock()))
            logger.info("Caregiver response recorded: %s", event_id)
            return updated
