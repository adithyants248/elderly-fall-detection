from dataclasses import replace
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import Mock

from src.caregiver.models import FallEvent, EventStatus, EventNotFoundError
from src.caregiver.notifier import MockCaregiverNotifier
from src.caregiver.repository import InMemoryFallEventRepository
from src.caregiver.service import CaregiverResponseService
from src.hospital.models import (Location, ResponseStatus, MissingLocationError,
    EventNotAcknowledgedError, DuplicateResponseError, HospitalNotFoundError,
    InvalidResponseStateError, ResponseNotFoundError, HospitalError)
from src.hospital.repository import InMemoryEmergencyResponseRepository
from src.hospital.hospital_service import MockHospitalSearchService
from src.hospital.emergency_service import MockEmergencyService
from src.hospital.service import EmergencyResponseService


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 14, tzinfo=timezone.utc)
        self.caregivers = InMemoryFallEventRepository()
        self.caregiver = CaregiverResponseService(self.caregivers, MockCaregiverNotifier(), lambda: self.now)
        self.repo = InMemoryEmergencyResponseRepository()
        self.search = Mock(wraps=MockHospitalSearchService())
        self.emergency = MockEmergencyService()
        self.service = EmergencyResponseService(self.caregivers, self.repo, self.search, self.emergency, lambda: self.now)
        self.location = Location(0, 0)

    def acknowledge(self, event_id='E1'):
        self.caregiver.handle_confirmed_fall(FallEvent(event_id, 'person-1', 8.0, created_at=self.now))
        return self.caregiver.acknowledge_event(event_id, 'c1')

    def start(self):
        self.acknowledge()
        return self.service.start_response('E1', self.location)

    def select(self):
        r = self.start()
        return self.service.select_hospital(r.response_id, r.hospitals[1].hospital_id, 'c1')

    def test_unacknowledged_states_never_search_or_create(self):
        self.caregivers.create(FallEvent('E1', 'p1', 1, created_at=self.now))
        for status in (EventStatus.CONFIRMED, EventStatus.ALERT_SENT):
            with self.subTest(status=status), self.assertRaises(EventNotAcknowledgedError):
                self.service.start_response('E1', self.location)
            if status == EventStatus.CONFIRMED:
                self.caregiver.send_alert('E1')
        self.search.find_nearby_hospitals.assert_not_called()
        self.assertEqual(self.repo.list_all(), [])

    def test_missing_event(self):
        with self.assertRaises(EventNotFoundError):
            self.service.start_response('missing', self.location)

    def test_acknowledged_start_stores_location_and_preserves_caregiver(self):
        event = self.acknowledge()
        r = self.service.start_response('E1', self.location)
        self.assertEqual(r.status, ResponseStatus.HOSPITALS_AVAILABLE)
        self.assertEqual(r.location, self.location)
        self.assertEqual(self.caregivers.get('E1'), event)
        self.search.find_nearby_hospitals.assert_called_once_with(self.location)

    def test_missing_location_is_explicit_and_retryable(self):
        self.acknowledge()
        with self.assertRaisesRegex(MissingLocationError, 'cannot be performed'):
            self.service.start_response('E1', None)
        self.assertEqual(self.repo.list_all(), [])
        self.search.find_nearby_hospitals.assert_not_called()
        self.assertEqual(self.service.start_response('E1', self.location).status, ResponseStatus.HOSPITALS_AVAILABLE)

    def test_duplicate_start_and_conflicting_location(self):
        r = self.start()
        self.assertEqual(self.service.start_response('E1', self.location), r)
        self.assertEqual(len(self.repo.list_all()), 1)
        self.search.find_nearby_hospitals.assert_called_once()
        with self.assertRaises(DuplicateResponseError):
            self.service.start_response('E1', Location(1, 1))

    def test_concurrent_duplicate_start(self):
        self.acknowledge()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.service.start_response('E1', self.location), range(8)))
        self.assertEqual(len({r.response_id for r in results}), 1)
        self.assertEqual(len(self.repo.list_all()), 1)

    def test_complete_workflow_and_idempotent_record(self):
        r = self.select()
        self.assertEqual(r.status, ResponseStatus.HOSPITAL_SELECTED)
        self.assertEqual(r.selected_hospital_name, 'Mock City Hospital')
        self.assertEqual(r.selected_by, 'c1')
        self.assertEqual(r.selected_at, self.now)
        final = self.service.record_response(r.response_id)
        self.assertEqual(final.status, ResponseStatus.RESPONSE_RECORDED)
        self.assertEqual(final.recorded_at, self.now)
        self.assertEqual(self.service.record_response(r.response_id), final)
        self.assertEqual(self.service.start_response('E1', self.location), final)
        self.assertEqual(self.emergency.recorded_requests, [r])
        self.assertEqual(self.repo.list_active(), [])

    def test_unknown_hospital(self):
        r = self.start()
        with self.assertRaises(HospitalNotFoundError):
            self.service.select_hospital(r.response_id, 'unknown', 'c1')
        self.assertEqual(self.service.get_response(r.response_id), r)

    def test_selection_replay_and_conflict(self):
        r = self.select()
        self.assertEqual(self.service.select_hospital(r.response_id, r.selected_hospital_id, 'c1'), r)
        for hospital_id, caregiver in ((r.hospitals[0].hospital_id, 'c1'), (r.selected_hospital_id, 'c2')):
            with self.assertRaises(InvalidResponseStateError):
                self.service.select_hospital(r.response_id, hospital_id, caregiver)

    def test_empty_caregiver_rejected(self):
        r = self.start()
        with self.assertRaises(HospitalError):
            self.service.select_hospital(r.response_id, r.hospitals[0].hospital_id, '')

    def test_record_before_selection_rejected(self):
        r = self.start()
        with self.assertRaises(InvalidResponseStateError):
            self.service.record_response(r.response_id)
        self.assertEqual(self.emergency.recorded_requests, [])

    def test_empty_search_stays_retryable_and_cannot_select(self):
        self.search.find_nearby_hospitals.return_value = []
        r = self.start()
        self.assertEqual(r.status, ResponseStatus.ACKNOWLEDGED)
        self.assertEqual(self.service.get_nearby_hospitals(r.response_id), [])
        with self.assertRaises(InvalidResponseStateError):
            self.service.select_hospital(r.response_id, 'MOCK-H001', 'c1')
        self.search.find_nearby_hospitals.return_value = MockHospitalSearchService().find_nearby_hospitals(self.location)
        self.assertEqual(self.service.start_response('E1', self.location).status, ResponseStatus.HOSPITALS_AVAILABLE)

    def test_search_failure_retries_same_response(self):
        self.search.find_nearby_hospitals.side_effect = OSError('search failed')
        self.acknowledge()
        with self.assertRaises(OSError):
            self.service.start_response('E1', self.location)
        r = self.repo.get_by_event('E1')
        self.assertEqual(r.status, ResponseStatus.ACKNOWLEDGED)
        self.search.find_nearby_hospitals.side_effect = None
        self.assertEqual(self.service.start_response('E1', self.location).response_id, r.response_id)

    def test_emergency_failure_preserves_selection(self):
        r = self.select()
        self.service.emergency_service = Mock()
        self.service.emergency_service.record_response.side_effect = OSError('record failed')
        with self.assertRaises(OSError):
            self.service.record_response(r.response_id)
        self.assertEqual(self.service.get_response(r.response_id), r)
        self.service.emergency_service = self.emergency
        self.assertEqual(self.service.record_response(r.response_id).status, ResponseStatus.RESPONSE_RECORDED)

    def test_save_failure_after_record_deduplicates_mock_request(self):
        r = self.select()
        update = self.repo.update
        self.repo.update = Mock(side_effect=OSError('save failed'))
        with self.assertRaises(OSError):
            self.service.record_response(r.response_id)
        self.repo.update = update
        self.service.record_response(r.response_id)
        self.assertEqual(len(self.emergency.recorded_requests), 1)

    def test_multiple_events_independent(self):
        r1 = self.select()
        self.acknowledge('E2')
        r2 = self.service.start_response('E2', Location(1, 1))
        self.service.record_response(r1.response_id)
        self.assertNotEqual(r1.response_id, r2.response_id)
        self.assertEqual(self.repo.list_active(), [r2])

    def test_unknown_response_operations(self):
        for operation in (lambda: self.service.get_response('missing'),
                          lambda: self.service.get_nearby_hospitals('missing'),
                          lambda: self.service.select_hospital('missing', 'MOCK-H001', 'c1'),
                          lambda: self.service.record_response('missing')):
            with self.assertRaises(ResponseNotFoundError):
                operation()
