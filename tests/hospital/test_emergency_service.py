from dataclasses import replace
import unittest

from src.hospital.models import (EmergencyResponse, Location, ResponseStatus,
                                 InvalidResponseStateError, DuplicateResponseError)
from src.hospital.hospital_service import MockHospitalSearchService
from src.hospital.emergency_service import MockEmergencyService


class EmergencyTests(unittest.TestCase):
    def setUp(self):
        r = EmergencyResponse('R1', 'E1', Location(0, 0))
        options = tuple(MockHospitalSearchService().find_nearby_hospitals(r.location))
        self.initial = r
        self.selected = replace(r, status=ResponseStatus.HOSPITAL_SELECTED, hospitals=options,
            selected_hospital_id=options[0].hospital_id, selected_hospital_name=options[0].name,
            selected_by='c1', selected_at=r.created_at)
        self.service = MockEmergencyService()

    def test_records_and_deduplicates(self):
        self.service.record_response(self.selected)
        self.service.record_response(self.selected)
        self.assertEqual(self.service.recorded_requests, [self.selected])

    def test_requires_selection(self):
        with self.assertRaises(InvalidResponseStateError):
            self.service.record_response(self.initial)

    def test_conflicting_request_rejected(self):
        self.service.record_response(self.selected)
        with self.assertRaises(DuplicateResponseError):
            self.service.record_response(replace(self.selected, selected_by='c2'))

    def test_request_list_cannot_mutate_storage(self):
        self.service.record_response(self.selected)
        self.service.recorded_requests.clear()
        self.assertEqual(len(self.service.recorded_requests), 1)
