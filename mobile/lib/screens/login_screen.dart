import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../widgets/care_widgets.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final identity = TextEditingController();
  late final TextEditingController server;
  @override
  void initState() {
    super.initState();
    server = TextEditingController(text: context.read<AuthProvider>().url);
  }

  @override
  void dispose() {
    identity.dispose();
    server.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    return Scaffold(
      body: SafeArea(
        child: PageBody(
          children: [
            const SizedBox(height: 32),
            const Icon(Icons.health_and_safety_outlined, size: 64),
            const SizedBox(height: 16),
            Text(
              'ELDERCARE AI',
              style: Theme.of(context).textTheme.headlineLarge,
            ),
            const Text('Smart Elderly Care & Fall Response'),
            const SizedBox(height: 28),
            const Notice(
              'DEMO SIGN-IN • This backend has no accounts or password authentication. Your username identifies acknowledgements only. It does not protect API access.',
            ),
            InfoCard(
              'Caregiver login',
              children: [
                TextField(
                  controller: identity,
                  maxLength: 160,
                  autofillHints: const [AutofillHints.username],
                  decoration: const InputDecoration(
                    labelText: 'Email / Username',
                  ),
                  textInputAction: TextInputAction.next,
                ),
                const SizedBox(height: 16),
                const TextField(
                  enabled: false,
                  obscureText: true,
                  decoration: InputDecoration(
                    labelText: 'Password',
                    hintText: 'Not used in demo mode',
                  ),
                ),
                TextButton(
                  onPressed: () => showDialog<void>(
                    context: context,
                    builder: (context) => AlertDialog(
                      title: const Text('Password recovery unavailable'),
                      content: const Text(
                        'There is no account or password service in this backend. Demo sign-in only needs a caregiver username.',
                      ),
                      actions: [
                        TextButton(
                          onPressed: () => Navigator.pop(context),
                          child: const Text('OK'),
                        ),
                      ],
                    ),
                  ),
                  child: const Text('Forgot Password'),
                ),
                TextField(
                  controller: server,
                  keyboardType: TextInputType.url,
                  autocorrect: false,
                  decoration: const InputDecoration(
                    labelText: 'FastAPI server address',
                  ),
                ),
                const SizedBox(height: 20),
                if (auth.error != null) Notice(auth.error!, urgent: true),
                FilledButton(
                  onPressed: auth.busy
                      ? null
                      : () => auth.login(identity.text, server.text),
                  child: Text(auth.busy ? 'SAVING…' : 'LOGIN · DEMO MODE'),
                ),
              ],
            ),
            const Text(
              'Keep the app open to receive polling alerts. Hospital responses in this prototype are mock records.',
            ),
          ],
        ),
      ),
    );
  }
}
