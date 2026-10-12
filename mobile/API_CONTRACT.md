# Inspected backend contract

Entry point: `src/api/app.py`. No backend changes are required for this client.
All endpoints are unauthenticated. Storage is process-local and disappears on restart.

| Method / path | Contract |
| --- | --- |
| GET /api/health | status, demo_enabled, hospital_data (mock), location disclaimer |
| GET /api/system/status | camera_enabled; camera_status and ai_status: disabled/starting/running/unavailable/stopped/error; frames_processed; last_frame_at; pending_events; latched_events; reset_requested; diagnostics |
| GET /api/falls | All FallView records |
| GET /api/falls/{id} | One FallView |
| POST /api/falls/{id}/acknowledge | `{caregiver_id}`; returns FallView; same caregiver replay is idempotent |
| GET /api/falls/{id}/hospitals | Explicit, state-changing lookup after acknowledgement; returns EmergencyResponse; never poll this route |
| POST /api/falls/{id}/hospital | `{caregiver_id,hospital_id}`; returns EmergencyResponse |
| POST /api/falls/{id}/emergency-response | Returns `{mock:true,message,response}`; idempotent recording; no dispatch |
| POST /api/demo/fall | 201 FallView; 404 if disabled |
| POST /api/system/camera/reset | 202 SystemStatus; explicit rearm only after camera events acknowledged |

FallView: event_id, person_id, timestamp (source seconds, NOT epoch),
detection_probability (nullable), status (CONFIRMED/ALERT_SENT/ACKNOWLEDGED),
created_at (UTC receipt time), acknowledged_at/by (nullable), simulated,
emergency_response (nullable). Only confirmed falls enter this repository.

EmergencyResponse: response_id, event_id, location, status
(ACKNOWLEDGED/HOSPITALS_AVAILABLE/HOSPITAL_SELECTED/RESPONSE_RECORDED),
hospitals, selected_hospital_id/name, created_at, selected_at/by, recorded_at.
Hospital: hospital_id, name, address, latitude, longitude, distance_km, phone.
Hospital records and coordinates are fictional. There are no ambulance, ETA,
hospital-received or hospital-acceptance states.

Diagnostics expose state NORMAL/FALL_SUSPECTED/CONFIRMED_FALL and optional
fall_probability, fall_threshold, warmup, temporal_ready. A missing state is
unavailable, never SAFE. Diagnostics describe the most recently processed track.

Errors: 404 missing resource; 409 transition/conflict; 422 validation; 500 server.
Client additionally handles 400/401/403, malformed responses and network timeouts.
There are no auth, password recovery, patient assignment or profile endpoints.
The local demo identity is not authentication or an API access control.
