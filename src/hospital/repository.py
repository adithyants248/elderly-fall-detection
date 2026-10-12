"""Process-local response storage; lifecycle enforcement independent of services."""
from typing import Protocol

from .models import (EmergencyResponse, ResponseStatus, ResponseNotFoundError,
                     DuplicateResponseError, InvalidResponseStateError)


class EmergencyResponseRepository(Protocol):
    def create(self, response: EmergencyResponse) -> EmergencyResponse: ...
    def get(self, response_id: str) -> EmergencyResponse: ...
    def get_by_event(self, event_id: str) -> EmergencyResponse | None: ...
    def update(self, response: EmergencyResponse) -> EmergencyResponse: ...
    def list_all(self) -> list[EmergencyResponse]: ...
    def list_active(self) -> list[EmergencyResponse]: ...


class InMemoryEmergencyResponseRepository:
    """Immutable records. Share one orchestration service for serialized access."""
    def __init__(self):
        self._responses: dict[str, EmergencyResponse] = {}
        self._events: dict[str, str] = {}

    def create(self, response: EmergencyResponse) -> EmergencyResponse:
        if response.response_id in self._responses or response.event_id in self._events:
            raise DuplicateResponseError("A response already exists for this response/event ID.")
        if response.status != ResponseStatus.ACKNOWLEDGED:
            raise InvalidResponseStateError("New responses must start at ACKNOWLEDGED.")
        self._responses[response.response_id] = response
        self._events[response.event_id] = response.response_id
        return response

    def get(self, response_id: str) -> EmergencyResponse:
        if response_id not in self._responses:
            raise ResponseNotFoundError(response_id)
        return self._responses[response_id]

    def get_by_event(self, event_id: str) -> EmergencyResponse | None:
        response_id = self._events.get(event_id)
        return self.get(response_id) if response_id is not None else None

    def update(self, response: EmergencyResponse) -> EmergencyResponse:
        old = self.get(response.response_id)
        if (old.event_id, old.location, old.created_at) != (response.event_id, response.location, response.created_at):
            raise InvalidResponseStateError("Response identity and location are immutable.")
        expected = {ResponseStatus.ACKNOWLEDGED: ResponseStatus.HOSPITALS_AVAILABLE,
                    ResponseStatus.HOSPITALS_AVAILABLE: ResponseStatus.HOSPITAL_SELECTED,
                    ResponseStatus.HOSPITAL_SELECTED: ResponseStatus.RESPONSE_RECORDED}
        if expected.get(old.status) != response.status:
            raise InvalidResponseStateError(f"Invalid transition {old.status.value} -> {response.status.value}")
        if old.status != ResponseStatus.ACKNOWLEDGED and old.hospitals != response.hospitals:
            raise InvalidResponseStateError("Offered hospital options are immutable.")
        if old.status == ResponseStatus.HOSPITAL_SELECTED:
            fields = ("selected_hospital_id", "selected_hospital_name", "selected_by", "selected_at")
            if any(getattr(old, key) != getattr(response, key) for key in fields):
                raise InvalidResponseStateError("Recorded selection is immutable.")
        self._responses[response.response_id] = response
        return response

    def list_all(self) -> list[EmergencyResponse]:
        return list(self._responses.values())

    def list_active(self) -> list[EmergencyResponse]:
        return [r for r in self.list_all() if r.status != ResponseStatus.RESPONSE_RECORDED]
