import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/contracts.dart';
import '../navigation/care_shell.dart';
import '../providers/auth_provider.dart';
import '../providers/care_providers.dart';
import '../widgets/care_widgets.dart';

class AlertsScreen extends StatelessWidget {
  const AlertsScreen({super.key});
  @override
  Widget build(BuildContext context) {
    final alerts = context.watch<AlertProvider>();
    return PageBody(
      children: [
        Text('Alert center', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 20),
        if (!context.watch<MonitoringProvider>().connected)
          const Notice(
            'Backend unavailable. Alert history may be out of date.',
            urgent: true,
          ),
        if (alerts.active.isEmpty)
          Padding(
              padding: const EdgeInsets.symmetric(vertical: 28),
              child: Column(children: [
                Icon(Icons.notifications_active_outlined,
                    size: 64, color: Theme.of(context).colorScheme.primary),
                const SizedBox(height: 14),
                Text(
                    context.watch<MonitoringProvider>().connected
                        ? "You're all caught up!"
                        : 'Alert status unavailable',
                    style: Theme.of(context)
                        .textTheme
                        .titleLarge
                        ?.copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(height: 8),
                Text(context.watch<MonitoringProvider>().connected
                    ? 'No active fall alerts.'
                    : 'Reconnect to retrieve current alerts.'),
              ])),
        for (final event in alerts.events) EventCard(event: event),
      ],
    );
  }
}

class EventCard extends StatelessWidget {
  final FallEvent event;
  final bool emergency;
  const EventCard({super.key, required this.event, this.emergency = false});
  @override
  Widget build(BuildContext context) {
    final recorded = event.response?.status == 'RESPONSE_RECORDED';
    final color =
        event.acknowledged ? const Color(0xff208653) : const Color(0xffc32936);
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Card(
      color: !event.acknowledged
          ? (dark ? const Color(0xff45262c) : const Color(0xfffff0f1))
          : null,
      child: InkWell(
        borderRadius: BorderRadius.circular(17),
        onTap: () => openEvent(context, event.id, emergency: emergency),
        child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Icon(
                        event.acknowledged
                            ? Icons.check_circle
                            : Icons.warning_rounded,
                        color:
                            dark ? Color.lerp(color, Colors.white, .5) : color),
                    const SizedBox(width: 10),
                    Expanded(
                        child: Text(
                            recorded
                                ? 'Response Recorded'
                                : event.acknowledged
                                    ? 'Alert Acknowledged'
                                    : 'FALL DETECTED',
                            style: Theme.of(context)
                                .textTheme
                                .titleSmall
                                ?.copyWith(fontWeight: FontWeight.w800))),
                    if (!event.acknowledged)
                      const StatusChip('New', color: Color(0xffc32936)),
                  ]),
                  const SizedBox(height: 14),
                  Text(
                      event.simulated
                          ? 'DEMO / SIMULATED FALL'
                          : 'AI-GENERATED FALL EVENT',
                      style: Theme.of(context).textTheme.labelSmall),
                  const SizedBox(height: 12),
                  Row(children: [
                    const Icon(Icons.person_outline, size: 18),
                    const SizedBox(width: 9),
                    Expanded(child: Text(event.personId))
                  ]),
                  const SizedBox(height: 9),
                  Row(children: [
                    const Icon(Icons.schedule, size: 18),
                    const SizedBox(width: 9),
                    Expanded(
                        child: Text(timeLabel(event.createdAt),
                            style: Theme.of(context).textTheme.bodySmall))
                  ]),
                  const SizedBox(height: 9),
                  Text(recorded
                      ? 'Mock emergency response recorded'
                      : event.acknowledged
                          ? 'Reviewed by caregiver'
                          : event.simulated
                              ? 'Simulated fall needs review'
                              : 'Confirmed fall needs review'),
                  Align(
                      alignment: Alignment.centerRight,
                      child: TextButton.icon(
                          onPressed: () => openEvent(context, event.id,
                              emergency: emergency),
                          label: Text(emergency
                              ? 'OPEN EMERGENCY RESPONSE'
                              : 'VIEW ALERT'),
                          icon: const Icon(Icons.chevron_right, size: 18))),
                ])),
      ),
    );
  }
}

class EmergencyScreen extends StatelessWidget {
  const EmergencyScreen({super.key});
  @override
  Widget build(BuildContext context) {
    final events = context.watch<AlertProvider>().events;
    return PageBody(
      children: [
        Text(
          'Emergency response',
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 20),
        const Notice(
          'PROTOTYPE · Requests are recorded by the mock service. No hospital is contacted and no ambulance is dispatched.',
        ),
        if (events.isEmpty)
          const InfoCard(
            'No fall event',
            children: [
              Text(
                'An emergency response requires a confirmed fall event and caregiver acknowledgement.',
              ),
            ],
          ),
        for (final event in events) EventCard(event: event, emergency: true),
      ],
    );
  }
}

class EventScreen extends StatefulWidget {
  final String id;
  final bool emergencyFirst;
  const EventScreen({super.key, required this.id, this.emergencyFirst = false});
  @override
  State<EventScreen> createState() => _EventScreenState();
}

class _EventScreenState extends State<EventScreen> {
  late bool responseMode = widget.emergencyFirst;
  @override
  Widget build(BuildContext context) {
    final alerts = context.watch<AlertProvider>();
    final event = alerts.find(widget.id);
    final otherAlerts = alerts.active.where((e) => e.id != widget.id).toList();
    final monitoring = context.watch<MonitoringProvider>();
    final action = context.watch<EmergencyProvider>();
    final session = context.read<CareSession>();
    final caregiver = context.read<AuthProvider>().caregiver!.id;
    final enabled = monitoring.connected && !action.busy;
    return Scaffold(
      appBar: AppBar(
        title: Text(responseMode ? 'Emergency response' : 'Fall alert'),
        actions: [
          IconButton(
            onPressed: session.refresh,
            tooltip: 'Refresh event',
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(children: [
          if (otherAlerts.isNotEmpty)
            Material(
              color: Theme.of(context).colorScheme.errorContainer,
              child: ListTile(
                leading: const Icon(Icons.warning_amber_rounded),
                title:
                    Text('Other fall alerts · ${otherAlerts.length} to review'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => openEvent(context, otherAlerts.first.id),
              ),
            ),
          if (!monitoring.connected)
            const Notice(
              'Backend unavailable. Displayed data may be out of date. Actions are disabled until reconnection.',
              urgent: true,
            ),
          Expanded(
              child: PageBody(children: [
            if (action.busy) const LinearProgressIndicator(),
            if (action.error != null) Notice(action.error!, urgent: true),
            if (event == null)
              const InfoCard(
                'Event unavailable',
                children: [
                  Text(
                    'This event is no longer in the backend snapshot. The server may have restarted.',
                  ),
                ],
              )
            else ...[
              if (responseMode) ResponseProgress(event: event),
              if (!responseMode ||
                  !event.acknowledged ||
                  event.response?.status == 'RESPONSE_RECORDED')
                Container(
                  padding: const EdgeInsets.all(18),
                  margin: const EdgeInsets.only(bottom: 20),
                  decoration: BoxDecoration(
                    color: event.acknowledged
                        ? (Theme.of(context).brightness == Brightness.dark
                            ? const Color(0xff193e31)
                            : const Color(0xffe6f6ed))
                        : const Color(0xffdf2935),
                    borderRadius: BorderRadius.circular(22),
                  ),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(
                            event.acknowledged
                                ? Icons.check_circle
                                : Icons.warning_amber_rounded,
                            size: event.response?.status == 'RESPONSE_RECORDED'
                                ? 68
                                : 38,
                            color: event.acknowledged
                                ? (Theme.of(context).brightness ==
                                        Brightness.dark
                                    ? const Color(0xff88d8a5)
                                    : const Color(0xff24964f))
                                : Colors.white),
                        const SizedBox(height: 12),
                        Text(
                            event.response?.status == 'RESPONSE_RECORDED'
                                ? 'RESPONSE RECORDED'
                                : event.acknowledged
                                    ? 'Fall acknowledged'
                                    : 'FALL DETECTED',
                            style: Theme.of(context)
                                .textTheme
                                .headlineSmall
                                ?.copyWith(
                                    fontWeight: FontWeight.w800,
                                    color: event.acknowledged
                                        ? null
                                        : Colors.white)),
                        const SizedBox(height: 8),
                        Text(
                            event.response?.status == 'RESPONSE_RECORDED'
                                ? 'DEMO / MOCK RESPONSE'
                                : event.simulated
                                    ? 'DEMO / SIMULATED FALL'
                                    : 'CONFIRMED FALL',
                            style: TextStyle(
                                color:
                                    event.acknowledged ? null : Colors.white)),
                        const SizedBox(height: 8),
                        if (event.response?.status == 'RESPONSE_RECORDED')
                          const Text(
                              'Mock record saved. No hospital contacted or ambulance dispatched.'),
                      ]),
                ),
              if (!responseMode || !event.acknowledged)
                InfoCard(
                  'Fall details',
                  icon: Icons.person_outline,
                  children: [
                    Fact('Event ID', event.id),
                    Fact('Person ID', event.personId),
                    Fact('Event received', timeLabel(event.createdAt)),
                    Fact(
                        'AI verification',
                        event.simulated
                            ? 'Simulated confirmation; AI not run'
                            : 'Confirmed by the backend. Individual verification steps are not supplied.'),
                    Fact('Current event state', label(event.status)),
                    Fact('Fall probability', percent(event.probability)),
                    Fact(
                      'Acknowledged by',
                      event.acknowledgedBy ?? 'Awaiting caregiver action',
                    ),
                    if (event.acknowledgedAt != null)
                      Fact('Acknowledged at', timeLabel(event.acknowledgedAt)),
                    ExpansionTile(
                      title: const Text('Technical event details'),
                      children: [
                        Fact('Emergency status',
                            label(event.response?.status ?? 'No request')),
                        Fact(
                          'Detection source time',
                          '${event.sourceSeconds} seconds (not wall-clock time)',
                        ),
                      ],
                    ),
                    if (!event.acknowledged)
                      FilledButton(
                        onPressed: !enabled || event.status != 'ALERT_SENT'
                            ? null
                            : () async {
                                if (!await confirm(
                                  context,
                                  'Acknowledge fall?',
                                  'Confirm that you have reviewed this alert. Acknowledgement does not send an emergency request.',
                                  action: 'ACKNOWLEDGE',
                                )) {
                                  return;
                                }
                                await action.perform(
                                  () => session.repository.acknowledge(
                                    event.id,
                                    caregiver,
                                  ),
                                  session.refresh,
                                  message:
                                      'Caregiver acknowledgement recorded.',
                                );
                              },
                        child: const Text('ACKNOWLEDGE'),
                      ),
                    if (!responseMode)
                      TextButton(
                        onPressed: () => setState(() => responseMode = true),
                        child: const Text('REQUEST EMERGENCY ASSISTANCE'),
                      ),
                  ],
                ),
              if (event.acknowledged && !responseMode) ...[
                const OutlinedButton(
                    onPressed: null, child: Text('Mark as Safe - unavailable')),
                const Padding(
                    padding: EdgeInsets.only(bottom: 18),
                    child: Text(
                        'This backend records acknowledgement, not a medical safety assessment.',
                        style: TextStyle(fontSize: 12))),
              ],
              if (event.response?.status == 'RESPONSE_RECORDED')
                InfoCard('Response Details', icon: Icons.task_alt, children: [
                  Fact('Event ID', event.id),
                  Fact('Hospital',
                      event.response!.hospitalName ?? 'Unavailable'),
                  Fact('Recorded at', timeLabel(event.response!.recordedAt)),
                  Fact('Status', 'Response Recorded (Mock)'),
                ]),
              if (responseMode) ...[
                if (event.response?.status == 'HOSPITALS_AVAILABLE')
                  Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text('Select Hospital',
                          style: Theme.of(context)
                              .textTheme
                              .headlineSmall
                              ?.copyWith(fontWeight: FontWeight.w700))),
                const Notice(
                  'MOCK HOSPITAL SERVICE · All offered hospitals are fictional. This flow records a local response only.',
                ),
                if (!event.acknowledged)
                  const Notice(
                    'Acknowledge the fall before requesting hospital options.',
                  ),
                if (event.acknowledged &&
                    (event.response == null ||
                        event.response!.status == 'ACKNOWLEDGED'))
                  InfoCard(
                    'Hospital options',
                    icon: Icons.local_hospital_outlined,
                    children: [
                      const Text(
                        'Load the hospitals offered by the backend for this event.',
                      ),
                      const SizedBox(height: 12),
                      FilledButton(
                        onPressed: !enabled
                            ? null
                            : () => action.perform(
                                  () => session.repository.hospitals(event.id),
                                  session.refresh,
                                  message:
                                      'Hospital lookup completed. If no options appear, retry the lookup.',
                                ),
                        child: const Text('LOAD MOCK HOSPITALS'),
                      ),
                    ],
                  ),
                if (event.response?.status == 'HOSPITALS_AVAILABLE')
                  for (final hospital in event.response!.hospitals)
                    InfoCard(
                      hospital.name,
                      icon: Icons.local_hospital_outlined,
                      children: [
                        const StatusChip('DEMO HOSPITAL'),
                        const SizedBox(height: 10),
                        Text(hospital.address),
                        const SizedBox(height: 12),
                        FilledButton.tonal(
                          onPressed: !enabled
                              ? null
                              : () async {
                                  if (!await confirm(
                                    context,
                                    'Select hospital?',
                                    'Select ${hospital.name} for this mock response? Selection cannot be changed in this backend.',
                                    action: 'SELECT',
                                  )) {
                                    return;
                                  }
                                  await action.perform(
                                    () => session.repository.select(
                                      event.id,
                                      hospital.id,
                                      caregiver,
                                    ),
                                    session.refresh,
                                    message: 'Mock hospital selected.',
                                  );
                                },
                          child: const Text('SELECT HOSPITAL'),
                        ),
                      ],
                    ),
                if (event.response?.hospitalName != null)
                  InfoCard(
                    'Selected hospital',
                    children: [
                      const StatusChip('SELECTED'),
                      const SizedBox(height: 12),
                      Text(event.response!.hospitalName!,
                          style: const TextStyle(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 16),
                      if (event.response!.status == 'HOSPITAL_SELECTED')
                        FilledButton.icon(
                          icon: const Icon(Icons.emergency_outlined),
                          onPressed: !enabled
                              ? null
                              : () async {
                                  if (!await confirm(
                                    context,
                                    'Send emergency request to the hospital?',
                                    'DEMO: This records a mock emergency response only. No hospital will be contacted and no ambulance will be dispatched.',
                                    action: 'SEND REQUEST',
                                  )) {
                                    return;
                                  }
                                  await action.perform(
                                    () => session.repository.record(event.id),
                                    session.refresh,
                                    message:
                                        'Mock emergency response recorded. No hospital contacted or ambulance dispatched.',
                                  );
                                },
                          label: const Text('SEND MOCK EMERGENCY REQUEST'),
                        ),
                    ],
                  ),
                HospitalTimeline(event: event),
                const InfoCard(
                  'Ambulance status',
                  icon: Icons.local_shipping_outlined,
                  children: [
                    Text(
                      'Unavailable. This backend does not provide ambulance assignment, dispatch, location, arrival or ETA.',
                    ),
                  ],
                ),
              ],
            ],
          ])),
        ]),
      ),
    );
  }
}

class HospitalTimeline extends StatelessWidget {
  final FallEvent event;
  const HospitalTimeline({super.key, required this.event});
  @override
  Widget build(BuildContext context) {
    final r = event.response;
    final steps = <(String, bool, DateTime?)>[
      ('Fall confirmed (received)', true, event.createdAt),
      (
        event.simulated
            ? 'Verification simulated (AI not run)'
            : 'AI verification completed',
        true,
        null
      ),
      (
        'Caregiver notified (local mock only)',
        event.status != 'CONFIRMED',
        null
      ),
      ('Caregiver acknowledged', event.acknowledged, event.acknowledgedAt),
      ('Hospital options available', r != null && r.hospitals.isNotEmpty, null),
      ('Hospital selected', r?.hospitalName != null, r?.selectedAt),
      (
        'Mock response recorded',
        r?.status == 'RESPONSE_RECORDED',
        r?.recordedAt,
      ),
    ];
    return InfoCard(
      'Hospital response timeline',
      icon: Icons.timeline,
      children: [
        for (final step in steps)
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: Icon(
              step.$2
                  ? Icons.check_circle_outline
                  : Icons.radio_button_unchecked,
              color: step.$2
                  ? Theme.of(context).colorScheme.primary
                  : Theme.of(context).colorScheme.outline,
            ),
            title: Text(step.$1),
            subtitle: Text(
              step.$2
                  ? step.$3 == null
                      ? 'Completed'
                      : timeLabel(step.$3)
                  : 'Not completed',
            ),
          ),
        const Text(
          'Hospital receipt and acceptance are not reported by this backend.',
        ),
      ],
    );
  }
}
