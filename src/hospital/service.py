"""Orchestrates responses exclusively after stored caregiver acknowledgement."""
from dataclasses import replace
from datetime import datetime
import logging
from threading import RLock
from typing import Callable
from uuid import uuid4

from src.caregiver.models import EventStatus, utc_now
from src.caregiver.repository import FallEventRepository
from .emergency_service import EmergencyService
from .hospital_service import HospitalSearchService
from .repository import EmergencyResponseRepository
from .models import (EmergencyResponse, Location, Hospital, ResponseStatus,
                     EventNotAcknowledgedError, MissingLocationError, DuplicateResponseError,
                     InvalidResponseStateError, HospitalNotFoundError, require_text)

logger = logging.getLogger(__name__)


class EmergencyResponseService:
    """Share one instance. Failed search/record operations remain retryable.

    Caregiver repository access is read-only. No ML imports or external actions.
    """
    def __init__(self, caregiver_repository: FallEventRepository,
                 repository: EmergencyResponseRepository, hospital_search: HospitalSearchService,
                 emergency_service: EmergencyService, clock: Callable[[], datetime] = utc_now):
        self.caregiver_repository = caregiver_repository
        self.repository = repository
        self.hospital_search = hospital_search
        self.emergency_service = emergency_service
        self.clock = clock
        self._lock = RLock()

    def start_response(self, event_id: str, location: Location | None) -> EmergencyResponse:
        with self._lock:
            event = self.caregiver_repository.get(event_id)  # Reuse EventNotFoundError.
            if event.status != EventStatus.ACKNOWLEDGED:
                raise EventNotAcknowledgedError("Caregiver acknowledgement is required before hospital response.")
            if not isinstance(location, Location):
                raise MissingLocationError("Nearby hospital lookup cannot be performed without a Location.")
            response = self.repository.get_by_event(event_id)
            if response is not None:
                if response.location != location:
                    raise DuplicateResponseError("Existing response has a different location.")
            else:
                response = self.repository.create(EmergencyResponse(
                    response_id=f"RESP-{uuid4()}", event_id=event_id, location=location,
                    created_at=max(self.clock(), event.acknowledged_at)))
                logger.info("Emergency response started; location received: %s", response.response_id)
            self.get_nearby_hospitals(response.response_id)
            return self.repository.get(response.response_id)

    def get_nearby_hospitals(self, response_id: str) -> list[Hospital]:
        with self._lock:
            response = self.repository.get(response_id)
            if response.status == ResponseStatus.ACKNOWLEDGED:
                logger.info("Hospital search requested: %s", response_id)
                hospitals = tuple(self.hospital_search.find_nearby_hospitals(response.location))
                if hospitals:
                    response = self.repository.update(replace(response, hospitals=hospitals,
                                                             status=ResponseStatus.HOSPITALS_AVAILABLE))
                logger.info("Hospital search returned %d options: %s", len(hospitals), response_id)
            return list(response.hospitals)

    def select_hospital(self, response_id: str, hospital_id: str, selected_by: str) -> EmergencyResponse:
        require_text(selected_by, "selected_by")
        with self._lock:
            response = self.repository.get(response_id)
            if response.status in (ResponseStatus.HOSPITAL_SELECTED, ResponseStatus.RESPONSE_RECORDED):
                if (response.selected_hospital_id, response.selected_by) == (hospital_id, selected_by):
                    return response
                raise InvalidResponseStateError("A hospital has already been selected.")
            if response.status != ResponseStatus.HOSPITALS_AVAILABLE:
                raise InvalidResponseStateError("Hospital selection requires available search results.")
            hospital = next((h for h in response.hospitals if h.hospital_id == hospital_id), None)
            if hospital is None:
                raise HospitalNotFoundError("Hospital is not among this response's search results.")
            updated = self.repository.update(replace(
                response, status=ResponseStatus.HOSPITAL_SELECTED, selected_hospital_id=hospital.hospital_id,
                selected_hospital_name=hospital.name, selected_by=selected_by, selected_at=self.clock()))
            logger.info("Hospital selected: %s", response_id)
            return updated

    def record_response(self, response_id: str) -> EmergencyResponse:
        with self._lock:
            response = self.repository.get(response_id)
            if response.status == ResponseStatus.RESPONSE_RECORDED:
                return response
            if response.status != ResponseStatus.HOSPITAL_SELECTED:
                raise InvalidResponseStateError("Select a hospital before recording the response.")
            updated = replace(response, status=ResponseStatus.RESPONSE_RECORDED, recorded_at=self.clock())
            self.emergency_service.record_response(response)
            updated = self.repository.update(updated)
            logger.info("Mock emergency response recorded: %s", response_id)
            return updated

    def get_response(self, response_id: str) -> EmergencyResponse:
        with self._lock:
            return self.repository.get(response_id)
