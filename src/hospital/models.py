"""Immutable response snapshots and validated geographic data."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import math

from src.caregiver.models import utc_now


class HospitalError(ValueError):
    """Domain error suitable for a future API boundary."""


class EventNotAcknowledgedError(HospitalError):
    pass


class ResponseNotFoundError(HospitalError):
    pass


class MissingLocationError(HospitalError):
    pass


class HospitalNotFoundError(HospitalError):
    pass


class InvalidResponseStateError(HospitalError):
    pass


class DuplicateResponseError(HospitalError):
    pass


def require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise HospitalError(f"{name} must be a nonempty string.")


def require_number(value: float, name: str, low: float, high: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise HospitalError(f"{name} must be finite and in [{low}, {high}].")


def require_time(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise HospitalError(f"{name} must be timezone-aware.")


@dataclass(frozen=True)
class Location:
    latitude: float
    longitude: float

    def __post_init__(self):
        require_number(self.latitude, "latitude", -90, 90)
        require_number(self.longitude, "longitude", -180, 180)


@dataclass(frozen=True)
class Hospital:
    hospital_id: str
    name: str
    address: str
    latitude: float
    longitude: float
    distance_km: float  # Geographic distance, never a driving/routing distance.
    phone: str | None = None

    def __post_init__(self):
        for name in ("hospital_id", "name", "address"):
            require_text(getattr(self, name), name)
        Location(self.latitude, self.longitude)
        require_number(self.distance_km, "distance_km", 0, math.inf)
        if self.phone is not None:
            require_text(self.phone, "phone")


class ResponseStatus(str, Enum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    HOSPITALS_AVAILABLE = "HOSPITALS_AVAILABLE"
    HOSPITAL_SELECTED = "HOSPITAL_SELECTED"
    RESPONSE_RECORDED = "RESPONSE_RECORDED"


@dataclass(frozen=True)
class EmergencyResponse:
    response_id: str
    event_id: str
    location: Location
    status: ResponseStatus = ResponseStatus.ACKNOWLEDGED
    hospitals: tuple[Hospital, ...] = ()
    selected_hospital_id: str | None = None
    selected_hospital_name: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    selected_at: datetime | None = None
    selected_by: str | None = None
    recorded_at: datetime | None = None

    def __post_init__(self):
        require_text(self.response_id, "response_id")
        require_text(self.event_id, "event_id")
        if not isinstance(self.location, Location):
            raise MissingLocationError("A Location is required for nearby hospital lookup.")
        if not isinstance(self.status, ResponseStatus):
            raise InvalidResponseStateError("status must be ResponseStatus.")
        require_time(self.created_at, "created_at")
        if not isinstance(self.hospitals, tuple) or any(not isinstance(h, Hospital) for h in self.hospitals):
            raise HospitalError("hospitals must be a tuple of Hospital records.")
        if len({h.hospital_id for h in self.hospitals}) != len(self.hospitals):
            raise HospitalError("Hospital option IDs must be unique.")
        if self.status == ResponseStatus.ACKNOWLEDGED and self.hospitals:
            raise InvalidResponseStateError("Hospital options require a completed search.")
        if self.status != ResponseStatus.ACKNOWLEDGED and not self.hospitals:
            raise InvalidResponseStateError("This state requires hospital options.")
        selected = self.status in (ResponseStatus.HOSPITAL_SELECTED, ResponseStatus.RESPONSE_RECORDED)
        if selected:
            require_text(self.selected_by, "selected_by")
            require_time(self.selected_at, "selected_at")
            if self.selected_at < self.created_at:
                raise HospitalError("Selection cannot precede creation.")
            if not any((h.hospital_id, h.name) == (self.selected_hospital_id, self.selected_hospital_name) for h in self.hospitals):
                raise HospitalNotFoundError("Selection must match an offered hospital.")
        elif any(v is not None for v in (self.selected_hospital_id, self.selected_hospital_name, self.selected_at, self.selected_by)):
            raise InvalidResponseStateError("Selection fields require HOSPITAL_SELECTED.")
        if self.status == ResponseStatus.RESPONSE_RECORDED:
            require_time(self.recorded_at, "recorded_at")
            if self.recorded_at < self.selected_at:
                raise HospitalError("Recording cannot precede selection.")
        elif self.recorded_at is not None:
            raise InvalidResponseStateError("recorded_at requires RESPONSE_RECORDED.")
