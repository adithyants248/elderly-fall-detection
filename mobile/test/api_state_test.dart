import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:eldercare_ai/providers/auth_provider.dart';
import 'package:eldercare_ai/providers/care_providers.dart';
import 'package:eldercare_ai/repositories/care_repository.dart';
import 'package:eldercare_ai/services/api_service.dart';

import 'support.dart';

void main() {
  test('demo session validation, restore and logout', () async {
    final store = MemoryStore();
    final auth = AuthProvider(store);
    await auth.restore();
    await auth.login('', 'http://10.0.2.2:8000');
    expect(auth.caregiver, isNull);
    await auth.login('test-caregiver', 'http://10.0.2.2:8000');
    expect(auth.caregiver!.id, 'test-caregiver');
    final restored = AuthProvider(store);
    await restored.restore();
    expect(restored.caregiver!.id, 'test-caregiver');
    await restored.logout();
    expect(store.values.containsKey('caregiver'), isFalse);
  });
  test(
    'actual contract workflow, deduplication and offline retention',
    () async {
      final backend = BackendFixture();
      final repo = CareRepository(
        ApiService('http://localhost:8000', client: backend.client),
      );
      final session = CareSession(repo);
      addTearDown(session.dispose);
      await session.refresh();
      await session.refresh();
      expect(session.alerts.events, hasLength(1));
      expect(session.alerts.events.single.createdAt.year, 2026);
      expect(session.alerts.events.single.sourceSeconds, 8);
      expect(session.monitoring.status!.state, 'Unavailable');
      await repo.acknowledge('DEMO-test', 'test-caregiver');
      await repo.hospitals('DEMO-test');
      await repo.select('DEMO-test', 'MOCK-H001', 'test-caregiver');
      await session.emergency.perform(
        () => repo.record('DEMO-test'),
        session.refresh,
      );
      expect(
        session.alerts.events.single.response!.status,
        'RESPONSE_RECORDED',
      );
      backend.offline = true;
      await session.refresh();
      expect(session.monitoring.connected, isFalse);
      expect(session.alerts.events, hasLength(1));
      backend.offline = false;
      await session.refresh();
      expect(session.monitoring.connected, isTrue);
    },
  );
  test('double taps do not duplicate in-flight actions', () async {
    final action = EmergencyProvider();
    final wait = Completer<void>();
    var calls = 0;
    final first = action.perform(() {
      calls++;
      return wait.future;
    }, () async {});
    await action.perform(() async {
      calls++;
    }, () async {});
    expect(calls, 1);
    wait.complete();
    await first;
    expect(action.busy, isFalse);
    action.dispose();
  });
  test(
    'empty backend is not an invented safe state or patient assignment',
    () async {
      final backend = BackendFixture()..empty = true;
      final session = CareSession(
        CareRepository(ApiService('http://localhost', client: backend.client)),
      );
      addTearDown(session.dispose);
      await session.refresh();
      expect(session.alerts.events, isEmpty);
      expect(session.monitoring.status!.state, 'Unavailable');
      expect(session.monitoring.status!.probability, isNull);
    },
  );
  for (final code in [400, 401, 403, 404, 409, 422, 500]) {
    test('HTTP $code is a friendly error', () async {
      final api = ApiService(
        'http://localhost',
        client: MockClient(
          (_) async => http.Response('secret stack trace', code),
        ),
      );
      addTearDown(api.close);
      await expectLater(
        api.request('/api/falls'),
        throwsA(
          isA<ApiException>().having((e) => e.status, 'status', code).having(
                (e) => e.message,
                'message',
                isNot(contains('stack trace')),
              ),
        ),
      );
    });
  }
  test('timeout and malformed data', () async {
    final api = ApiService(
      'http://localhost',
      timeout: const Duration(milliseconds: 1),
      client: MockClient((_) async {
        await Future<void>.delayed(const Duration(milliseconds: 20));
        return http.Response('{}', 200);
      }),
    );
    await expectLater(api.request('/'), throwsA(isA<ApiException>()));
    api.close();
    final malformed = ApiService(
      'http://localhost',
      client: MockClient((_) async => http.Response('<html>', 200)),
    );
    await expectLater(malformed.request('/'), throwsA(isA<ApiException>()));
    malformed.close();
  });
  test('server address rejects credentials and non-HTTP schemes', () {
    for (final url in [
      'file:///tmp',
      'http://user:password@host',
      'http://host/api',
      'bad',
    ]) {
      expect(() => ApiService.validateUrl(url), throwsA(isA<ApiException>()));
    }
  });
}
