"""Complete mock workflow; no device, ML, or external service required."""
from src.caregiver.models import FallEvent
from src.caregiver.notifier import MockCaregiverNotifier
from src.caregiver.repository import InMemoryFallEventRepository
from src.caregiver.service import CaregiverResponseService
from src.hospital.models import Location
from src.hospital.repository import InMemoryEmergencyResponseRepository
from src.hospital.hospital_service import MockHospitalSearchService
from src.hospital.emergency_service import MockEmergencyService
from src.hospital.service import EmergencyResponseService


def main():
    print('HOSPITAL / EMERGENCY RESPONSE DEMO (MOCK ONLY)')
    caregivers = InMemoryFallEventRepository()
    caregiver = CaregiverResponseService(caregivers, MockCaregiverNotifier())
    caregiver.handle_confirmed_fall(FallEvent('DEMO-FALL-001', 'demo-person', 8.0, 0.87))
    event = caregiver.acknowledge_event('DEMO-FALL-001', 'demo-caregiver')
    print('Caregiver status:', event.status.value)
    service = EmergencyResponseService(caregivers, InMemoryEmergencyResponseRepository(),
                                       MockHospitalSearchService(), MockEmergencyService())
    location = Location(0, 0)
    print(f'Mock coordinates: latitude={location.latitude}, longitude={location.longitude}')
    print('Starting emergency response...')
    response = service.start_response(event.event_id, location)
    print('Nearby MOCK hospitals (geographic distance, not routing distance):')
    hospitals = service.get_nearby_hospitals(response.response_id)
    for index, hospital in enumerate(hospitals, 1):
        print(f'{index}. {hospital.name} [{hospital.hospital_id}]\n   {hospital.address}\n   Distance: {hospital.distance_km:.2f} km')
    response = service.select_hospital(response.response_id, hospitals[1].hospital_id, 'demo-caregiver')
    print('Simulated caregiver selects:', response.selected_hospital_name)
    print('Selection status:', response.status.value)
    response = service.record_response(response.response_id)
    print('Final response status:', response.status.value)
    print('ACKNOWLEDGED -> HOSPITALS_AVAILABLE -> HOSPITAL_SELECTED -> RESPONSE_RECORDED')
    print('No hospital contacted, ambulance dispatched, or patient transfer initiated.')


if __name__ == '__main__':
    main()
