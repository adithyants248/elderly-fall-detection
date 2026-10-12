"""Post-GRU decisions. Inputs are probabilities and RAW training motion features.

This module does not scale features, run a model, or send notifications.
Do not supply the older detector's pixels/second derivatives here.
"""

from dataclasses import dataclass
from enum import Enum
import math
from pathlib import Path
import time
from uuid import uuid4


from src.core.fall_detection.model_schema import FALL_THRESHOLD, WINDOW_SIZE, FEATURE_NAMES


class FallState(str, Enum):
    NORMAL = "NORMAL"
    FALL_SUSPECTED = "FALL_SUSPECTED"
    CONFIRMED_FALL = "CONFIRMED_FALL"


@dataclass(frozen=True)
class PostFallConfig:
    """Initial engineering limits, requiring calibration on camera data.

    Linear motion is pixels/frame, angle change degrees/frame, aspect change
    ratio/frame. The 3-second wait uses elapsed time, not an assumed FPS.
    A missing observation or gap cancels suspicion rather than proving stillness.
    """

    inactivity_seconds: float = 3.0
    max_observation_gap_seconds: float = 0.5
    body_movement_threshold: float = 15.0
    hip_vertical_velocity_threshold: float = 10.0
    hip_horizontal_velocity_threshold: float = 10.0
    torso_angle_change_threshold: float = 10.0
    aspect_ratio_change_threshold: float = 0.2

    def __post_init__(self):
        for name, value in vars(self).items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive.")

    def motion_limits(self):
        return {
            "body_center_movement": self.body_movement_threshold,
            "hip_vertical_velocity": self.hip_vertical_velocity_threshold,
            "hip_horizontal_velocity": self.hip_horizontal_velocity_threshold,
            "torso_angle_change": self.torso_angle_change_threshold,
            "aspect_ratio_change": self.aspect_ratio_change_threshold,
        }


@dataclass
class _Track:
    timestamp: float
    clock_source: str
    state: FallState = FallState.NORMAL
    suspected_at: float = None
    event_id: str = None


class PostFallVerifier:
    """One state per persistent person ID; explicit reset after event handling.

    update() accepts the current unscaled 20-feature mapping. Only the five
    motion fields plus person_detected are required. Use update_vector() for
    a vector in FEATURE_NAMES order. Missing/nonfinite motion cancels suspicion;
    sequence interpolation must never turn a missing live pose into stillness.

    A confirmed state is latched until reset(), even if tracking is lost.
    result['event'] is populated only on entry to CONFIRMED_FALL. The caller
    owns durable storage, delivery and retry using the event_id as a dedup key.
    This object is intended for a single ordered processing loop.
    """

    def __init__(self, config=None, *, threshold_path=None):
        self.config = config or PostFallConfig()
        if threshold_path is not None:
            threshold = float(Path(threshold_path).read_text(encoding="utf-8").strip())
            if not math.isfinite(threshold) or threshold != FALL_THRESHOLD:
                raise ValueError("The saved threshold must be exactly 0.30.")
        self._tracks = {}

    def update_vector(self, track_id, fall_probability, feature_vector, timestamp=None):
        if len(feature_vector) != len(FEATURE_NAMES):
            raise ValueError("Expected one unscaled 20-feature vector in training order.")
        return self.update(track_id, fall_probability, dict(zip(FEATURE_NAMES, feature_vector)), timestamp)

    def update(self, track_id, fall_probability, features, timestamp=None, *, candidate_allowed=True):
        """Use None probability during warmup or unavailable GRU inference.

        The caller must wait for 60 frames before supplying a GRU probability.
        A low probability during suspicion does not cancel the event by itself:
        the decision after suspicion is based on observed motion.
        Live GRUInference always supplies candidate_allowed from its causal onset
        gate. The default retains the standalone probability-replay contract;
        direct calls alone do not implement startup/transition protection.
        """
        source = "monotonic" if timestamp is None else "provided"
        now = time.monotonic() if timestamp is None else float(timestamp)
        if not math.isfinite(now):
            raise ValueError("timestamp must be finite.")
        if fall_probability is not None:
            fall_probability = float(fall_probability)
            if not math.isfinite(fall_probability) or not 0 <= fall_probability <= 1:
                raise ValueError("fall_probability must be finite and in [0, 1].")
        track = self._tracks.get(track_id)
        if track is not None:
            if track.clock_source != source:
                raise ValueError("Cannot mix clocks within a track; reset first.")
            if now <= track.timestamp:
                raise ValueError("Timestamps must strictly increase for each track.")
        gap = track is not None and now - track.timestamp > self.config.max_observation_gap_seconds
        if track is None:
            track = _Track(now, source)
            self._tracks[track_id] = track
        track.timestamp = now

        limits = self.config.motion_limits()
        motion = {name: features.get(name) for name in limits}
        observed = features.get("person_detected") == 1 and all(
            value is not None and math.isfinite(value) for value in motion.values()
        )
        moving = observed and any(abs(motion[name]) > limit for name, limit in limits.items())
        event = None
        reason = "normal"
        if track.state == FallState.CONFIRMED_FALL:
            reason = "awaiting_reset"
        elif gap or not observed or fall_probability is None:
            track.state = FallState.NORMAL
            track.suspected_at = None
            reason = "observation_gap" if gap else "missing_motion" if not observed else "prediction_unavailable"
        elif track.state == FallState.FALL_SUSPECTED:
            if moving:
                track.state = FallState.NORMAL
                track.suspected_at = None
                reason = "movement_resumed"
            elif now - track.suspected_at >= self.config.inactivity_seconds:
                track.state = FallState.CONFIRMED_FALL
                track.event_id = str(uuid4())
                event = {
                    "type": "confirmed_fall", "event_id": track.event_id,
                    "track_id": track_id, "timestamp": now,
                    "suspected_at": track.suspected_at,
                    "fall_probability": fall_probability,
                }
                reason = "prolonged_inactivity"
            else:
                reason = "observing_inactivity"
        elif fall_probability >= FALL_THRESHOLD and candidate_allowed:
            # Motion on the triggering frame can be the fall itself.
            track.state = FallState.FALL_SUSPECTED
            track.suspected_at = now
            reason = "probability_threshold"
        elif fall_probability >= FALL_THRESHOLD:
            reason = "waiting_for_transition"

        return {
            "track_id": track_id, "state": track.state.value,
            "fall_probability": fall_probability, "fall_threshold": FALL_THRESHOLD,
            "elapsed_seconds": 0.0 if track.suspected_at is None else now - track.suspected_at,
            "fall_confirmed": track.state == FallState.CONFIRMED_FALL,
            "reason": reason, "event": event, "event_id": track.event_id,
        }

    def reset(self, track_id):
        """Acknowledge/clear an episode; a future high probability can rearm it."""
        self._tracks.pop(track_id, None)

    def cleanup_stale_tracks(self, timestamp=None, stale_seconds=10.0):
        """Expire nonconfirmed tracks only; pending emergencies require reset."""
        if not math.isfinite(stale_seconds) or stale_seconds <= 0:
            raise ValueError("stale_seconds must be finite and positive.")
        source = "monotonic" if timestamp is None else "provided"
        now = time.monotonic() if timestamp is None else float(timestamp)
        if not math.isfinite(now):
            raise ValueError("timestamp must be finite.")
        stale = [key for key, track in self._tracks.items()
                 if track.clock_source == source and track.state != FallState.CONFIRMED_FALL
                 and now - track.timestamp > stale_seconds]
        for key in stale:
            self.reset(key)
        return stale
