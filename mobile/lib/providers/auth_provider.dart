import 'package:flutter/material.dart';

import '../models/contracts.dart';
import '../services/api_service.dart';
import '../services/authentication_service.dart';

class AuthProvider extends ChangeNotifier {
  final SessionStore store;
  Caregiver? caregiver;
  bool ready = false, busy = false, dark = false;
  String? error;
  String url = const String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );
  AuthProvider(this.store);
  Future<void> restore() async {
    try {
      url = ApiService.validateUrl(await store.read('url') ?? url);
      dark = await store.read('dark') == 'true';
      final id = await store.read('caregiver');
      if (id != null && id.isNotEmpty) caregiver = Caregiver(id);
    } catch (_) {
      error = 'Could not restore the secure session. Please sign in again.';
    }
    ready = true;
    notifyListeners();
  }

  Future<void> login(String identity, String server) async {
    if (busy) return;
    busy = true;
    error = null;
    notifyListeners();
    try {
      final id = identity.trim();
      if (id.isEmpty || id.length > 160) {
        throw const ApiException(
          'Enter a caregiver username of 1–160 characters.',
        );
      }
      final validated = ApiService.validateUrl(server);
      await store.write('url', validated);
      await store.write('caregiver', id);
      url = validated;
      caregiver = Caregiver(id);
    } on ApiException catch (e) {
      error = e.message;
    } catch (_) {
      error = 'Unable to save your secure demo session. Please retry.';
    }
    busy = false;
    notifyListeners();
  }

  Future<void> logout() async {
    try {
      await store.delete('caregiver');
      caregiver = null;
      error = null;
    } catch (_) {
      error = 'Unable to remove the saved session. Please retry logout.';
    }
    notifyListeners();
  }

  Future<void> setDark(bool value) async {
    try {
      await store.write('dark', '$value');
      dark = value;
      error = null;
    } catch (_) {
      error = 'Unable to save this setting.';
    }
    notifyListeners();
  }
}
