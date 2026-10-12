import 'dart:io';
import 'package:eldercare_ai/repositories/care_repository.dart';
import 'package:eldercare_ai/services/api_service.dart';

// Run only against a disposable camera-disabled server with demo injection enabled.
Future<void> main(List<String> args) async {
  if (args.length != 1) {
    throw ArgumentError('Supply the disposable server URL.');
  }
  final api = ApiService(args.single);
  final repo = CareRepository(api);
  void check(bool result, String message) {
    if (!result) throw StateError(message);
  }

  try {
    check((await repo.health()).demoEnabled, 'Demo must be enabled');
    check(
      (await repo.monitoring()).camera == 'disabled',
      'Use a camera-disabled disposable server',
    );
    final before = (await repo.events()).map((e) => e.id).toSet();
    await repo.demo();
    final event = (await repo.events()).singleWhere(
      (e) => !before.contains(e.id),
    );
    check(
      event.simulated && !event.acknowledged,
      'Expected new simulated alert',
    );
    await repo.acknowledge(event.id, 'mobile-smoke');
    await repo.acknowledge(event.id, 'mobile-smoke');
    await repo.hospitals(event.id);
    final offered = (await repo.events()).singleWhere((e) => e.id == event.id);
    await repo.select(
      event.id,
      offered.response!.hospitals.first.id,
      'mobile-smoke',
    );
    await repo.record(event.id);
    await repo.record(event.id);
    final completed = (await repo.events()).singleWhere(
      (e) => e.id == event.id,
    );
    check(
      completed.response!.status == 'RESPONSE_RECORDED',
      'Response not recorded',
    );
    stdout.writeln(
      'PASS: Dart client → FastAPI demo → acknowledgement → hospital → idempotent mock response',
    );
  } finally {
    api.close();
  }
}
