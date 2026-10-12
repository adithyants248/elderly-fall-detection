import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../providers/care_providers.dart';
import '../widgets/care_widgets.dart';

class HomeScreen extends StatelessWidget {
  final ValueChanged<int> onNavigate;
  const HomeScreen({super.key, required this.onNavigate});
  @override
  Widget build(BuildContext context) {
    final m = context.watch<MonitoringProvider>();
    final a = context.watch<AlertProvider>();
    final hour = DateTime.now().hour;
    final live = m.connected &&
        m.status?.camera == 'running' &&
        m.status?.stale == false;
    return PageBody(children: [
      Text(
          'Good ${hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : 'evening'},',
          style: Theme.of(context).textTheme.bodyLarge),
      const SizedBox(height: 4),
      Text(context.watch<AuthProvider>().caregiver!.id,
          style: Theme.of(context)
              .textTheme
              .headlineSmall
              ?.copyWith(fontWeight: FontWeight.w800)),
      const SizedBox(height: 18),
      if (m.error != null)
        Notice('${m.error!} Displayed data may be out of date.', urgent: true),
      Card(
          child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
        leading: CircleAvatar(
            backgroundColor: Theme.of(context).colorScheme.primaryContainer,
            child: const Icon(Icons.person_outline)),
        title: const Text('Elderly Person',
            style: TextStyle(fontWeight: FontWeight.w700)),
        subtitle: Text(live
            ? 'Monitoring active - identity unassigned'
            : 'Monitoring unavailable - identity unassigned'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => onNavigate(1),
      )),
      MonitoringHero(
          status: m.status,
          connected: m.connected,
          activeAlert: a.active.isNotEmpty),
      SummaryPair(
        first: SummaryTile(
            'Last checked',
            m.updatedAt == null
                ? 'Unavailable'
                : TimeOfDay.fromDateTime(m.updatedAt!.toLocal())
                    .format(context),
            icon: Icons.schedule),
        second: SummaryTile('System', m.connected ? 'Online' : 'Unavailable',
            icon: m.connected ? Icons.wifi : Icons.wifi_off),
      ),
      const SizedBox(height: 18),
      FilledButton.icon(
          onPressed: () => onNavigate(1),
          icon: const Icon(Icons.arrow_forward, size: 19),
          label: const Text('OPEN MONITORING')),
      const SizedBox(height: 18),
      InfoCard('Recent Alerts', icon: Icons.notifications_outlined, children: [
        if (a.events.isEmpty)
          const Padding(
              padding: EdgeInsets.symmetric(vertical: 10),
              child: Text('No recent alerts', textAlign: TextAlign.center))
        else ...[
          Text(
              a.active.isEmpty
                  ? 'All alerts acknowledged'
                  : '${a.active.length} alerts need your review',
              style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Text(a.events.first.simulated
              ? 'DEMO / SIMULATED FALL'
              : 'AI-GENERATED FALL EVENT'),
          Fact('Latest received', timeLabel(a.events.first.createdAt)),
          TextButton(
              onPressed: () => onNavigate(2), child: const Text('VIEW ALERTS')),
        ],
      ]),
      const Text(
          'Patient name and age are unavailable. Events identify the person using the backend person ID.',
          style: TextStyle(fontSize: 12)),
    ]);
  }
}

class MonitoringScreen extends StatelessWidget {
  const MonitoringScreen({super.key});
  @override
  Widget build(BuildContext context) {
    final m = context.watch<MonitoringProvider>();
    final s = m.status;
    final action = context.watch<EmergencyProvider>();
    final session = context.read<CareSession>();
    return PageBody(
      children: [
        Text('Monitoring', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 20),
        Center(
            child: StatusChip(
                m.connected && s?.camera == 'running' && s?.stale == false
                    ? 'LIVE MONITORING'
                    : 'MONITORING UNAVAILABLE')),
        const SizedBox(height: 16),
        MonitoringHero(
            status: s,
            connected: m.connected,
            activeAlert: context.watch<AlertProvider>().active.isNotEmpty),
        const Text(
            'Status visualization only. The backend does not provide a live camera stream.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 12)),
        const SizedBox(height: 16),
        SummaryTile(
            'Person observation',
            !m.connected || s?.camera != 'running' || s?.stale == true
                ? 'Unavailable'
                : s?.diagnostics['person_detected'] == 1
                    ? 'Person detected'
                    : s?.diagnostics['person_detected'] == 0
                        ? 'No person detected'
                        : 'Unavailable',
            icon: Icons.person_outline),
        const SizedBox(height: 16),
        if (m.error != null)
          Notice('${m.error!} Last snapshot is retained.', urgent: true),
        if (s?.stale == true)
          const Notice(
            'No completed camera frame in the last 10 seconds. Monitoring data is stale.',
            urgent: true,
          ),
        InfoCard(
          'Camera & AI',
          icon: Icons.videocam_outlined,
          children: [
            Fact('Camera', label(s?.camera ?? 'Unavailable')),
            Fact('AI', label(s?.ai ?? 'Unavailable')),
            Fact(
              'Verifier state (last snapshot)',
              label(s?.state ?? 'Unavailable'),
            ),
            Fact('Fall probability (not pose confidence)',
                percent(s?.probability)),
            Fact('Monitoring duration', 'Unavailable'),
            Fact('Last processed frame', timeLabel(s?.lastFrame)),
            Text(s?.message ?? 'Waiting for a backend response.'),
          ],
        ),
        ExpansionTile(
          title: const Text('Technical details'),
          children: [
            Fact(
                'GRU readiness',
                s?.diagnostics['temporal_ready'] == true
                    ? 'Ready'
                    : 'Waiting for temporal input'),
            Fact('Saved fall threshold', percent(s?.threshold)),
            Fact('Frames processed', '${s?.frames ?? 0}'),
            Fact('Pending delivery', '${s?.pending ?? 0}'),
            Fact('Latched episodes', '${s?.latched ?? 0}'),
            const Text(
              'The backend does not expose uptime. Diagnostics describe the most recently processed track.',
            ),
          ],
        ),
        const SizedBox(height: 16),
        if (s != null && s.latched > 0)
          FilledButton.tonal(
            onPressed:
                !m.connected || action.busy || s.pending > 0 || s.resetRequested
                    ? null
                    : () async {
                        if (!await confirm(
                          context,
                          'Rearm camera?',
                          'Check the person and acknowledge all camera alerts first. This starts a fresh monitoring episode.',
                        )) {
                          return;
                        }
                        await action.perform(
                          session.repository.rearm,
                          session.refresh,
                          message: 'Camera rearm requested.',
                        );
                      },
            child: Text(s.resetRequested ? 'REARM REQUESTED' : 'REARM CAMERA'),
          ),
        if (action.error != null) Notice(action.error!, urgent: true),
        if (action.success != null) Notice(action.success!),
      ],
    );
  }
}
