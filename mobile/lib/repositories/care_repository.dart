import '../models/contracts.dart';
import '../services/api_service.dart';

class CareRepository {
  final ApiService api;
  CareRepository(this.api);
  String path(String id) => '/api/falls/${Uri.encodeComponent(id)}';
  Future<Health> health() async =>
      Health.fromJson(await api.request('/api/health') as Json);
  Future<MonitoringStatus> monitoring() async => MonitoringStatus.fromJson(
        await api.request('/api/system/status') as Json,
      );
  Future<List<FallEvent>> events() async =>
      (await api.request('/api/falls') as List)
          .map((j) => FallEvent.fromJson(j as Json))
          .toList();
  Future<void> acknowledge(String id, String caregiver) => api.request(
        '${path(id)}/acknowledge',
        method: 'POST',
        body: {'caregiver_id': caregiver},
      );
  Future<void> hospitals(String id) => api.request('${path(id)}/hospitals');
  Future<void> select(String id, String hospital, String caregiver) =>
      api.request(
        '${path(id)}/hospital',
        method: 'POST',
        body: {'hospital_id': hospital, 'caregiver_id': caregiver},
      );
  Future<void> record(String id) =>
      api.request('${path(id)}/emergency-response', method: 'POST');
  Future<void> demo() => api.request('/api/demo/fall', method: 'POST');
  Future<void> rearm() =>
      api.request('/api/system/camera/reset', method: 'POST');
}
