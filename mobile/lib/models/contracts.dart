typedef Json = Map<String, dynamic>;

class Caregiver {
  final String id;
  const Caregiver(this.id);
}

class Health {
  final bool demoEnabled;
  final String hospitalData;
  Health.fromJson(Json j)
      : demoEnabled = j['demo_enabled'] == true,
        hospitalData = j['hospital_data'] as String;
}

class MonitoringStatus {
  final String camera, ai, message;
  final int frames, pending, latched;
  final bool resetRequested;
  final DateTime? lastFrame;
  final Json diagnostics;
  MonitoringStatus.fromJson(Json j)
      : camera = j['camera_status'] as String,
        ai = j['ai_status'] as String,
        message = j['message'] as String,
        frames = j['frames_processed'] as int,
        pending = j['pending_events'] as int,
        latched = j['latched_events'] as int,
        resetRequested = j['reset_requested'] == true,
        lastFrame = DateTime.tryParse(j['last_frame_at'] ?? ''),
        diagnostics = (j['diagnostics'] as Json?) ?? {};
  String get state => diagnostics['state'] as String? ?? 'Unavailable';
  double? get probability =>
      (diagnostics['fall_probability'] as num?)?.toDouble();
  double? get threshold => (diagnostics['fall_threshold'] as num?)?.toDouble();
  bool get stale =>
      camera == 'running' &&
      (lastFrame == null ||
          DateTime.now().difference(lastFrame!).inSeconds > 10);
}

class Hospital {
  final String id, name, address;
  Hospital.fromJson(Json j)
      : id = j['hospital_id'] as String,
        name = j['name'] as String,
        address = j['address'] as String;
}

class EmergencyRequest {
  final String id, status;
  final String? hospitalName;
  final List<Hospital> hospitals;
  final DateTime? selectedAt, recordedAt;
  EmergencyRequest.fromJson(Json j)
      : id = j['response_id'] as String,
        status = j['status'] as String,
        hospitalName = j['selected_hospital_name'] as String?,
        hospitals = (j['hospitals'] as List)
            .map((h) => Hospital.fromJson(h as Json))
            .toList(),
        selectedAt = DateTime.tryParse(j['selected_at'] ?? ''),
        recordedAt = DateTime.tryParse(j['recorded_at'] ?? '');
}

class FallEvent {
  final String id, personId, status;
  final double sourceSeconds;
  final double? probability;
  final DateTime createdAt;
  final DateTime? acknowledgedAt;
  final String? acknowledgedBy;
  final bool simulated;
  final EmergencyRequest? response;
  FallEvent.fromJson(Json j)
      : id = j['event_id'] as String,
        personId = j['person_id'] as String,
        status = j['status'] as String,
        sourceSeconds = (j['timestamp'] as num).toDouble(),
        probability = (j['detection_probability'] as num?)?.toDouble(),
        createdAt = DateTime.parse(j['created_at'] as String),
        acknowledgedAt = DateTime.tryParse(j['acknowledged_at'] ?? ''),
        acknowledgedBy = j['acknowledged_by'] as String?,
        simulated = j['simulated'] == true,
        response = j['emergency_response'] == null
            ? null
            : EmergencyRequest.fromJson(j['emergency_response'] as Json);
  bool get acknowledged => status == 'ACKNOWLEDGED';
}
