from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import math


class CaregiverError(ValueError):
    """Base domain error suitable for a future API boundary."""


class EventNotFoundError(CaregiverError):
    pass


class DuplicateEventError(CaregiverError):
    pass


class InvalidTransitionError(CaregiverError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def require_id(value, name):
    if not isinstance(value, str) or not value.strip():
        raise CaregiverError(f"{name} must be a nonempty string.")


class EventStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    ALERT_SENT = "ALERT_SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"


@dataclass(frozen=True)
class FallEvent:
    event_id: str
    person_id: str
    timestamp: float  # Original source seconds, NOT Unix wall time.
    detection_probability: float = None
    status: EventStatus = EventStatus.CONFIRMED
    created_at: datetime = field(default_factory=utc_now)
    acknowledged_at: datetime = None
    acknowledged_by: str = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        require_id(self.event_id, "event_id")
        require_id(self.person_id, "person_id")
        if isinstance(self.timestamp, bool) or not isinstance(self.timestamp, (int, float)) or not math.isfinite(self.timestamp):
            raise CaregiverError("timestamp must be finite source seconds.")
        probability = self.detection_probability
        if probability is not None and (isinstance(probability, bool) or not isinstance(probability, (int, float)) or not math.isfinite(probability) or not 0 <= probability <= 1):
            raise CaregiverError("detection_probability must be in [0, 1].")
        if not isinstance(self.status, EventStatus):
            raise CaregiverError("status must be EventStatus.")
        if not isinstance(self.created_at, datetime) or self.created_at.utcoffset() is None:
            raise CaregiverError("created_at must be timezone-aware.")
        if not isinstance(self.metadata, dict):
            raise CaregiverError("metadata must be a dictionary.")
        if self.status == EventStatus.ACKNOWLEDGED:
            require_id(self.acknowledged_by, "acknowledged_by")
            if not isinstance(self.acknowledged_at, datetime) or self.acknowledged_at.utcoffset() is None:
                raise CaregiverError("acknowledged_at must be timezone-aware.")
            if self.acknowledged_at < self.created_at:
                raise CaregiverError("Acknowledgement cannot precede creation.")
        elif self.acknowledged_at is not None or self.acknowledged_by is not None:
            raise CaregiverError("Only acknowledged events may contain a response.")

    def mark_alert_sent(self):
        if self.status != EventStatus.CONFIRMED:
            raise InvalidTransitionError("Only CONFIRMED can become ALERT_SENT.")
        return replace(self, status=EventStatus.ALERT_SENT)

    def acknowledge(self, caregiver_id, at):
        require_id(caregiver_id, "caregiver_id")
        if self.status != EventStatus.ALERT_SENT:
            raise InvalidTransitionError("Only ALERT_SENT can become ACKNOWLEDGED.")
        return replace(self, status=EventStatus.ACKNOWLEDGED,
                       acknowledged_by=caregiver_id, acknowledged_at=at)
