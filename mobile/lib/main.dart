import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'providers/auth_provider.dart';
import 'screens/login_screen.dart';
import 'navigation/care_shell.dart';
import 'services/authentication_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(ElderCareApp(auth: AuthProvider(SecureSessionStore())..restore()));
}

class ElderCareApp extends StatelessWidget {
  final AuthProvider auth;
  const ElderCareApp({super.key, required this.auth});
  @override
  Widget build(BuildContext context) => ChangeNotifierProvider.value(
        value: auth,
        child: Consumer<AuthProvider>(
          builder: (context, auth, _) => MaterialApp(
            title: 'ElderCare AI',
            debugShowCheckedModeBanner: false,
            themeMode: auth.dark ? ThemeMode.dark : ThemeMode.light,
            theme: theme(Brightness.light),
            darkTheme: theme(Brightness.dark),
            home: !auth.ready
                ? const SplashScreen()
                : auth.caregiver == null
                    ? const LoginScreen()
                    : CareShell(
                        key: ValueKey('${auth.url}/${auth.caregiver!.id}')),
          ),
        ),
      );
  ThemeData theme(Brightness brightness) => ThemeData(
        useMaterial3: true,
        brightness: brightness,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xff00858b),
          brightness: brightness,
          primary: brightness == Brightness.light
              ? const Color(0xff007d84)
              : const Color(0xff80d4d5),
          onPrimary: brightness == Brightness.light
              ? Colors.white
              : const Color(0xff00383d),
        ),
        scaffoldBackgroundColor: brightness == Brightness.light
            ? const Color(0xfff3f9fa)
            : const Color(0xff10252d),
        appBarTheme: AppBarTheme(
            centerTitle: false,
            elevation: 0,
            scrolledUnderElevation: 0,
            backgroundColor: brightness == Brightness.light
                ? const Color(0xfff3f9fa)
                : const Color(0xff10252d)),
        cardTheme: CardThemeData(
          elevation: 1,
          shadowColor: const Color(0x181d5363),
          color: brightness == Brightness.light
              ? Colors.white
              : const Color(0xff19343e),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(17),
            side: BorderSide(
                color: brightness == Brightness.light
                    ? const Color(0xffe1edf0)
                    : const Color(0xff36505a)),
          ),
        ),
        navigationBarTheme: NavigationBarThemeData(
          elevation: 0,
          height: 72,
          backgroundColor: brightness == Brightness.light
              ? Colors.white
              : const Color(0xff19343e),
          indicatorColor: brightness == Brightness.light
              ? const Color(0xffdcf1f1)
              : const Color(0xff26515a),
          labelTextStyle: WidgetStateProperty.resolveWith((states) => TextStyle(
              fontSize: 11,
              fontWeight: states.contains(WidgetState.selected)
                  ? FontWeight.w700
                  : FontWeight.w500)),
        ),
        inputDecorationTheme: const InputDecorationTheme(
          border: OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(12))),
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            minimumSize: const Size(48, 52),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
          ),
        ),
      );
}

class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});
  @override
  Widget build(BuildContext context) => const Scaffold(
        body: SafeArea(
          child: Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.health_and_safety_outlined, size: 72),
                  SizedBox(height: 20),
                  Text(
                    'ELDERCARE AI',
                    style: TextStyle(fontSize: 30, fontWeight: FontWeight.bold),
                  ),
                  SizedBox(height: 12),
                  Text(
                    'Smart Elderly Care & Fall Response',
                    textAlign: TextAlign.center,
                  ),
                  SizedBox(height: 32),
                  CircularProgressIndicator(),
                ],
              ),
            ),
          ),
        ),
      );
}
