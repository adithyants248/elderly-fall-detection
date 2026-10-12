import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/contracts.dart';
import '../repositories/care_repository.dart';
import '../services/api_service.dart';

String friendlyError(Object e) => e is ApiException
    ? e.message
    : 'Could not read the server response. Please refresh.';

class MonitoringProvider extends ChangeNotifier {
  MonitoringStatus? status;
  Health? health;
  bool connected = false;
  DateTime? updatedAt;
  String? error;
  void update(MonitoringStatus value, Health capabilities) {
    status = value;
    health = capabilities;
    connected = true;
    updatedAt = DateTime.now();
    error = null;
    notifyListeners();
  }

  void fail(Object e) {
    connected = false;
    error = friendlyError(e);
    notifyListeners();
  }
}

class AlertProvider extends ChangeNotifier {
  List<FallEvent> events = [];
  List<FallEvent> get active => events.where((e) => !e.acknowledged).toList();
  FallEvent? find(String id) {
    for (final event in events) {
      if (event.id == id) return event;
    }
    return null;
  }

  void update(List<FallEvent> value) {
    // IDs are authoritative; never create duplicate alert cards on repeated polls.
    events = {for (final e in value) e.id: e}.values.toList()
      ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
    notifyListeners();
  }
}

class EmergencyProvider extends ChangeNotifier {
  bool busy = false;
  String? error, success;
  bool _disposed = false;
  Future<void> perform(
    Future<void> Function() action,
    Future<void> Function() refresh, {
    String message = 'Action completed.',
  }) async {
    if (busy) return;
    busy = true;
    error = null;
    success = null;
    notifyListeners();
    try {
      await action();
      success = message;
    } catch (e) {
      error = friendlyError(e);
    }
    // Reconcile even on timeout/conflict; a server write may already have completed.
    await refresh();
    busy = false;
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

class CareSession {
  final CareRepository repository;
  final MonitoringProvider monitoring = MonitoringProvider();
  final AlertProvider alerts = AlertProvider();
  final EmergencyProvider emergency = EmergencyProvider();
  Timer? _timer;
  Future<void>? _inFlight;
  bool _disposed = false, _paused = false;
  int _failures = 0;
  CareSession(this.repository);
  Future<void> refresh() {
    if (_disposed) return Future.value();
    return _inFlight ??= _load().whenComplete(() => _inFlight = null);
  }

  Future<void> _load() async {
    _timer?.cancel();
    try {
      final snapshot = await Future.wait<Object>([
        repository.monitoring(),
        repository.events(),
        repository.health(),
      ]);
      if (_disposed) return;
      monitoring.update(snapshot[0] as MonitoringStatus, snapshot[2] as Health);
      alerts.update(snapshot[1] as List<FallEvent>);
      _failures = 0;
    } catch (e) {
      if (!_disposed) monitoring.fail(e);
      _failures++;
    } finally {
      if (!_disposed && !_paused) {
        final seconds = _failures == 0
            ? 3
            : (3 * (1 << _failures.clamp(0, 3))).clamp(3, 24);
        _timer = Timer(Duration(seconds: seconds), refresh);
      }
    }
  }

  void pause() {
    _paused = true;
    _timer?.cancel();
  }

  void resume() {
    _paused = false;
    refresh();
  }

  void dispose() {
    _disposed = true;
    _timer?.cancel();
    repository.api.close();
    monitoring.dispose();
    alerts.dispose();
    emergency.dispose();
  }
}
