"""Translate existing verifier dictionaries without importing or changing ML."""
from .models import FallEvent, CaregiverError, utc_now


def event_from_payload(payload, *, person_id=None, received_at=None):
    if payload.get("type") != "confirmed_fall":
        raise CaregiverError("Only confirmed_fall payloads are accepted.")
    for key in ("event_id", "track_id", "timestamp"):
        if key not in payload:
            raise CaregiverError(f"Missing confirmed-event field: {key}")
    track_id = payload["track_id"]
    if isinstance(track_id, bool) or not isinstance(track_id, (int, str)) or not str(track_id).strip():
        raise CaregiverError("Invalid track_id.")
    return FallEvent(
        event_id=payload["event_id"],
        person_id=person_id if person_id is not None else str(track_id),
        timestamp=payload["timestamp"],
        detection_probability=payload.get("fall_probability"),
        created_at=received_at if received_at is not None else utc_now(),
        metadata={"source": "PostFallVerifier", "track_id": track_id,
                  "suspected_at": payload.get("suspected_at"), "timestamp_basis": "source_seconds"},
    )


def consume_verification_result(result, service, *, person_id=None):
    """NORMAL/SUSPECTED never alert. Latched confirmed frames have event=None."""
    if result.get("state") not in ("NORMAL", "FALL_SUSPECTED", "CONFIRMED_FALL"):
        raise CaregiverError("Unknown verification state.")
    if result["state"] != "CONFIRMED_FALL":
        return None
    payload = result.get("event")
    if payload is None:
        return None
    event = event_from_payload(payload, person_id=person_id, received_at=service.clock())
    return service.handle_confirmed_fall(event)
