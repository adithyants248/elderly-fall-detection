import 'package:flutter/material.dart';
import '../models/contracts.dart';

String label(String value) => value.replaceAll('_', ' ');
String timeLabel(DateTime? value) =>
    value == null ? 'Unavailable' : value.toLocal().toString().split('.').first;
String percent(double? value) =>
    value == null ? 'Unavailable' : '${(value * 100).toStringAsFixed(1)}%';

class InfoCard extends StatelessWidget {
  final String title;
  final List<Widget> children;
  final IconData icon;
  const InfoCard(
    this.title, {
    super.key,
    required this.children,
    this.icon = Icons.info_outline,
  });
  @override
  Widget build(BuildContext context) => Card(
        margin: const EdgeInsets.only(bottom: 16),
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(icon,
                      color: title == 'FALL DETECTED'
                          ? Theme.of(context).colorScheme.error
                          : Theme.of(context).colorScheme.primary),
                  const SizedBox(width: 12),
                  Expanded(
                      child: Text(title,
                          style:
                              Theme.of(context).textTheme.titleMedium?.copyWith(
                                    color: title == 'FALL DETECTED'
                                        ? Theme.of(context).colorScheme.error
                                        : null,
                                    fontWeight: FontWeight.w700,
                                  ))),
                ],
              ),
              const SizedBox(height: 16),
              ...children,
            ],
          ),
        ),
      );
}

class Fact extends StatelessWidget {
  final String name, value;
  const Fact(this.name, this.value, {super.key});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: LayoutBuilder(builder: (context, constraints) {
          final title =
              Text(name, style: Theme.of(context).textTheme.bodySmall);
          final detail = SelectableText(value,
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(fontWeight: FontWeight.w600));
          if (constraints.maxWidth < 260 ||
              MediaQuery.textScalerOf(context).scale(14) > 20) {
            return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [title, const SizedBox(height: 5), detail]);
          }
          return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(flex: 4, child: title),
            const SizedBox(width: 16),
            Expanded(flex: 6, child: detail)
          ]);
        }),
      );
}

class Notice extends StatelessWidget {
  final String text;
  final bool urgent;
  const Notice(this.text, {super.key, this.urgent = false});
  @override
  Widget build(BuildContext context) => Semantics(
        liveRegion: urgent,
        child: Container(
          width: double.infinity,
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            color: urgent
                ? (Theme.of(context).brightness == Brightness.dark
                    ? const Color(0xff493b20)
                    : const Color(0xfffff1d5))
                : Theme.of(context).colorScheme.secondaryContainer,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(urgent ? Icons.warning_amber_rounded : Icons.info_outline),
              const SizedBox(width: 12),
              Expanded(child: Text(text)),
            ],
          ),
        ),
      );
}

class PageBody extends StatelessWidget {
  final List<Widget> children;
  const PageBody({super.key, required this.children});
  @override
  Widget build(BuildContext context) => Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 680),
          child: ListView(
              padding: const EdgeInsets.fromLTRB(18, 14, 18, 24),
              children: children),
        ),
      );
}

/// Presentation of the existing backend snapshot; no inference or state changes.
class MonitoringHero extends StatelessWidget {
  final MonitoringStatus? status;
  final bool connected;
  final bool activeAlert;
  const MonitoringHero(
      {super.key,
      required this.status,
      required this.connected,
      this.activeAlert = false});

  @override
  Widget build(BuildContext context) {
    final s = status;
    final live = connected && s != null && s.camera == 'running' && !s.stale;
    final state = live ? s.state : 'Unavailable';
    final detected = live ? s.diagnostics['person_detected'] : null;
    final ready = live && s.diagnostics['temporal_ready'] == true;
    final normal = state == 'NORMAL' && ready && detected == 1 && !activeAlert;
    final fall = state == 'CONFIRMED_FALL';
    final awaitingRearm = fall && s?.diagnostics['reason'] == 'awaiting_reset';
    final suspected = state == 'FALL_SUSPECTED';
    final title = awaitingRearm
        ? 'Previous fall confirmed — awaiting camera rearm'
        : activeAlert
        ? 'ALERT NEEDS REVIEW'
        : !live
            ? 'MONITORING UNAVAILABLE'
            : fall
                ? 'CONFIRMED FALL'
                : suspected
                    ? 'FALL SUSPECTED'
                    : normal
                        ? 'NO FALL DETECTED'
                        : 'MONITORING';
    final dark = Theme.of(context).brightness == Brightness.dark;
    final accent = fall
        ? (dark ? const Color(0xffffb4ab) : const Color(0xffb32632))
        : normal
            ? (dark ? const Color(0xffa0d8b8) : const Color(0xff246444))
            : (dark ? const Color(0xffffd990) : const Color(0xff81550a));
    return Semantics(
      liveRegion: fall || suspected,
      child: Container(
        margin: const EdgeInsets.only(bottom: 20),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 22),
        decoration: BoxDecoration(
          color: dark
              ? const Color(0xff18333b)
              : fall
                  ? const Color(0xfffff0f1)
                  : normal
                      ? const Color(0xffe6f6ed)
                      : const Color(0xffeaf4f5),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: accent.withValues(alpha: .25)),
        ),
        child:
            Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('CURRENT STATUS',
              textAlign: TextAlign.center,
              style: TextStyle(
                  color: accent,
                  fontWeight: FontWeight.w700,
                  fontSize: 11,
                  letterSpacing: 1)),
          const SizedBox(height: 12),
          Icon(
              activeAlert
                  ? Icons.notifications_active_outlined
                  : normal
                      ? Icons.verified_user_rounded
                      : fall
                          ? Icons.warning_rounded
                          : Icons.monitor_heart_outlined,
              color: accent,
              size: 52),
          const SizedBox(height: 12),
          Text(title,
              textAlign: TextAlign.center,
              style: Theme.of(context)
                  .textTheme
                  .titleLarge
                  ?.copyWith(color: accent, fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          Text(
              activeAlert
                  ? 'Open Alerts to review the latest event.'
                  : !live
                      ? 'Check the backend and camera connection.'
                      : fall
                          ? awaitingRearm
                              ? 'The previous episode remains latched. Open Alerts to review the event.'
                              : 'A fall has been confirmed. Open Alerts to review the event.'
                          : suspected
                              ? 'The system is observing movement before confirmation.'
                              : ready
                                  ? 'No fall reported in the latest observation.'
                                  : 'Preparing the observation history.',
              textAlign: TextAlign.center),
          const SizedBox(height: 10),
          Text('Monitoring status is not a guarantee of safety.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodySmall),
        ]),
      ),
    );
  }
}

class StatusChip extends StatelessWidget {
  final String text;
  final Color color;
  const StatusChip(this.text,
      {super.key, this.color = const Color(0xff007d84)});
  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final foreground = dark ? Color.lerp(color, Colors.white, .6)! : color;
    return Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
        decoration: BoxDecoration(
            color: color.withValues(alpha: dark ? .2 : .09),
            borderRadius: BorderRadius.circular(24)),
        child: Text(text,
            style: TextStyle(
                color: foreground, fontSize: 11, fontWeight: FontWeight.w700)));
  }
}

class SummaryTile extends StatelessWidget {
  final String title, value;
  final IconData icon;
  const SummaryTile(this.title, this.value, {super.key, required this.icon});
  @override
  Widget build(BuildContext context) => Card(
      margin: EdgeInsets.zero,
      child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(children: [
            Icon(icon, color: Theme.of(context).colorScheme.primary, size: 22),
            const SizedBox(width: 10),
            Expanded(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  Text(title, style: Theme.of(context).textTheme.bodySmall),
                  const SizedBox(height: 4),
                  Text(value,
                      style: Theme.of(context)
                          .textTheme
                          .bodyMedium
                          ?.copyWith(fontWeight: FontWeight.w700)),
                ]))
          ])));
}

class SummaryPair extends StatelessWidget {
  final Widget first, second;
  const SummaryPair({super.key, required this.first, required this.second});
  @override
  Widget build(BuildContext context) =>
      LayoutBuilder(builder: (context, constraints) {
        if (constraints.maxWidth < 290 ||
            MediaQuery.textScalerOf(context).scale(14) > 20) {
          return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [first, const SizedBox(height: 10), second]);
        }
        return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: first),
          const SizedBox(width: 10),
          Expanded(child: second)
        ]);
      });
}

class ResponseProgress extends StatelessWidget {
  final FallEvent event;
  const ResponseProgress({super.key, required this.event});
  @override
  Widget build(BuildContext context) {
    final done = [
      event.acknowledged,
      event.response?.hospitalName != null,
      event.response?.status == 'RESPONSE_RECORDED'
    ];
    return Padding(
        padding: const EdgeInsets.symmetric(vertical: 20),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          for (var i = 0; i < 3; i++)
            Expanded(
                child: Column(children: [
              CircleAvatar(
                  radius: 16,
                  backgroundColor: done[i]
                      ? Theme.of(context).colorScheme.primary
                      : Theme.of(context).colorScheme.surfaceContainerHighest,
                  child: done[i]
                      ? Icon(Icons.check,
                          size: 18,
                          color: Theme.of(context).colorScheme.onPrimary)
                      : Text('${i + 1}',
                          style: Theme.of(context).textTheme.labelMedium)),
              const SizedBox(height: 8),
              Text(['Acknowledge', 'Hospital', 'Response'][i],
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.labelSmall),
            ])),
        ]));
  }
}

Future<bool> confirm(
  BuildContext context,
  String title,
  String text, {
  String action = 'CONFIRM',
}) async =>
    await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Text(text),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('CANCEL'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text(action),
          ),
        ],
      ),
    ) ??
    false;

Future<String?> editValue(
  BuildContext context,
  String title,
  String initial, {
  bool server = false,
}) =>
    showDialog<String>(
      context: context,
      builder: (_) =>
          _EditDialog(title: title, initial: initial, server: server),
    );

class _EditDialog extends StatefulWidget {
  final String title, initial;
  final bool server;
  const _EditDialog({
    required this.title,
    required this.initial,
    required this.server,
  });
  @override
  State<_EditDialog> createState() => _EditDialogState();
}

class _EditDialogState extends State<_EditDialog> {
  late final controller = TextEditingController(text: widget.initial);
  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.title),
        content: TextField(
          controller: controller,
          maxLength: widget.server ? null : 160,
          keyboardType: widget.server ? TextInputType.url : TextInputType.text,
          decoration: InputDecoration(
            labelText: widget.server ? 'Server address' : 'Email / Username',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('CANCEL'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text),
            child: const Text('SAVE'),
          ),
        ],
      );
}
