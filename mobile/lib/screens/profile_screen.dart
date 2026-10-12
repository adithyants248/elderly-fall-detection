import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../providers/care_providers.dart';
import '../widgets/care_widgets.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});
  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final m = context.watch<MonitoringProvider>();
    final action = context.watch<EmergencyProvider>();
    final session = context.read<CareSession>();
    return PageBody(
      children: [
        Text(
          'Profile & settings',
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 20),
        Row(children: [
          CircleAvatar(
              radius: 30,
              backgroundColor: Theme.of(context).colorScheme.primaryContainer,
              child: const Icon(Icons.person, size: 38)),
          const SizedBox(width: 16),
          Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Text(auth.caregiver!.id,
                    style: Theme.of(context)
                        .textTheme
                        .titleMedium
                        ?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 5),
                const Text('Caregiver (Demo)'),
                const SizedBox(height: 5),
                Text(m.connected ? 'Connected' : 'Backend unavailable'),
              ])),
        ]),
        const SizedBox(height: 24),
        InfoCard('Backend connection', icon: Icons.cloud_outlined, children: [
          Fact('Status', m.connected ? 'Connected' : 'Unavailable / retrying'),
          Fact('Last update', timeLabel(m.updatedAt)),
        ]),
        InfoCard(
          'Caregiver',
          icon: Icons.person_outline,
          children: [
            Fact('Demo identity', auth.caregiver!.id),
            const Text(
              'Verified name, email, phone and patient assignment are not supplied by this backend.',
            ),
            TextButton(
              onPressed: action.busy
                  ? null
                  : () async {
                      final id = await editValue(
                        context,
                        'Edit demo identity',
                        auth.caregiver!.id,
                      );
                      if (id != null) await auth.login(id, auth.url);
                    },
              child: const Text('EDIT DEMO PROFILE'),
            ),
            if (auth.error != null) Notice(auth.error!, urgent: true),
            OutlinedButton(
              onPressed: action.busy
                  ? null
                  : () async {
                      if (await confirm(
                        context,
                        'Log out?',
                        'Remove this demo identity from secure storage?',
                        action: 'LOGOUT',
                      )) {
                        await auth.logout();
                      }
                    },
              child: const Text('LOGOUT'),
            ),
          ],
        ),
        InfoCard(
          'Settings',
          icon: Icons.settings_outlined,
          children: [
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('App Theme'),
              subtitle: const Text('Dark mode'),
              value: auth.dark,
              onChanged: auth.setDark,
            ),
            Fact('Server address', auth.url),
            TextButton(
              onPressed: action.busy
                  ? null
                  : () async {
                      final url = await editValue(
                        context,
                        'Change API server',
                        auth.url,
                        server: true,
                      );
                      if (url != null) {
                        await auth.login(auth.caregiver!.id, url);
                      }
                    },
              child: const Text('CHANGE SERVER'),
            ),
            const ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(Icons.notifications_outlined),
                title: Text('Notifications'),
                subtitle: Text('Foreground alerts only')),
            const Text(
              'Alerts refresh while the app is open. Background push notifications are not available. Polling resumes when you return.',
            ),
          ],
        ),
        if (m.health?.demoEnabled == true)
          InfoCard(
            'Development / demo',
            icon: Icons.science_outlined,
            children: [
              const Notice(
                'DEMO MODE · Injects a clearly marked simulated fall into the existing backend. It does not run or modify the AI.',
              ),
              FilledButton.tonal(
                onPressed: !m.connected || action.busy
                    ? null
                    : () async {
                        if (!await confirm(
                          context,
                          'Simulate demo fall?',
                          'Create a simulated event in the connected backend?',
                          action: 'SIMULATE',
                        )) {
                          return;
                        }
                        await action.perform(
                          session.repository.demo,
                          session.refresh,
                          message:
                              'Simulated fall created. Open Alerts to review it.',
                        );
                      },
                child: const Text('SIMULATE DEMO FALL'),
              ),
              if (action.error != null) Notice(action.error!, urgent: true),
              if (action.success != null) Notice(action.success!),
            ],
          ),
        const InfoCard(
          'About ElderCare AI',
          icon: Icons.health_and_safety_outlined,
          children: [
            Text(
              'Smart Elderly Care & Fall Response\nVersion 1.0.0\nFinal-year project caregiver application.',
            ),
            SizedBox(height: 12),
            Text(
              'Live AI events and simulated events are labelled separately. All hospital response handling currently uses the backend mock service.',
            ),
          ],
        ),
      ],
    );
  }
}
