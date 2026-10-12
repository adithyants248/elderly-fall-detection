from collections import deque
import math
import time

from .features import body_center, extract_features
from src.core.fall_verification.verifier import FallVerifier


class FallDetector:
    """
    Rule-based fall detector with post-fall inactivity detection.

    Uses:
    - torso angle
    - vertical movement
    - bounding-box aspect ratio
    - post-fall inactivity
    """

    def __init__(
        self,
        history_size: int = 30,
        torso_angle_threshold: float = 45.0,
        vertical_drop_threshold: float = 50.0,
        aspect_ratio_threshold: float = 1.2,

        # Post-fall inactivity settings
        inactivity_frames: int = 60,
        movement_threshold: float = 15.0,
        *,
        verification_window_seconds: float = 2.0,
        max_observation_gap_seconds: float = 0.5,
        stale_track_seconds: float = 10.0,
        inactivity_seconds: float = None,
    ):

        if history_size < 2:
            raise ValueError("history_size must be at least 2.")
        if inactivity_frames < 1:
            raise ValueError("inactivity_frames must be at least 1.")
        if inactivity_seconds is not None and (
            not math.isfinite(inactivity_seconds) or inactivity_seconds <= 0
        ):
            raise ValueError("inactivity_seconds must be finite and positive.")
        self.inactivity_seconds = inactivity_seconds
        if not math.isfinite(stale_track_seconds) or stale_track_seconds <= 0:
            raise ValueError("stale_track_seconds must be finite and positive.")

        self.verifier = FallVerifier(
            verification_window_seconds=verification_window_seconds,
            max_observation_gap_seconds=max_observation_gap_seconds,
            torso_angle_threshold=torso_angle_threshold,
            aspect_ratio_threshold=aspect_ratio_threshold,
            vertical_drop_threshold=vertical_drop_threshold,
        )
        self.stale_track_seconds = stale_track_seconds
        self.clock_sources = {}

        self.torso_angle_threshold = torso_angle_threshold
        self.vertical_drop_threshold = vertical_drop_threshold
        self.aspect_ratio_threshold = aspect_ratio_threshold

        self.history_size = history_size

        # Number of consecutive frames required
        # to consider the person inactive after a fall.
        self.inactivity_frames = inactivity_frames

        # Maximum movement allowed during inactivity.
        self.movement_threshold = movement_threshold

        self.history = {}

        # Stores inactivity information for each tracked person.
        self.inactivity_state = {}

    def _get_history(self, track_id):

        if track_id not in self.history:

            self.history[track_id] = deque(
                maxlen=self.history_size
            )

        return self.history[track_id]

    def _get_inactivity_state(self, track_id):

        if track_id not in self.inactivity_state:

            self.inactivity_state[track_id] = {
                "active": False,
                "inactive_frames": 0,
                "still_since": None,
            }

        return self.inactivity_state[track_id]

    def _calculate_bbox_center(self, bbox):
        return body_center(bbox)

    def reset(self, track_id):
        """Clear every stage for a lost track or a new video/clock session."""
        self.history.pop(track_id, None)
        self.inactivity_state.pop(track_id, None)
        self.clock_sources.pop(track_id, None)
        self.verifier.reset(track_id)

    def cleanup_stale_tracks(self, timestamp=None):
        """Expire absent tracks using the same clock as analyze().

        Call on every input frame, including frames without people. Explicit
        timestamps must share the source video timeline across tracks.
        """
        source = "monotonic" if timestamp is None else "provided"
        now = time.monotonic() if timestamp is None else float(timestamp)
        if not math.isfinite(now):
            raise ValueError("timestamp must be finite.")
        stale = [
            track_id for track_id, history in self.history.items()
            if history and self.clock_sources.get(track_id) == source
            and now - history[-1]["timestamp"] > self.stale_track_seconds
        ]
        for track_id in stale:
            self.reset(track_id)
        return stale

    def analyze(self, person, timestamp=None):
        """Analyze one tracked observation.

        timestamp is seconds, strictly increasing per track. Omit it for live
        monotonic time, or supply video timestamps for reproducible offline
        extraction. Use the same clock throughout a track's lifetime.
        fall_detected remains an alias for the raw fall_candidate. Final
        fall_confirmed requires verification followed by inactivity_frames
        low-movement observations; that existing inactivity setting is still
        measured in observations unless inactivity_seconds is supplied.
        """

        track_id = person["track_id"]
        keypoints = person["keypoints"]
        bbox = person["bbox"]

        source = "monotonic" if timestamp is None else "provided"
        if track_id in self.clock_sources and self.clock_sources[track_id] != source:
            raise ValueError("Cannot mix clock sources for a track; reset it first.")
        timestamp = time.monotonic() if timestamp is None else float(timestamp)
        if not math.isfinite(timestamp):
            raise ValueError("timestamp must be finite.")

        history = self._get_history(track_id)

        # --------------------------------------------------
        # 1. Calculate current features
        # --------------------------------------------------

        previous = history[-1] if history else None
        if previous is not None and timestamp <= previous["timestamp"]:
            raise ValueError("Timestamps must be strictly increasing per track.")
        features = extract_features(
            keypoints,
            bbox,
            previous["features"] if previous is not None else None,
            dt=timestamp - previous["timestamp"] if previous is not None else None,
        )
        current_position = features["hip_vertical_position"]
        current_angle = features["torso_angle"]
        current_ratio = features["aspect_ratio"]
        current_center = features["body_center"]
        inactivity = self._get_inactivity_state(track_id)
        self.clock_sources[track_id] = source

        # --------------------------------------------------
        # 2. Store current frame information
        # --------------------------------------------------

        history.append(
            {
                "position": current_position,
                "angle": current_angle,
                "ratio": current_ratio,
                "center": current_center,
                "timestamp": timestamp,
                "features": features,
            }
        )

        # --------------------------------------------------
        # 3. Not enough history
        # --------------------------------------------------

        # The first observation has no motion history, but still supplies the
        # verifier's posture baseline and the same output schema as later calls.

        # --------------------------------------------------
        # 4. Calculate fall features
        # --------------------------------------------------

        vertical_drop = features["vertical_drop"]

        angle_signal = (
            current_angle >= self.torso_angle_threshold
        )

        drop_signal = (
            vertical_drop >= self.vertical_drop_threshold
        )

        ratio_signal = (
            current_ratio >= self.aspect_ratio_threshold
        )

        # --------------------------------------------------
        # 5. Calculate fall score
        # --------------------------------------------------

        signals = sum(
            [
                angle_signal,
                drop_signal,
                ratio_signal,
            ]
        )
        if previous is None:
            signals = 0

        score = signals / 3.0

        fall_detected = signals >= 2
        verification = self.verifier.update(
            track_id,
            score,
            timestamp=timestamp,
            fall_candidate=fall_detected,
            features=features,
        )
        fall_verified = verification["fall_verified"]

        # --------------------------------------------------
        # 6. Calculate movement
        # --------------------------------------------------

        movement = features["movement"]

        # --------------------------------------------------
        # 7. Start post-fall inactivity monitoring
        # --------------------------------------------------

        if not fall_verified:
            inactivity["active"] = False
            inactivity["inactive_frames"] = 0
            inactivity["still_since"] = None
        elif not inactivity["active"]:
            inactivity["active"] = True
            inactivity["inactive_frames"] = 0
            inactivity["still_since"] = timestamp
        else:
            # Begin counting AFTER verification. Repeated candidates do not
            # restart the monitoring period. Movement clears confirmation.
            if movement <= self.movement_threshold:
                inactivity["inactive_frames"] = min(
                    inactivity["inactive_frames"] + 1, self.inactivity_frames,
                )
            else:
                inactivity["inactive_frames"] = 0
                inactivity["still_since"] = timestamp
        inactive_elapsed = (
            0.0 if inactivity["still_since"] is None
            else timestamp - inactivity["still_since"]
        )
        post_fall_inactive = (
            inactivity["active"]
            and (
                inactive_elapsed >= self.inactivity_seconds
                if self.inactivity_seconds is not None
                else inactivity["inactive_frames"] >= self.inactivity_frames
            )
        )

        # --------------------------------------------------
        # 10. Return result
        # --------------------------------------------------

        return {
            "fall_detected": fall_detected,
            "fall_candidate": fall_detected,
            "fall_verified": fall_verified,
            "fall_confirmed": fall_verified and post_fall_inactive,
            "verification": verification,
            "inactivity": {
                "elapsed_seconds": inactive_elapsed,
                "required_seconds": self.inactivity_seconds,
                "inactive_frames": inactivity["inactive_frames"],
                "required_frames": self.inactivity_frames,
                "movement": movement,
                "movement_threshold": self.movement_threshold,
                "reason": (
                    "waiting_for_verification" if not fall_verified
                    else "movement" if movement > self.movement_threshold
                    else "inactive" if post_fall_inactive
                    else "observing_stillness"
                ),
            },

            "post_fall_inactive": post_fall_inactive,

            "score": score,

            "features": features.copy(),
        }
