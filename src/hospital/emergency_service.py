"""Future emergency-action port. The mock only stores local requests."""
from typing import Protocol

from .models import EmergencyResponse, ResponseStatus, InvalidResponseStateError, DuplicateResponseError


class EmergencyService(Protocol):
    """Providers must deduplicate by response_id and raise on failure."""
    def record_response(self, response: EmergencyResponse) -> None: ...


class MockEmergencyService:
    """Records requests only; does not contact hospitals or dispatch anything."""
    def __init__(self):
        self._requests: dict[str, EmergencyResponse] = {}

    @property
    def recorded_requests(self) -> list[EmergencyResponse]:
        return list(self._requests.values())

    def record_response(self, response: EmergencyResponse) -> None:
        if response.status != ResponseStatus.HOSPITAL_SELECTED:
            raise InvalidResponseStateError("A hospital must be selected before recording a request.")
        old = self._requests.get(response.response_id)
        if old is not None and old != response:
            raise DuplicateResponseError("Conflicting emergency request for response_id.")
        self._requests[response.response_id] = response
