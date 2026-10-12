"""Hospital search port and deterministic fictional hospital catalog."""
import math
from typing import Protocol

from .models import Hospital, HospitalError, Location, MissingLocationError


def geographic_distance_km(origin: Location, destination: Location) -> float:
    """Haversine great-circle distance using a mean Earth radius of 6371 km."""
    lat1, lat2 = math.radians(origin.latitude), math.radians(destination.latitude)
    dlat = lat2 - lat1
    dlon = math.radians(destination.longitude - origin.longitude)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


class HospitalSearchService(Protocol):
    def find_nearby_hospitals(self, location: Location, limit: int = 3) -> list[Hospital]: ...


class MockHospitalSearchService:
    """Fixed fictional coordinates around (0, 0); no network or location access.

    Results are the closest entries in this demo catalog, with no radius filter.
    They do not represent actual hospitals near the caller.
    """
    def find_nearby_hospitals(self, location: Location, limit: int = 3) -> list[Hospital]:
        if not isinstance(location, Location):
            raise MissingLocationError("Nearby hospital lookup requires a Location.")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise HospitalError("limit must be a positive integer.")
        catalog = (
            ("MOCK-H001", "Mock General Hospital", Location(0.01, 0.01)),
            ("MOCK-H002", "Mock City Hospital", Location(0.02, 0.02)),
            ("MOCK-H003", "Mock Medical Center", Location(0.03, 0.03)),
        )
        hospitals = [Hospital(identifier, name, "Fictional demo address", point.latitude,
                              point.longitude, geographic_distance_km(location, point))
                     for identifier, name, point in catalog]
        return sorted(hospitals, key=lambda h: (h.distance_km, h.hospital_id))[:limit]
