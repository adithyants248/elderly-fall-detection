"""Application composition and same-process verifier integration."""
from threading import RLock
from uuid import uuid4
from src.caregiver.adapter import consume_verification_result
from src.caregiver.notifier import MockCaregiverNotifier
from src.caregiver.repository import InMemoryFallEventRepository
from src.caregiver.service import CaregiverResponseService
from src.hospital.models import Location, ResponseNotFoundError
from src.hospital.repository import InMemoryEmergencyResponseRepository
from src.hospital.hospital_service import MockHospitalSearchService
from src.hospital.emergency_service import MockEmergencyService
from src.hospital.service import EmergencyResponseService
from .models import FallView
from src.caregiver.models import EventStatus


class ApplicationContext:
    def __init__(self, *, demo_enabled=True, location=Location(0, 0)):
        self.lock = RLock()
        self.demo_enabled = demo_enabled
        self.location = location  # Explicit fictional prototype coordinates, not GPS.
        self.falls = InMemoryFallEventRepository()
        self.responses = InMemoryEmergencyResponseRepository()
        self.caregiver = CaregiverResponseService(self.falls, MockCaregiverNotifier())
        self.hospital = EmergencyResponseService(self.falls, self.responses,
            MockHospitalSearchService(), MockEmergencyService())
        self._simulated = set()

    def consume_verification_result(self, result, *, person_id=None):
        """Call from an application-owned producer in THIS process, not another worker."""
        with self.lock:
            return consume_verification_result(result, self.caregiver, person_id=person_id)

    def demo_fall(self):
        with self.lock:
            event_id = f'DEMO-{uuid4()}'
            event = self.consume_verification_result({
                'state': 'CONFIRMED_FALL', 'event': {
                    'type': 'confirmed_fall', 'event_id': event_id, 'track_id': 'demo-person',
                    'timestamp': 8.0, 'fall_probability': .87,
                }}, person_id='SIMULATED-PERSON')
            self._simulated.add(event_id)
            return self.view(event)

    def view(self, event):
        return FallView(**{key: getattr(event, key) for key in (
            'event_id', 'person_id', 'timestamp', 'detection_probability', 'status',
            'created_at', 'acknowledged_at', 'acknowledged_by')},
            simulated=event.event_id in self._simulated,
            emergency_response=self.responses.get_by_event(event.event_id))

    def response_for(self, event_id):
        self.caregiver.get_event(event_id)
        response = self.responses.get_by_event(event_id)
        if response is None:
            raise ResponseNotFoundError('Request hospitals for this acknowledged event first.')
        return response

    def camera_events_acknowledged(self, event_ids):
        """Read-only gate for an explicit ML rearm; never acknowledges events."""
        with self.lock:
            return all(self.falls.get(event_id).status == EventStatus.ACKNOWLEDGED
                       for event_id in event_ids)
