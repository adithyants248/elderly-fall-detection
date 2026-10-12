import 'dart:convert';

import 'package:eldercare_ai/services/authentication_service.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class MemoryStore implements SessionStore {
  final values = <String, String>{};
  @override
  Future<String?> read(String key) async => values[key];
  @override
  Future<void> write(String key, String value) async {
    values[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    values.remove(key);
  }
}

// Test-only data: never imported into the application.
class BackendFixture {
  bool offline = false;
  bool empty = false;
  bool additionalAlert = false;
  int recordCalls = 0;
  Map<String, dynamic>? response;
  String status = 'ALERT_SENT';
  Map<String, dynamic> get event => {
        'event_id': 'DEMO-test',
        'person_id': 'SIMULATED-PERSON',
        'timestamp': 8.0,
        'detection_probability': 0.87,
        'status': status,
        'created_at': '2026-09-21T10:00:00Z',
        'acknowledged_at':
            status == 'ACKNOWLEDGED' ? '2026-09-21T10:01:00Z' : null,
        'acknowledged_by': status == 'ACKNOWLEDGED' ? 'test-caregiver' : null,
        'simulated': true,
        'emergency_response': response,
      };
  late final client = MockClient((request) async {
    if (offline) throw http.ClientException('offline');
    final path = request.url.path;
    Object result;
    if (path.endsWith('/health')) {
      result = {'status': 'ok', 'demo_enabled': true, 'hospital_data': 'mock'};
    } else if (path.endsWith('/system/status')) {
      result = {
        'camera_enabled': false,
        'camera_status': 'disabled',
        'ai_status': 'disabled',
        'message': 'Camera mode disabled.',
        'frames_processed': 0,
        'last_frame_at': null,
        'pending_events': 0,
        'latched_events': 0,
        'reset_requested': false,
        'diagnostics': {},
      };
    } else if (path.endsWith('/acknowledge')) {
      status = 'ACKNOWLEDGED';
      result = event;
    } else if (path.endsWith('/hospitals')) {
      if (status != 'ACKNOWLEDGED') return http.Response('{}', 409);
      response ??= {
        'response_id': 'RESP-test',
        'event_id': 'DEMO-test',
        'status': 'HOSPITALS_AVAILABLE',
        'selected_hospital_name': null,
        'selected_at': null,
        'recorded_at': null,
        'hospitals': [
          {
            'hospital_id': 'MOCK-H001',
            'name': 'Mock General Hospital',
            'address': 'Fictional demo address',
          },
        ],
      };
      result = response!;
    } else if (path.endsWith('/hospital')) {
      response!['status'] = 'HOSPITAL_SELECTED';
      response!['selected_hospital_name'] = 'Mock General Hospital';
      response!['selected_at'] = '2026-09-21T10:02:00Z';
      result = response!;
    } else if (path.endsWith('/emergency-response')) {
      recordCalls++;
      response!['status'] = 'RESPONSE_RECORDED';
      response!['recorded_at'] = '2026-09-21T10:03:00Z';
      result = {'mock': true, 'response': response};
    } else if (path == '/api/falls') {
      result = empty
          ? []
          : [
              event,
              if (additionalAlert)
                {
                  ...event,
                  'event_id': 'DEMO-second',
                  'status': 'ALERT_SENT',
                  'acknowledged_at': null,
                  'acknowledged_by': null,
                  'emergency_response': null
                },
            ];
    } else {
      return http.Response('{}', 404);
    }
    return http.Response(jsonEncode(result), 200);
  });
}
