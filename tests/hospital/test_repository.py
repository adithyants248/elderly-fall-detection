from dataclasses import replace
import unittest

from src.hospital.models import (EmergencyResponse, Location, ResponseStatus,
    DuplicateResponseError, ResponseNotFoundError, InvalidResponseStateError)
from src.hospital.hospital_service import MockHospitalSearchService
from src.hospital.repository import InMemoryEmergencyResponseRepository


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryEmergencyResponseRepository()
        self.response = EmergencyResponse('R1', 'E1', Location(0, 0))
        self.options = tuple(MockHospitalSearchService().find_nearby_hospitals(self.response.location))

    def test_create_get_and_event_index(self):
        self.assertEqual(self.repo.create(self.response), self.response)
        self.assertEqual(self.repo.get('R1'), self.response)
        self.assertEqual(self.repo.get_by_event('E1'), self.response)
        self.assertIsNone(self.repo.get_by_event('missing'))

    def test_unknown_get_and_update(self):
        for operation in (lambda: self.repo.get('missing'), lambda: self.repo.update(self.response)):
            with self.assertRaises(ResponseNotFoundError):
                operation()

    def test_duplicate_response_and_event_ids(self):
        self.repo.create(self.response)
        for r in (self.response, replace(self.response, response_id='R2'), replace(self.response, event_id='E2')):
            with self.assertRaises(DuplicateResponseError):
                self.repo.create(r)

    def test_reject_advanced_creation(self):
        with self.assertRaises(InvalidResponseStateError):
            self.repo.create(replace(self.response, status=ResponseStatus.HOSPITALS_AVAILABLE, hospitals=self.options))

    def test_update_and_active_lifecycle(self):
        self.repo.create(self.response)
        available = self.repo.update(replace(self.response, status=ResponseStatus.HOSPITALS_AVAILABLE, hospitals=self.options))
        selected = self.repo.update(replace(available, status=ResponseStatus.HOSPITAL_SELECTED,
            selected_hospital_id=self.options[0].hospital_id, selected_hospital_name=self.options[0].name,
            selected_by='c1', selected_at=self.response.created_at))
        self.assertEqual(len(self.repo.list_active()), 1)
        recorded = self.repo.update(replace(selected, status=ResponseStatus.RESPONSE_RECORDED, recorded_at=selected.selected_at))
        self.assertEqual(self.repo.list_active(), [])
        self.assertEqual(self.repo.list_all(), [recorded])
        with self.assertRaises(InvalidResponseStateError):
            self.repo.update(selected)

    def test_identity_and_state_cannot_be_overwritten(self):
        self.repo.create(self.response)
        available = replace(self.response, status=ResponseStatus.HOSPITALS_AVAILABLE, hospitals=self.options)
        for r in (self.response, replace(available, event_id='E2'), replace(available, location=Location(1, 1))):
            with self.assertRaises(InvalidResponseStateError):
                self.repo.update(r)

    def test_returned_list_is_independent(self):
        self.repo.create(self.response)
        self.repo.list_all().clear()
        self.assertEqual(len(self.repo.list_all()), 1)
