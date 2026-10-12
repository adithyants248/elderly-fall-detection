# ElderCare AI — Android caregiver app

Real Flutter/Material 3 client for the existing FastAPI application. Flutter
3.47.5 / Dart 3.13.4 is the SDK selected for validation (official stable archive).
See [the inspected API contract](API_CONTRACT.md) for routes and state semantics.

## Setup

Install Flutter and Android Studio with Android SDK tools; complete
`flutter doctor -v` and `flutter doctor --android-licenses`. Add Flutter's `bin`
directory to PATH. Official instructions: https://docs.flutter.dev/install/manual

For this workspace, a local Flutter SDK was downloaded under `tmp/flutter-sdk/`.
To use it from a new PowerShell terminal at the repository root:

```powershell
$env:Path = (Join-Path (Get-Location) 'tmp\flutter-sdk\flutter\bin') + ';' + $env:Path
$env:PUB_CACHE = Join-Path (Get-Location) 'tmp\pub-cache'
# When using the locally installed Android build tools:
$env:ANDROID_HOME = Join-Path (Get-Location) 'tmp\android-sdk'
$env:GRADLE_USER_HOME = Join-Path (Get-Location) 'tmp\gradle-home'
```

These development caches are ignored by Git and are not application dependencies
to commit. A normal Flutter installation can run the same project.

From the repository root, run FastAPI in one terminal:

```powershell
$env:FALL_CAMERA_ENABLED = '1'
$env:FALL_CAMERA_SOURCE = '0'
$env:FALL_CAMERA_SELECTION = 'first'
$env:FALL_DEMO_ENABLED = '1'
.\venv\Scripts\python.exe -B -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

Use `FALL_CAMERA_ENABLED='0'` for a camera-free demonstration. Use one worker;
the camera and event repository must share a process. Do not run the separate
camera preview at the same time. Existing Python dependencies are installed with
`.\venv\Scripts\python.exe -m pip install -r requirements.txt`.

In another terminal:

```powershell
cd mobile
flutter pub get
flutter devices
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

The Android emulator reaches the computer through `10.0.2.2`. For a physical
Android phone, enable Developer options and USB debugging, connect USB, authorize
the debugging prompt, and select the phone from `flutter devices`. Put both
devices on the same Wi-Fi. Find your computer's Wi-Fi IPv4 address with `ipconfig`:

```powershell
flutter run -d <PHONE_DEVICE_ID> --dart-define=API_BASE_URL=http://<COMPUTER_WIFI_IPV4>:8000
```

Enter the same address on the login screen, or change it under Profile & Settings.
Saved server settings override the compile-time default. Check
`http://<COMPUTER_WIFI_IPV4>:8000/api/health` in the phone browser. Allow TCP 8000
on Windows Firewall for your private network if blocked; guest Wi-Fi client
isolation can also prevent access. `localhost` on a phone means the phone itself.

The Android manifest allows Internet access and cleartext HTTP for this local
prototype. Use only a trusted local network: the existing API is unauthenticated.
HTTPS and real server authentication are required before an external deployment.

## Session and settings

The backend has no authentication endpoint. **DEMO SIGN-IN** takes a caregiver
username/email-shaped identifier; it never claims to verify email or password.
The disabled password field and Forgot Password explanation make this explicit.
Flutter Secure Storage saves the local identity, server URL and dark-mode setting.
Logout deletes the saved identity. Profile editing changes only the local demo
identifier; previous backend acknowledgements retain their original identity.
Patient assignment, name, age, phone and verified email are unavailable.

## Caregiver workflow

Home, Monitoring, Alerts, Emergency and Profile use bottom navigation. Open an
alert to see fall details, then acknowledge after review. Emergency Response
requires this acknowledgement, followed by an explicit mock hospital lookup and
selection. Confirm **SEND MOCK EMERGENCY REQUEST** to call the existing record
endpoint. The button is disabled during submission. On a timeout or conflict the
client refreshes state so a completed request can be recognized before retrying.
The backend's acknowledgement, selection and recording replay rules are retained.

The hospital timeline displays only confirmed/acknowledged, options available,
hospital selected and response recorded steps. Hospital records are fictional;
no hospital is contacted. Ambulance status explicitly says unavailable because
there is no dispatch/tracking endpoint. No coordinates, distance or ETA are invented.

The app polls status, falls and health concurrently every three seconds after
each completed refresh. Requests never overlap refresh cycles. Failures back off
to 6/12/24 seconds; existing state remains visible with an offline warning.
Polling pauses when the app leaves the foreground and refreshes on resume.
An active fall banner appears across the main tabs, deduplicated by event ID.
This is foreground alerting, not push notifications or a background service.
Camera frames older than ten seconds are marked stale. Missing state never becomes
SAFE. `created_at` is labelled receipt time; `timestamp` remains source seconds.

Profile's development section is visible only when `/api/health` enables demo
injection. It calls `/api/demo/fall`; resulting cards retain the simulated label.
Live events retain their AI-verified label even if demo injection is enabled.
Camera rearm is explicit, confirmed, and uses the existing backend safety gate.

## Structure and validation

`lib/models` holds typed transport models; `services` centralizes HTTP and secure
storage; `repositories` exposes the inspected API; `providers` holds separate
auth, monitoring, alert and action state using Provider/ChangeNotifier;
`navigation`, `screens` and `widgets` compose the responsive UI.

```powershell
dart format lib test
flutter analyze
flutter test
flutter build apk --debug
```

Tests use isolated test-only HTTP fixtures for error handling, session persistence,
deduplication, double taps, offline retention/recovery, responsive navigation and
the confirmed fall → acknowledgement → hospital selection → mock response flow.
No fixture data is imported by the running application.

For an actual-server demonstration: start FastAPI, sign in, open Profile, simulate
a demo fall, open Alerts, acknowledge, select a mock hospital and record a response.
Verify the same event in the existing browser dashboard. Stop/restart FastAPI to
verify offline recovery; the server's in-memory events disappear on restart.

Remaining backend limits: no durable event history, no user access control or
assignment, no real hospital integration, no ambulance tracking, and no push
notifications. The mobile client does not implement or change AI inference.
