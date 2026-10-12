import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  final String message;
  final int? status;
  const ApiException(this.message, [this.status]);
  @override
  String toString() => message;
}

class ApiService {
  final String baseUrl;
  final http.Client client;
  final Duration timeout;
  ApiService(
    String url, {
    http.Client? client,
    this.timeout = const Duration(seconds: 8),
  })  : baseUrl = validateUrl(url),
        client = client ?? http.Client();
  static String validateUrl(String value) {
    final uri = Uri.tryParse(value.trim());
    if (uri == null ||
        !['http', 'https'].contains(uri.scheme) ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        (uri.path.isNotEmpty && uri.path != '/')) {
      throw const ApiException(
        'Enter a server address such as http://10.0.2.2:8000.',
      );
    }
    return value.trim().replaceFirst(RegExp(r'/+$'), '');
  }

  Future<dynamic> request(
    String path, {
    String method = 'GET',
    Map<String, dynamic>? body,
  }) async {
    try {
      final uri = Uri.parse('$baseUrl$path');
      final response = await (method == 'GET'
              ? client.get(uri)
              : client.post(
                  uri,
                  headers: {'Content-Type': 'application/json'},
                  body: body == null ? null : jsonEncode(body),
                ))
          .timeout(timeout);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final message = switch (response.statusCode) {
          400 || 422 => 'Please check your input and try again.',
          401 =>
            'The server requires authentication. This client supports demo identity only.',
          403 => 'The server did not allow this action.',
          404 =>
            'This event or feature is no longer available. Refresh and try again.',
          409 =>
            'This event changed or was already handled. Refresh before trying again.',
          _ => 'The server could not complete the request. Please try again.',
        };
        throw ApiException(message, response.statusCode);
      }
      return jsonDecode(response.body);
    } on TimeoutException {
      throw const ApiException(
        'The server took too long. Refresh to check whether your action completed before retrying.',
      );
    } on http.ClientException {
      throw const ApiException(
        'Backend unavailable. Check the server address and Wi-Fi connection.',
      );
    } on FormatException {
      throw const ApiException('The server returned an unreadable response.');
    }
  }

  void close() => client.close();
}
