import unittest

from src.hospital.hospital_service import MockHospitalSearchService, geographic_distance_km
from src.hospital.models import Location, Hospital, HospitalError


class SearchTests(unittest.TestCase):
    def test_structured_mock_records(self):
        results = MockHospitalSearchService().find_nearby_hospitals(Location(0, 0))
        self.assertEqual(len(results), 3)
        self.assertTrue(all(isinstance(h, Hospital) and h.hospital_id.startswith('MOCK-')
                            and h.name.startswith('Mock ') for h in results))

    def test_deterministic_distance_order_and_limit(self):
        service = MockHospitalSearchService()
        results = service.find_nearby_hospitals(Location(0, 0))
        self.assertEqual(results, service.find_nearby_hospitals(Location(0, 0)))
        self.assertEqual(results, sorted(results, key=lambda h: (h.distance_km, h.hospital_id)))
        self.assertEqual(results[:2], service.find_nearby_hospitals(Location(0, 0), 2))

    def test_location_changes_distance_and_order(self):
        results = MockHospitalSearchService().find_nearby_hospitals(Location(.03, .03))
        self.assertEqual(results[0].hospital_id, 'MOCK-H003')
        self.assertEqual(results[0].distance_km, 0)

    def test_invalid_limit_or_location(self):
        for limit in (0, -1, True, 1.5):
            with self.assertRaises(HospitalError):
                MockHospitalSearchService().find_nearby_hospitals(Location(0, 0), limit)
        with self.assertRaises(HospitalError):
            MockHospitalSearchService().find_nearby_hospitals(None)

    def test_known_distance_and_symmetry(self):
        a, b = Location(0, 0), Location(0, 1)
        self.assertAlmostEqual(geographic_distance_km(a, b), 111.1949266, places=6)
        self.assertEqual(geographic_distance_km(a, b), geographic_distance_km(b, a))
        self.assertEqual(geographic_distance_km(a, a), 0)

    def test_antimeridian_and_antipodes(self):
        self.assertAlmostEqual(geographic_distance_km(Location(0, 179), Location(0, -179)), 222.389853, places=5)
        self.assertAlmostEqual(geographic_distance_km(Location(0, 0), Location(0, 180)), 20015.086796, places=5)
