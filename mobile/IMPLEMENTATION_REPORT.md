# Caregiver application implementation

## Delivered

The real Android Flutter project is in `mobile/`, generated with Flutter 3.47.5
and Dart 3.13.4. `android/` includes its native activity, Gradle build configuration,
Internet permission and prototype HTTP support. No web frontend replaces Android.

Screens/views: splash, explicitly labelled demo login, home, monitoring, alert
center, prominent fall alert, fall details, emergency response, hospital timeline,
ambulance-unavailable view, profile editing of the demo identifier, logout, settings
(working dark mode/server address) and backend-gated demo injection.

## Files and architecture

New app files:

- `lib/main.dart`: Material 3 theme, splash and authentication routing.
- `lib/models/contracts.dart`: caregiver, health, monitoring, fall, hospital and
  emergency response transport models. No fictitious patient/ambulance model data.
- `lib/services/api_service.dart`: configurable URL, HTTP, timeout and friendly errors.
- `lib/services/authentication_service.dart`: secure storage interface/implementation.
- `lib/repositories/care_repository.dart`: existing backend route operations.
- `lib/providers/auth_provider.dart`: secure local session and preferences.
- `lib/providers/care_providers.dart`: separate monitoring, alerts, emergency action
  notifiers; lifecycle-aware polling coordinator.
- `lib/navigation/care_shell.dart`: navigation, persistent connection/fall banner.
- `lib/screens/login_screen.dart`, `dashboard_screens.dart`, `event_screens.dart`,
  `profile_screen.dart`: connected screens and response workflow.
- `lib/widgets/care_widgets.dart`: shared cards, notices, fields and dialogs.
- `test/api_state_test.dart`, `test/app_test.dart`, `test/support.dart`: isolated tests.
- `tool/backend_smoke.dart`: actual HTTP integration check against disposable FastAPI.
- `pubspec.yaml`, `pubspec.lock`, `analysis_options.yaml`, `.gitignore`, `.metadata`,
  native `android/` scaffold, `README.md`, `API_CONTRACT.md` and this report.

Root edits: appended CARETAKER MOBILE APPLICATION documentation to `README.md`;
added local development-tool exclusions to `.gitignore`.

**Backend files changed: none. Endpoints added: none. AI changes: none.** Existing
working-tree changes and all existing tests were preserved.

## API and behavior

The entry point is `src/api/app.py`. Discovered routes are documented in
[API_CONTRACT.md](API_CONTRACT.md): health, system status, camera reset, falls list
and detail, acknowledgement, hospital lookup/selection, response recording, demo fall.

State management uses Provider/ChangeNotifier with separate session, monitoring,
alerts and emergency-action state. HTTP is outside widgets behind the repository.

Authentication is explicitly **local demo identity**, persisted using Flutter
Secure Storage. The API has no login/profile/password-recovery endpoint, and the
client does not pretend to authenticate requests. Password input is disabled with
an explanation. No passwords or secrets are embedded or logged.

Foreground polling runs three requests every three seconds after completion,
pauses in background and backs off to 24 seconds on failure. Alert IDs deduplicate
cards; active alerts remain prominent across tabs. Offline snapshots are retained
and marked stale; event-page offline warnings remain visible while scrolling.

Emergency workflow: open confirmed event → review → acknowledge → explicit mock
hospital lookup → confirm selection → confirm mock request → recorded response.
Submission disables repeat taps. Timeout/conflict handling refreshes server state;
the existing backend provides idempotent replays. No automatic hospital request
is sent on acknowledgement or on alert receipt.

Hospital timeline reflects only the actual backend states. The backend never
contacts hospitals or dispatches ambulances; the UI labels this and shows ambulance
tracking as unavailable. It fabricates no GPS, ETA, distance, patients or hospitals.

The demo action appears only when health enables it and calls the existing demo
route after confirmation. Simulated and live event labels remain separate.

## Completed validation

On 2026-09-22:

- `dart format lib test tool`: passed.
- `flutter analyze --no-pub`: **No issues found**.
- `flutter test --no-pub`: **17 passed**. Includes 320/412/800-pixel layouts, splash,
  login validation, password explanation, home/monitoring/alerts, details,
  acknowledgement, hospital selection, cancellation/confirmation of a response,
  ambulance limitation, offline UI and logout. State tests cover restore,
  deduplication, double taps, empty state, reconnection, HTTP errors and timeouts.
- `dart run tool/backend_smoke.dart http://127.0.0.1:8767`: **passed** against a
  disposable actual FastAPI process, including repeated acknowledgement and
  repeated mock response recording. The disposable process was stopped afterward.
- Existing backend suite: `venv/Scripts/python.exe -B -m pytest -q -p no:cacheprovider`:
  **249 passed, 56 subtests passed**, four dependency deprecation warnings.

## Run and limitations

Exact FastAPI/Flutter commands and physical-phone networking instructions are in
[README.md](README.md). Set the phone's API URL to your computer's Wi-Fi IPv4
address on port 8000; both must share a reachable private network. Emulator default
is `http://10.0.2.2:8000`. Saved app settings override the compile-time URL default.

Backend limits remain: in-memory history, unauthenticated API, no patient
assignment, mock hospital service and no ambulance/push-notification service.
Polling requires the app to be in the foreground. No physical Android device was
attached during validation; widget tests do not establish device/hardware behavior.
