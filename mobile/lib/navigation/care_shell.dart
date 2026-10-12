import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../providers/care_providers.dart';
import '../repositories/care_repository.dart';
import '../services/api_service.dart';
import '../screens/dashboard_screens.dart';
import '../screens/event_screens.dart';
import '../screens/profile_screen.dart';

class CareShell extends StatefulWidget {
  final CareSession? session;
  const CareShell({super.key, this.session});
  @override
  State<CareShell> createState() => _CareShellState();
}

class _CareShellState extends State<CareShell> with WidgetsBindingObserver {
  late final CareSession session;
  int selected = 0;
  @override
  void initState() {
    super.initState();
    session = widget.session ??
        CareSession(
          CareRepository(ApiService(context.read<AuthProvider>().url)),
        );
    WidgetsBinding.instance.addObserver(this);
    session.refresh();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      session.resume();
    } else {
      session.pause();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    session.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MultiProvider(
        providers: [
          Provider.value(value: session),
          ChangeNotifierProvider.value(value: session.monitoring),
          ChangeNotifierProvider.value(value: session.alerts),
          ChangeNotifierProvider.value(value: session.emergency),
        ],
        child: Builder(
          builder: (context) {
            final monitoring = context.watch<MonitoringProvider>();
            final alerts = context.watch<AlertProvider>();
            final emergency = context.watch<EmergencyProvider>();
            return Scaffold(
              appBar: AppBar(
                toolbarHeight: selected == 0 ? 72 : 56,
                title: selected == 0
                    ? const Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                            Text('ElderCare AI',
                                style: TextStyle(
                                    fontSize: 21,
                                    fontWeight: FontWeight.w800,
                                    color: Color(0xff007d84))),
                            SizedBox(height: 4),
                            Text('Smart Elderly Care & Fall Response',
                                style: TextStyle(fontSize: 10)),
                          ])
                    : Text(
                        [
                          'Home',
                          'Monitoring',
                          'Alerts',
                          'Emergency Response',
                          'Profile'
                        ][selected],
                        style: const TextStyle(
                            fontSize: 20, fontWeight: FontWeight.w700)),
                actions: [
                  IconButton(
                    tooltip: 'Refresh backend',
                    onPressed: session.refresh,
                    icon: const Icon(Icons.refresh),
                  ),
                ],
              ),
              body: SafeArea(
                child: Column(
                  children: [
                    if (!monitoring.connected)
                      Material(
                        color: Theme.of(context)
                            .colorScheme
                            .surfaceContainerHighest,
                        child: Padding(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 8,
                          ),
                          child: Row(
                            children: [
                              Icon(
                                monitoring.connected
                                    ? Icons.cloud_done_outlined
                                    : Icons.cloud_off_outlined,
                                size: 20,
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  monitoring.connected
                                      ? 'Connected · Demo identity'
                                      : 'Backend unavailable · Retrying',
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    if (alerts.active.isNotEmpty)
                      Material(
                        color: Theme.of(context).colorScheme.errorContainer,
                        child: ListTile(
                          leading: const Icon(Icons.warning_amber_rounded),
                          title: Text(
                            'FALL DETECTED · ${alerts.active.length} to review',
                          ),
                          subtitle: const Text(
                            'Open the alert and check the person.',
                          ),
                          onTap: () =>
                              openEvent(context, alerts.active.first.id),
                          trailing: const Icon(Icons.chevron_right),
                        ),
                      ),
                    if (emergency.busy) const LinearProgressIndicator(),
                    if (monitoring.updatedAt == null &&
                        monitoring.error == null)
                      const LinearProgressIndicator(),
                    Expanded(
                      child: IndexedStack(
                        index: selected,
                        children: [
                          HomeScreen(
                            onNavigate: (value) =>
                                setState(() => selected = value),
                          ),
                          const MonitoringScreen(),
                          const AlertsScreen(),
                          const EmergencyScreen(),
                          const ProfileScreen(),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              bottomNavigationBar: NavigationBar(
                selectedIndex: selected,
                labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
                onDestinationSelected: (value) =>
                    setState(() => selected = value),
                destinations: [
                  const NavigationDestination(
                    icon: Icon(Icons.home_outlined),
                    label: 'Home',
                  ),
                  const NavigationDestination(
                    icon: Icon(Icons.monitor_heart_outlined),
                    label: 'Monitor',
                  ),
                  NavigationDestination(
                    icon: Badge(
                      isLabelVisible: alerts.active.isNotEmpty,
                      label: Text('${alerts.active.length}'),
                      child: const Icon(Icons.notifications_outlined),
                    ),
                    label: 'Alerts',
                  ),
                  NavigationDestination(
                    icon: Icon(
                      Icons.emergency_outlined,
                      color: alerts.active.isEmpty
                          ? null
                          : Theme.of(context).colorScheme.error,
                    ),
                    label: 'Response',
                  ),
                  const NavigationDestination(
                    icon: Icon(Icons.person_outline),
                    label: 'Profile',
                  ),
                ],
              ),
            );
          },
        ),
      );
}

void openEvent(BuildContext context, String id, {bool emergency = false}) {
  final session = context.read<CareSession>();
  Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => MultiProvider(
        providers: [
          Provider.value(value: session),
          ChangeNotifierProvider.value(value: context.read<AuthProvider>()),
          ChangeNotifierProvider.value(value: session.monitoring),
          ChangeNotifierProvider.value(value: session.alerts),
          ChangeNotifierProvider.value(value: session.emergency),
        ],
        child: EventScreen(id: id, emergencyFirst: emergency),
      ),
    ),
  );
}
