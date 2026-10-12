# Live inference correction and validation

## Findings

The actual API entry point is `src/api/app.py` (`application.py` does not exist).
Its worker runs `GRUCameraSource`, YOLO pose, first-person selection, canonical
feature extraction, `TemporalBuffer`, GRU, `PostFallVerifier`, caregiver adapter,
shared in-memory repository, and dashboard polling. `scripts/run_pipeline.py`
is a separate legacy rule-based demo; its features are not model inputs.

The principal false-positive mechanism was reproducible: a high probability on
a completely static initial window started suspicion, and another three seconds
of the same posture confirmed it. Inactivity alone supplied no evidence of onset.
The notebook labels whole source sequences; high window confidence does not
establish that a fall has just occurred. The specific reported 0.9977 observation
was not recorded as raw poses, so its model-level cause cannot be reconstructed.

Raw extraction already matched the notebook. The live preprocessor, however,
reinterpolated the rolling window in both directions. It used no frames beyond
the current prediction time, but changed past missing values on each prediction
and could not reproduce full-source offline interpolation. Live camera pixel
geometry, frame cadence and pose-library version remain possible domain shifts.

## Changes

| File | Change |
| --- | --- |
| `src/core/fall_detection/preprocessing.py` | Immutable causal rows; schema validation; explicit offline projection |
| `src/core/fall_detection/transition.py` | Bounded, causal temporal onset evidence |
| `src/core/fall_detection/gru_inference.py` | Warmup/onset integration, reacquisition reset, timing/readiness diagnostics |
| `src/core/fall_detection/camera.py` | Only detected people count as visible for stale cleanup |
| `src/core/fall_verification/post_fall.py` | Separate candidate eligibility input; original elapsed-time verification and latch retained |
| `src/api/camera.py`, `src/api/models.py` | Safe diagnostic snapshot in system status; periodic/event logging |
| `tests/core/test_live_safety.py` | Adversarial high-probability regression coverage |
| `tests/core/test_gru_preprocessing.py`, `tests/core/test_camera_source.py` | Positive integration fixtures now include a genuine post-warmup transition |
| `scripts/check_live_application.py` | Disposable HTTP/camera/demo/browser smoke test with cooperative cleanup |
| `scripts/check_dashboard_browser.py` | Configurable disposable-server URL |
| `README.md`, `LIVE_PIPELINE.md` | Corrected runtime description and operational instructions |

Model weights, threshold 0.30, training medians, scaler, caregiver/hospital
state transitions and delivery retry policy were not altered by this fix.

### Causal preprocessing and schema

`model_schema.FEATURE_NAMES` remains the sole ordered model schema. The extractor
uses COCO pairs 5/6, 11/12, 13/14, 15/16, raw image pixels, unsigned torso angle,
xyxy box dimensions, box confidence and a binary detection indicator. Named rows
must contain all 20 features. Model DataFrames must have the canonical order;
offline source tables explicitly select it. Artifact loading validates ordered
scaler names, ordered median names, finite medians and model input/output shapes.
Notebook-execution tests compare extraction numerically against its actual code.

Differences are computed from consecutive **raw** rows, before any filling.
The first velocity and first two accelerations are NaN; disappearance and
recovery do not bridge derivatives. Each model row is filled exactly once:

1. Finite raw values remain unchanged.
2. Missing spatial/confidence values use the last finite observation since reset,
   or their saved training median if no past observation exists.
3. Missing motion values use their saved training medians directly, never a
   carried impact or motion inferred across a missing frame.
4. `person_detected` remains 0/1. The saved scaler transforms all 20 columns.

No online fitting, estimated medians, backward filling or future interpolation
occurs. The raw and filled histories are separate. Offline interpolation remains
available solely for artifact parity and offline sequence processing.

### Warmup and temporal decision

No GRU prediction is made before 60 rows. At row 60 the first probability becomes
available, but onset history starts there: motion during warmup cannot establish
a new episode. A static startup posture therefore cannot start the verifier,
even when every subsequent probability is 0.9977. Any starting posture can later
produce a qualifying transition; there are no sitting/sleeping/lying labels.

The onset gate compares observed poses over the preceding one second (at most
120 observations). Engineering defaults require hip displacement >=25% of the
prior box height plus either >=20 degrees of torso change or >=0.25 aspect-ratio
change. Downward displacement >=40% of prior box height also supports an axial
collapse. Lateral displacement is unsigned. These are provisional geometry
limits, not trained or clinically validated decision thresholds.

When recent onset evidence, probability >=0.30 and an observed low-motion frame
coincide, the verifier enters FALL_SUSPECTED. The existing five raw-motion limits
must then remain satisfied for **three elapsed seconds**. Movement cancels
suspicion. A low subsequent model probability alone does not cancel it. Onset
history is consumed on suspicion and cleared during verification/recovery so
the same transition cannot immediately rearm another episode.

Confirmation remains latched and emits one event. Repeated confirmed frames,
delivery retries and caregiver acknowledgement retain the existing behavior.
Explicit API rearm requires acknowledged camera events and starts fresh warmup.

`PostFallVerifier` by itself remains a low-level probability/inactivity verifier
for existing replay and domain tests. Its default candidate eligibility preserves
that contract. **Live protection requires GRUInference**, which always supplies
the onset gate; standalone score replay does not provide equivalent protection.

### Missing observations, identity and time

Missing rows remain in the buffer with raw NaNs and `person_detected=0`. They
cannot prove stillness, regardless of the filled tensor or GRU probability.
Reacquisition starts fresh 60-frame history and clears onset evidence. This
conservative policy also avoids joining two people across disappearance in
first-person mode. It can delay detection after even a brief pose dropout.

First-person selection remains notebook-compatible at confidence 0.25. Use a
single-person scene: first-person ordering cannot identify a swap between two
continuously visible people. Optional tracked mode maintains separate buffers
per ID; a new ID starts empty. Tracker ID reuse remains a prototype limitation.

Camera capture uses monotonic seconds; file video uses frame index / source FPS.
Per-track timestamps must be finite, strictly increasing and from one clock.
A gap over 0.5 seconds resets model history and cancels unconfirmed suspicion.
Confirmed episodes survive missing observations. Event `timestamp` remains source
seconds; `created_at` remains UTC receipt time. Neither schema is repurposed.

### Observability

`GET /api/system/status` includes frames processed and a `diagnostics` snapshot:
buffer frames, warmup, temporal readiness, transition support, person detection,
probability, unchanged threshold, verifier state/reason, event creation,
observation interval and model prediction duration. Logging occurs every 150
frames and on emitted events. No images, keypoints or other camera content are
logged. In tracked mode the snapshot describes the last processed track.

## Validation evidence

- Artifact validation reproduced train `(341,60,20)`, validation `(64,60,20)` and
  test `(69,60,20)` with maximum absolute error **0.0**, including saved medians.
- Regression tests cover static startup at multiple postures with P=0.9977,
  exact 60-row readiness, normal walking/gradual sitting, directional fall-like
  transitions, movement cancellation, disappearance/recovery, new falls after
  reacquisition, warmup transitions, causal immutable filling, saved scaler and
  medians, malformed schema, deduplication and latched episodes.
- Full suite: **209 passed, 56 subtests passed, 5 warnings in 43.46 seconds**,
  recorded in `output/live-pytest-final.txt`. Warnings concern dependency
  deprecations and an unwritable pytest cache; no test failed. Existing
  caregiver, hospital, camera lifecycle, API and legacy tests remain included.
- In the sandbox camera 0 was unavailable. The actual HTTP API/dashboard remained
  available and the complete demo response succeeded (`output/live-application.txt`).
- With hardware access, the actual camera reached running and processed **200
  frames**. No camera event was created. One sampled probability was **0.69385**,
  state NORMAL, reason `waiting_for_transition`. Shutdown reported stopped with
  no pending events (`output/live-application-hardware.txt`).
- Headless Chrome passed mobile/desktop layout, polling, simulated fall,
  acknowledgement, hospital selection, response recording, reload and no JS
  errors against a camera-disabled API (`output/live-browser.txt`).

The physical check was unattended: it does not certify standing, sitting,
walking or a bed simulation. It showed warmup restarts; gaps exceeding 0.5 seconds
or detection loss can prevent continuous monitoring on this hardware. Timing
diagnostics now make performance gaps visible. Safe labeled camera recordings
are still needed to calibrate onset limits and measure false positives/negatives.
Slow collapses, occlusion, intentional rapid posture changes, camera motion,
resolution/cadence shifts and falls during warmup can be missed or misclassified.
Training-array parity is not live accuracy. Hospital services and caregiver
delivery remain mocks; storage/retry are in-memory and do not survive restart.

## Run commands (PowerShell, repository root)

```powershell
$env:FALL_CAMERA_ENABLED = '1'
$env:FALL_CAMERA_SOURCE = '0'
$env:FALL_CAMERA_SELECTION = 'first'
.\venv\Scripts\python.exe -B -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

Use one server worker. Open `http://localhost:8000/`. Stop with Ctrl+C so the
worker releases the capture. Set `FALL_CAMERA_ENABLED='0'` for dashboard/demo only.
The standalone preview does not share the API's repository:

```powershell
.\venv\Scripts\python.exe -B -m scripts.run_gru_pipeline --source 0
.\venv\Scripts\python.exe -B -m scripts.validate_gru_artifacts
.\venv\Scripts\python.exe -B -m pytest -v
.\venv\Scripts\python.exe -B -m scripts.check_live_application --seconds 60 --browser
```

Do not open the standalone preview and API camera simultaneously. In the preview,
q closes the camera; r resets ML episodes only, not caregiver acknowledgement.

## Safe manual checks

Keep the camera fixed, the full person visible and a second person observing the
dashboard. Record status snapshots and event IDs, not just a screenshot of an
alert. Use a fresh server for each startup scenario; existing events are latched.

1. **Standing startup:** start while standing comfortably. Wait for `running`,
   `buffer_frames=60`, `warmup=false`, then observe for 20 seconds. Expect no event.
2. **Sitting startup:** restart while already seated comfortably. Repeat the same
   readiness and 20-second check. High probability alone must leave NORMAL with
   `waiting_for_transition`.
3. **Normal movement:** after warmup, walk normally within view, stop, sit normally,
   and stand if comfortable. Observe each stationary period for at least five
   seconds. Expect no confirmed event; record any suspected/confirmed episode.
4. **Supported bed simulation:** only if comfortable and practical, start already
   safely seated on a stable bed, warm up, and gently recline onto its support
   with a helper nearby. Do not jump, drop, accelerate movement to meet a limit,
   or perform a real fall. Remain comfortably still for over three seconds.
   A gentle maneuver may intentionally fail the onset gate; no alert is not
   evidence of a broken model or validated fall sensitivity. Record diagnostics.
5. **Demo:** press SIMULATE DEMO FALL, acknowledge, select an offered mock hospital,
   then RECORD EMERGENCY RESPONSE. Expect the simulated badge and
   RESPONSE_RECORDED, including with camera disabled/unavailable.

Do not ask an elderly person to fall. Use recorded/synthetic transitions for
repeatable positive software tests. If a camera alert appears, check the person,
acknowledge it and use the dashboard rearm control for a fresh episode.
