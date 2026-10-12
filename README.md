# Elderly fall detection

See [Live inference correction and validation](LIVE_PIPELINE.md) for causal
preprocessing, startup protection, camera/API commands and safe manual checks.

## Local API and phone dashboard

The application layer serves a responsive HTML/CSS/vanilla-JavaScript dashboard
and FastAPI endpoints from the same origin. No CORS configuration is needed.
The live GRU path uses causal preprocessing and temporal onset verification.

```text
PostFallVerifier result -> existing caregiver adapter -> shared caregiver repository
 -> FastAPI -> phone dashboard (2-second polling)
 -> existing caregiver acknowledgement -> existing hospital service
 -> offered mock hospitals -> selection -> mock response recording
```

`src/api/app.py` contains the thin routes, domain-error translation and static
serving. `context.py` composes one shared set of existing in-memory repositories
and services and exposes the verifier integration method. `models.py` validates
request bodies and provides a focused fall-event response. The existing typed
hospital response is serialized directly. `templates/dashboard.html` and
`static/css/style.css`, `static/js/app.js` provide the mobile interface.

From the repository root, install dependencies and start **one worker**:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -B -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/` on the computer; API docs are at
`http://localhost:8000/docs`. The dashboard itself uses only local assets and
works without internet. FastAPI's default Swagger UI at `/docs` uses CDN assets,
so its interactive rendering requires internet; `/openapi.json` is local.

For a phone, connect both devices to the same Wi-Fi. Run `ipconfig` in Windows
PowerShell and find **IPv4 Address** under the active Wi-Fi adapter (not a VPN or
virtual adapter). Open `http://<COMPUTER-LAN-IP>:8000/` on the phone, substituting
that address. Do not use `localhost` on the phone. If Windows Firewall prompts,
allow Python on your private network. Guest Wi-Fi client isolation may prevent
access. No IP is hard-coded and no firewall rules are changed by this project.
Do not expose this unauthenticated prototype to the public internet.

To demonstrate: press **SIMULATE DEMO FALL**, then **ACKNOWLEDGE FALL**, select
one offered mock hospital, and press **RECORD EMERGENCY RESPONSE**. Simulation
events display a DEMO badge and a simulated person ID. The dashboard shows source
seconds separately from the received wall-clock time, acknowledgement details,
and recorded response progress. Polling updates existing events without duplicate
cards, pauses actions while requests run, shows connection failures, and restores
workflow state after a browser refresh. API availability is not camera status.

| Method | Endpoint | Behavior |
| --- | --- | --- |
| GET | `/api/health` | API status and mock/demo configuration |
| GET | `/api/falls` | All stored events, including response progress |
| GET | `/api/falls/{event_id}` | One event, or 404 |
| POST | `/api/falls/{event_id}/acknowledge` | Existing acknowledgement service; body `{"caregiver_id":"caregiver-001"}` |
| GET | `/api/falls/{event_id}/hospitals` | Start/reuse response and return its offered `hospitals` array |
| POST | `/api/falls/{event_id}/hospital` | Body `{"hospital_id":"MOCK-H002","caregiver_id":"caregiver-001"}`; ID must be offered |
| POST | `/api/falls/{event_id}/emergency-response` | No body; record selected mock response |
| POST | `/api/demo/fall` | No body; create a clearly simulated event (201) |

Unknown records/options return 404, conflicting states return 409, invalid
bodies/IDs or missing location return 422. Unexpected errors return a generic
500 message rather than a traceback. The hospital GET initializes in-memory
response state on first use; repeated requests reuse cached results. It still
requires acknowledgement. Selection and recording never implicitly perform
the prerequisite steps. The recording response includes `mock: true`.

Demo injection is enabled by default for this local prototype. Disable it before
starting the server with `$env:FALL_DEMO_ENABLED = "0"`; the endpoint then returns
404 and the button is hidden. This setting is not authentication.

The integration boundary for an application-owned producer is:

```python
from src.api.app import app

# In the SAME process serving this app; result is from the existing verifier.
app.state.context.consume_verification_result(result)
```

This delegates to the existing caregiver adapter and preserves its duplicate and
nonconfirmed-event behavior. It does not run inference or change/reset the verifier.
The existing standalone camera runners are unchanged and do not automatically
publish into the server process. Running them in a separate terminal does not
share these in-memory repositories. Set `FALL_CAMERA_ENABLED=1` before starting
the API to use its application-owned camera worker and shared event repository.

All hospital lookups use the existing mock search with explicitly fictional
`Location(0, 0)` coordinates. No GPS is accessed. An application can construct
`ApplicationContext(location=...)`; `None` produces the existing missing-location
error. This configuration never represents the user's actual location.

Validation:

```powershell
.\venv\Scripts\python.exe -B -m pytest -v
.\venv\Scripts\python.exe -B -m pytest tests/api -v
.\venv\Scripts\python.exe -B -m scripts.validate_gru_artifacts
```

`pytest.ini` limits collection to `tests` and supports the existing core tests'
sibling imports without modifying them. API tests use isolated app instances and
the real caregiver/hospital services. No camera, internet or ML is needed for
`tests/api`; the complete suite also runs the existing artifact/model checks.

Optional browser smoke check (installed Chrome, with the local server running):

```powershell
.\venv\Scripts\python.exe -m pip install playwright==1.62.0
.\venv\Scripts\python.exe -B -m scripts.check_dashboard_browser
```

This creates one DEMO event and verifies acknowledgement, hospital selection,
mock recording, refresh persistence and phone/desktop horizontal layout. Playwright
is a development-only helper and is not required to run the application.

Limitations: this is a local prototype. Hospital data is fictional; responses and
notifications are mocked. No hospital is contacted, ambulance dispatched, patient
transfer initiated, or SMS/WhatsApp/email sent. Authentication, database and GPS
are not implemented. Caregiver IDs are caller supplied. Records vanish on server
restart; do not use multiple workers or expect reload to retain state. No cloud
deployment, WebSockets, maps or frontend framework is included.

## Caregiver Alert and Response Module

`src/caregiver/` is a standard-library-only module independent of ML. It consumes
confirmed events through `adapter.py`, uses a typed `FallEvent` and validated
`CONFIRMED -> ALERT_SENT -> ACKNOWLEDGED` lifecycle, and separates service logic
from repository storage and notification presentation.

- `models.py`: event identity, source timestamp, probability, lifecycle and response.
- `repository.py`: repository protocol and in-memory snapshots; active means not acknowledged.
- `notifier.py`: notifier protocol, formatted alert and mock recording `sent_alerts`.
- `service.py`: creation, alert sending, lookup, active events and acknowledgement.
- `adapter.py`: accepts the existing PostFallVerifier result without importing ML.

Integration at the application boundary (the ML runners remain unchanged):

```python
from src.caregiver.adapter import consume_verification_result
from src.caregiver.repository import InMemoryFallEventRepository
from src.caregiver.notifier import MockCaregiverNotifier
from src.caregiver.service import CaregiverResponseService

notifier = MockCaregiverNotifier()
service = CaregiverResponseService(InMemoryFallEventRepository(), notifier)
# result is the existing verifier/inference result dictionary:
event = consume_verification_result(result, service)
# Later, after displaying service.get_event(event_id):
updated = service.acknowledge_event(event_id, caregiver_id)
```

NORMAL and FALL_SUSPECTED never alert. A latched confirmed result with event=None
also does nothing. Duplicate delivery of the same event_id returns the stored
event without resending; conflicting identity/details raise DuplicateEventError.
Repeated acknowledgement by the same caregiver preserves the original response;
a different caregiver cannot overwrite it. Unsent events cannot be acknowledged.
Notifier failure propagates and leaves CONFIRMED for retry. The mock deduplicates
by event_id, including retry after delivery succeeded but status saving failed.

Source timestamp is preserved as source seconds: monotonic/video timestamps are
NOT interpreted as dates. created_at/acknowledged_at are timezone-aware reception
and response times. Track ID is the default person identifier, not a verified
identity; a caller can pass an existing person_id mapping. No names or medical
details are invented. Caregiver acknowledgement does not reset the ML verifier.

```powershell
.\venv\Scripts\python.exe -m scripts.demo_caregiver_response
.\venv\Scripts\python.exe -B -m unittest discover -s tests/caregiver -v
.\venv\Scripts\python.exe -B -m unittest discover -s tests/core -v
.\venv\Scripts\python.exe -B -m scripts.validate_gru_artifacts
```

The demo simulates an event, records/displays its mock alert, and acknowledges it.
**Notifications are mocked: no real caregiver, hospital, or emergency service is
contacted.** The separate hospital module below consumes acknowledgement, and the
local API/dashboard above presents it. There is no database or authentication.
Records and deduplication are process-local and lost
on restart. Share one service instance; distributed transactions/delivery retries
require a future persistent repository and idempotent notifier. Logging records
event IDs and lifecycle actions, not caregiver identity or personal details.
The caregiver workflow ends at acknowledgement. No new dependencies are required.

## Hospital / Emergency Response Module

`src/hospital/` implements the next independent, standard-library-only stage.
`EmergencyResponseService` reads the existing `FallEventRepository` and accepts
only stored `ACKNOWLEDGED` events. It does not modify caregiver events or ML code.
The API layer above integrates through this service layer.

- `models.py`: immutable typed `Location`, `Hospital`, `EmergencyResponse`, statuses
  and domain errors. Coordinates must be finite and within latitude/longitude
  bounds. Hospitals contain ID, name, address, coordinates, `distance_km` and optional
  phone. Responses link to the existing event ID and retain options, selection,
  caregiver ID and timezone-aware creation, selection and recording timestamps.
- `repository.py`: repository protocol and in-memory storage with one response per
  event, validated forward transitions, immutable identities/options/selections,
  and create/get/update/list_all/list_active operations. Active means not recorded.
  Hospital options are stored within response snapshots; no separate hospital
  repository or duplicate hospital CRUD catalog is needed for this search workflow.
- `hospital_service.py`: `HospitalSearchService` protocol and mock implementation.
  Three explicitly fictional hospitals use fixed demo coordinates around (0, 0).
  Haversine geographic distance in kilometers is calculated from the supplied
  location; results sort by distance then ID, with a positive result limit.
  These are demo catalog entries, not actual nearby facilities or live routing
  distances. There is no radius or availability filter and no admission claim.
- `service.py`: acknowledgement gate, search, selection and recording orchestration.
- `emergency_service.py`: `EmergencyService` protocol and `MockEmergencyService`,
  which stores local request snapshots and deduplicates by response ID.

Lifecycle:

```text
Caregiver ACKNOWLEDGED
 -> response ACKNOWLEDGED
 -> HOSPITALS_AVAILABLE
 -> HOSPITAL_SELECTED
 -> RESPONSE_RECORDED
```

Application integration after the existing caregiver acknowledgement:

```python
from src.hospital.models import Location
from src.hospital.repository import InMemoryEmergencyResponseRepository
from src.hospital.hospital_service import MockHospitalSearchService
from src.hospital.emergency_service import MockEmergencyService
from src.hospital.service import EmergencyResponseService

# caregiver_repository is the same repository used by CaregiverResponseService.
hospital = EmergencyResponseService(
    caregiver_repository, InMemoryEmergencyResponseRepository(),
    MockHospitalSearchService(), MockEmergencyService(),
)
response = hospital.start_response(acknowledged_event_id, Location(0, 0))  # demo only
options = hospital.get_nearby_hospitals(response.response_id)
# Display options and supply the caregiver's selection:
selected = hospital.select_hospital(response.response_id, options[1].hospital_id, caregiver_id)
recorded = hospital.record_response(selected.response_id)
```

Location is caller-supplied; no device/browser location is accessed. Passing `None`
raises `MissingLocationError` with an explanation and creates no response. The caller
can display that message and retry when a location is available; no location is
invented. Unknown caregiver events reuse the existing `EventNotFoundError`.
Unacknowledged events, unknown responses/hospitals, invalid states and conflicting
duplicates have explicit domain errors.

`start_response` saves the initial response and searches immediately. Empty results
leave it `ACKNOWLEDGED`; the UI should show no options and may retry
`get_nearby_hospitals`. Search failure propagates and preserves the same retryable
record. Successful options are cached. Selection accepts only an offered ID and
records one hospital, selector and timestamp. A matching replay preserves the
original selection; conflicting hospital/selector changes are rejected.
`record_response` is a separate action, requiring selection. Recording failures
leave `HOSPITAL_SELECTED` for retry. The mock also deduplicates a retry after its
request was saved but the repository update failed. Identical start requests reuse
the existing response; conflicting locations are rejected. Independent fall events
have independent responses. Logs contain IDs/counts/actions, not coordinates or
caregiver identities.

Run the complete simulated selection demo and independent hospital tests:

```powershell
.\venv\Scripts\python.exe -B -m scripts.demo_hospital_response
.\venv\Scripts\python.exe -B -m unittest discover -s tests/hospital -v
```

Run all three test directories separately (existing core tests use sibling imports):

```powershell
.\venv\Scripts\python.exe -B -m unittest discover -s tests/core -v
.\venv\Scripts\python.exe -B -m unittest discover -s tests/caregiver -v
.\venv\Scripts\python.exe -B -m unittest discover -s tests/hospital -v
.\venv\Scripts\python.exe -B -m scripts.validate_gru_artifacts
```

**Hospital data is MOCK. No real hospital API is connected; no real emergency service
is contacted, no ambulance is dispatched and no real patient transfer is initiated.**
Database and authentication are not implemented. The local dashboard above supplies
selector IDs from callers; these are not authenticated identities.
Records and deduplication are lost on
restart. Share one service instance for serialized operations; multi-process storage
and external delivery guarantees require future infrastructure. Future providers can
implement the protocols without adding hospital logic to caregiver or ML modules.
No dependencies were added. The workflow stops at recording the mock request.

The existing webcam application remains the rule-based pipeline:

```powershell
.\venv\Scripts\python.exe -m scripts.run_pipeline
```

## Post-GRU verification

`src/core/fall_verification/post_fall.py` adds a separate decision policy for
**actual GRU probabilities**, not the old rule-based score. `FallVerifier` in
`verifier.py` still serves the existing webcam application; it cannot be reused
unchanged because it requires lying geometry, whereas the GRU policy requires
a probability followed by motion-based inactivity.

```python
from src.core.fall_verification.post_fall import PostFallVerifier

from src.core.fall_detection.model_schema import ArtifactPaths
verifier = PostFallVerifier(threshold_path=ArtifactPaths().threshold)
result = verifier.update(
    track_id=1,
    fall_probability=0.35,  # actual model output, after 60 frames
    features={
        "body_center_movement": 0.5,
        "hip_vertical_velocity": 0.2,
        "hip_horizontal_velocity": 0.1,
        "torso_angle_change": 0.5,
        "aspect_ratio_change": 0.01,
        "person_detected": 1,
    },
    timestamp=video_timestamp_seconds,
)
if result["event"] is not None:
    caregiver_event = result["event"]  # persist/enqueue in a future handler
# After the event has been handled: verifier.reset(track_id)
```

Keep one verifier instance across observations. Pass None probability during
model warmup/unavailability; no suspicion is started. `update_vector()` accepts
the exact 20-feature order in `FEATURE_NAMES`. Features for this decision layer
must be **raw, unscaled, current observed** values, not interpolated/scaled model
inputs. Do not use the older features.py velocity/movement conventions:
training uses frame differences and hip-center movement. Both extractors use
the notebook's UNSIGNED atan2(abs(dx), abs(dy)) torso angle.

States:

- Probability >= **0.30** enters `FALL_SUSPECTED` once, including on a moving
  triggering frame (which may be the fall).
- Subsequent observed low-motion frames spanning **3 seconds** confirm the
  event. Repeated high probabilities do not restart the timer. A lower valid
  probability alone does not cancel a suspicion.
- Any substantial motion before confirmation cancels to `NORMAL`, with no
  rearming on that same observation.
- Missing pose/motion/prediction or a gap over 0.5 seconds cancels suspicion.
- `CONFIRMED_FALL` remains latched until explicit reset; it emits exactly one
  event per episode in this process. Movement/tracking loss cannot acknowledge
  an unhandled emergency. Cleanup only removes stale nonconfirmed tracks.

`PostFallConfig` centralizes initial motion limits: body displacement 15 px/frame,
vertical/horizontal hip differences 10 px/frame, torso change 10 degrees/frame,
aspect change 0.2/frame. Durations use seconds; thresholds still depend on source
resolution and sampling rate and need calibration. No 90-frame FPS assumption
is used for the three-second timer.

## Artifacts and GRU inference

Original files remain read-only in `colab_reference/`:

- `ur_gru_fall_detector.keras`
- `scaler.pkl`
- `selected_threshold.txt` (0.30)

The archive declares `(None, 60, 20)` input and Keras 3.13.2 metadata. The scaler
records scikit-learn 1.6.1; these runtime versions are pinned in requirements.
YOLO weights remain at `models/pose/yolov8n-pose.pt`. `ArtifactPaths` in
`model_schema.py` centrally resolves these paths independently of working directory.
The reconstructed `models/fall_detection/train_medians.pkl` is the sole generated
median artifact. `reconstruction.json` records source hashes, split IDs and parity
results. The original median pickle was absent; these are medians reconstructed
from notebook Cell 6 and `UR_features_all.csv`, not scaler means.

The implemented online connection is:

```
existing pose/tracking -> training-compatible 20 raw features per frame
 -> immutable causal filling -> per-source/ID 60-frame buffer
 -> saved scaler.transform -> (1, 60, 20) -> saved GRU probability
 -> causal transition gate + PostFallVerifier + raw observed motion
 -> one confirmed-fall event -> application caregiver adapter
```

`preprocessing.py` is the canonical model extractor/preprocessor. It preserves
raw NaNs, exports all 20 features, computes motion continuously before imputation,
and uses only the saved scaler's transform. `gru_inference.py` loads the GRU once,
buffers observations, predicts after 60 rows, and passes raw observed motion to
the existing PostFallVerifier. `features.py` remains the legacy rule-based API;
its time-normalized derivatives must not be fed to the GRU.

Offline parity follows Cell 6: source-sequence quality filter >=70%, class-wise
70/15/15 splits with random_state=42, full-source-sequence bidirectional linear
interpolation of 19 features (no gap limit), training medians for residual NaNs,
scaler fitted originally on training frames, transform all 20 columns, then
60-row windows with stride 15, float32. No scaler fitting occurs in our code.
The validation command reproduces all three supplied X/y arrays; observed maximum
absolute feature error is 0.0 for train, validation and test.

**Online limitation:** live input cannot see future source observations.
Each row is filled once: spatial features use the last finite observation, then
saved training medians; missing motion uses saved training medians directly.
Earlier rows never change. This is not generally numerically equal to offline
full-sequence interpolation. `person_detected` stays binary before
scaling. Entirely missing pose rows are not changed to zero motion for verification.
There is no 70% quality filter applied to live windows. Predictions run each frame
after warmup (training window stride was 15). An observation gap >0.5 seconds resets
the live buffer and cancels suspicion. Reacquisition after a missing detection
also starts a fresh 60-frame history. This is deployment policy, not training
preprocessing. No deliberate frame-rate resampling or image resizing is added.

Reconstruct/validate artifacts (never modifies `colab_reference/`):

```powershell
.\venv\Scripts\python.exe -m scripts.validate_gru_artifacts --reconstruct
.\venv\Scripts\python.exe -m scripts.validate_gru_artifacts
```

Run the GRU webcam/video path:

```powershell
.\venv\Scripts\python.exe -m scripts.run_gru_pipeline
.\venv\Scripts\python.exe -m scripts.run_gru_pipeline --source example.mp4
.\venv\Scripts\python.exe -m scripts.run_gru_pipeline --selection tracked --device cpu
```

Default selection uses the first YOLO detection at confidence 0.25, as in Colab,
and reports source ID 0. It has no identity guarantee: use a single-person scene.
Optional tracked mode reuses PersonTracker with ByteTrack and separate histories;
person selection/ID switches are then a deployment difference from training.
Unreadable video sources raise an error; video decode ends at EOF/read failure.
The notebook instead recursively read sorted PNG files and skipped unreadable
images. For exact dataset parity use the offline CSV validation path.

Press q to quit; r resets/acknowledges all episodes and restarts warmup. The screen
shows probability, state and buffer/timer progress. Confirmation produces one
local console event; no caregiver notification is sent. All artifact paths can
be overridden with --model/--scaler/--medians/--threshold/--pose. The threshold file
must still contain 0.30. YOLO auto-selects CUDA if available, otherwise CPU.
Keras defaults to its PyTorch backend, reusing the project's runtime rather than
requiring TensorFlow; an explicitly selected Keras backend is respected.

The local API above accepts this event payload through its same-process adapter;
the standalone runner does not publish to it. No network caregiver notification is sent here. Durable
event storage, delivery/retry, restart deduplication, concurrency, and handling
track-ID switches are not implemented by this in-memory state machine.

## Run post-GRU verification independently

Replay a JSONL file of actual predictions (one observation per line):

```powershell
.\venv\Scripts\python.exe -m scripts.verify_gru_predictions predictions.jsonl
```

Each line contains `track_id`, `timestamp` (seconds), `fall_probability` (number
or null during warmup), and `features` as in the Python example. Input must be
ordered within each track and use one shared source timeline for stale cleanup.
Use `-` as the filename to read stdin. Output is JSONL state/results with `event`
populated only on confirmation; output is not delivery to a caregiver.

Install dependencies into the project environment with:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

New inference dependencies are pandas, scikit-learn, joblib, Keras and h5py.
The post-GRU state machine itself remains standard-library-only.

```powershell
.\venv\Scripts\python.exe -B -m unittest discover -s tests/core -v
```

Tests validate notebook extraction on synthetic poses, exact offline artifact
parity, software transitions, shape/order, saved-model loading and one-time
event emission. They do not establish real-world camera accuracy. Resolution,
actual FPS, pose-model/library differences, occlusion, tracking switches and the
documented online imputation difference remain deployment limitations. The original
notebook did not pin Ultralytics, and its labels apply to entire Fall/ADL sequences.

## CARETAKER MOBILE APPLICATION

The Flutter Android application **ElderCare AI** is in [`mobile/`](mobile/README.md).
It connects to the existing FastAPI routes without changing the AI or backend.
See [mobile setup and workflow](mobile/README.md) for Flutter version, dependency
installation, emulator/physical-phone networking, secure demo identity, polling,
acknowledgement, mock emergency response, hospital/ambulance limitations and tests.
The [API contract](mobile/API_CONTRACT.md) records all discovered routes and states.

```powershell
# Terminal 1, repository root (set FALL_CAMERA_ENABLED='0' for camera-free demo)
$env:FALL_CAMERA_ENABLED = '1'
$env:FALL_DEMO_ENABLED = '1'
.\venv\Scripts\python.exe -B -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

```powershell
# Terminal 2, repository root
cd mobile
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

On a physical phone, use `http://<COMPUTER_WIFI_IPV4>:8000` in the login server
field; connect both devices to the same Wi-Fi. This backend has no account
service, so sign-in is explicitly a local demo identity, stored with Flutter
Secure Storage. Hospital response recording is mock-only and does not dispatch
an ambulance. Keep the app open for polling alerts.
