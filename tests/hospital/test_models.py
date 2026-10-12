from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import unittest

from src.hospital.models import (Location, Hospital, EmergencyResponse, ResponseStatus,
                                 HospitalError, InvalidResponseStateError)


class ModelTests(unittest.TestCase):
    def test_location(self):
        self.assertEqual(Location(0, 180).longitude, 180)
        self.assertEqual(Location(-90, -180).latitude, -90)

    def test_invalid_coordinates(self):
        for lat, lon in ((91, 0), (0, -181), (float('nan'), 0), (0, float('inf')), (True, 0), ('0', 0)):
            with self.subTest(lat=lat, lon=lon), self.assertRaises(HospitalError):
                Location(lat, lon)

    def test_hospital(self):
        h = Hospital('MOCK-1', 'Mock Hospital', 'Fictional address', 0, 0, 1.2)
        self.assertEqual(h.distance_km, 1.2)
        self.assertIsNone(h.phone)

    def test_invalid_hospital(self):
        h = Hospital('MOCK-1', 'Mock Hospital', 'Fictional address', 0, 0, 1.2)
        for changes in ({'hospital_id': ''}, {'name': ' '}, {'distance_km': -1},
                        {'distance_km': float('inf')}, {'phone': ''}):
            with self.subTest(changes=changes), self.assertRaises(HospitalError):
                replace(h, **changes)

    def test_response(self):
        r = EmergencyResponse('R1', 'E1', Location(0, 0))
        self.assertEqual(r.status, ResponseStatus.ACKNOWLEDGED)
        self.assertIsNotNone(r.created_at.utcoffset())
        with self.assertRaises(FrozenInstanceError):
            r.event_id = 'other'

    def test_invalid_response_fields(self):
        r = EmergencyResponse('R1', 'E1', Location(0, 0))
        for changes in ({'response_id': ''}, {'location': None}, {'status': 'ACKNOWLEDGED'},
                        {'created_at': datetime(2026, 1, 1)}, {'hospitals': []},
                        {'selected_by': 'c1'}, {'recorded_at': datetime.now(timezone.utc)}):
            with self.subTest(changes=changes), self.assertRaises(HospitalError):
                replace(r, **changes)

    def test_available_requires_options(self):
        with self.assertRaises(InvalidResponseStateError):
            EmergencyResponse('R1', 'E1', Location(0, 0), status=ResponseStatus.HOSPITALS_AVAILABLE)
