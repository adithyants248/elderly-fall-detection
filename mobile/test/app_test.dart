import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:eldercare_ai/main.dart';
import 'package:eldercare_ai/navigation/care_shell.dart';
import 'package:eldercare_ai/providers/auth_provider.dart';
import 'package:eldercare_ai/providers/care_providers.dart';
import 'package:eldercare_ai/repositories/care_repository.dart';
import 'package:eldercare_ai/services/api_service.dart';

import 'support.dart';

Future<void> tapText(WidgetTester tester, String text) async {
  final target = find.text(text).last;
  if (find.text(text).evaluate().isEmpty) {
    final scrollable = find
        .descendant(
            of: find.byType(ListView).last,
            matching: find.byType(Scrollable))
        .first;
    tester.state<ScrollableState>(scrollable).position.jumpTo(0);
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text(text), 180,
        scrollable: scrollable);
  }
  await tester.ensureVisible(target);
  await tester.pumpAndSettle();
  await tester.tap(target);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('splash, demo login validation and password explanation', (
    tester,
  ) async {
    final auth = AuthProvider(MemoryStore());
    await tester.pumpWidget(ElderCareApp(auth: auth));
    expect(find.byType(SplashScreen), findsOneWidget);
    await auth.restore();
    await tester.pumpAndSettle();
    await tapText(tester, 'LOGIN · DEMO MODE');
    expect(find.textContaining('Enter a caregiver username'), findsOneWidget);
    await tapText(tester, 'Forgot Password');
    expect(find.text('Password recovery unavailable'), findsOneWidget);
  });

  for (final width in [320.0, 412.0, 800.0]) {
    testWidgets('responsive navigation and complete response flow at $width', (
      tester,
    ) async {
      tester.view.physicalSize = Size(width, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final auth = AuthProvider(MemoryStore());
      await auth.restore();
      await auth.login('test-caregiver', 'http://localhost');
      final backend = BackendFixture();
      final session = CareSession(
        CareRepository(ApiService(auth.url, client: backend.client)),
      );
      await tester.pumpWidget(
        ChangeNotifierProvider.value(
          value: auth,
          child: MaterialApp(
            theme: ThemeData(useMaterial3: true),
            home: Consumer<AuthProvider>(
              builder: (context, value, child) => value.caregiver == null
                  ? const Text('Logged out')
                  : CareShell(session: session),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('FALL DETECTED · 1 to review'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.byIcon(Icons.monitor_heart_outlined).last);
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(find.text('Camera & AI'), 180,
          scrollable: find
              .descendant(
                  of: find.byType(ListView).last,
                  matching: find.byType(Scrollable))
              .first);
      expect(find.text('Camera & AI'), findsOneWidget);
      await tester.tap(find.byIcon(Icons.notifications_outlined));
      await tester.pumpAndSettle();
      await tapText(tester, 'VIEW ALERT');
      expect(find.text('Fall details'), findsOneWidget);
      await tapText(tester, 'ACKNOWLEDGE');
      await tapText(tester, 'ACKNOWLEDGE');
      expect(backend.status, 'ACKNOWLEDGED');
      await tapText(tester, 'REQUEST EMERGENCY ASSISTANCE');
      await tapText(tester, 'LOAD MOCK HOSPITALS');
      await tapText(tester, 'SELECT HOSPITAL');
      await tapText(tester, 'SELECT');
      await tapText(tester, 'SEND MOCK EMERGENCY REQUEST');
      await tapText(tester, 'CANCEL');
      expect(backend.recordCalls, 0);
      await tapText(tester, 'SEND MOCK EMERGENCY REQUEST');
      await tapText(tester, 'SEND REQUEST');
      expect(backend.recordCalls, 1);
      await tester.scrollUntilVisible(find.text('Ambulance status'), 180,
          scrollable: find
              .descendant(
                  of: find.byType(ListView).last,
                  matching: find.byType(Scrollable))
              .first);
      await tester.pumpAndSettle();
      expect(
        find.textContaining(
          'Unavailable. This backend does not provide ambulance',
        ),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
      backend.additionalAlert = true;
      await session.refresh();
      await tester.pumpAndSettle();
      expect(find.text('Other fall alerts · 1 to review'), findsOneWidget);
      backend.offline = true;
      await session.refresh();
      await tester.pumpAndSettle();
      expect(
        find.textContaining('Backend unavailable. Displayed data'),
        findsOneWidget,
      );
      await tester.pageBack();
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.person_outline).last);
      await tester.pumpAndSettle();
      await tapText(tester, 'LOGOUT');
      await tapText(tester, 'LOGOUT');
      expect(auth.caregiver, isNull);
      await tester.pumpWidget(const SizedBox());
    });
  }
}
