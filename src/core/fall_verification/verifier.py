"""Explainable, elapsed-time verification of a fall-like transition."""

from collections import deque
import math


class FallVerifier:
    """Require a candidate followed by sustained lying posture.

    Start at the first qualifying lying candidate, even if the camera missed
    the transition into lying. Lying means BOTH torso and box thresholds are
    met. A raw two-of-three candidate alone can still be non-lying and will
    not verify. Already-lying people can verify after the full window; this
    rule cannot distinguish intentional lying from a fall without a baseline.
    Legacy transition threshold arguments remain accepted for compatibility,
    but no longer gate the start of verification.

    Continuous support lasts verification_window_seconds (default 2 seconds).
    Gaps above max_observation_gap_seconds and non-lying observations cancel
    the event. This conservative rule does not interpolate missing observations.
    Thresholds are heuristics, not calibrated probabilities.

    Call update with explicit timestamps from one clock. The old score-only
    interface cannot establish a transition and is replaced by the feature-aware
    interface below. Inactivity/final confirmation belong to FallDetector.
    """

    def __init__(
        self,
        verification_window_seconds=2.0,
        *,
        transition_window_seconds=0.5,
        max_observation_gap_seconds=0.5,
        torso_angle_threshold=45.0,
        aspect_ratio_threshold=1.2,
        vertical_drop_threshold=50.0,
        posture_change_threshold=30.0,
        confirmation_threshold=0.66,
    ):
        for name, value in (
            ("verification_window_seconds", verification_window_seconds),
            ("transition_window_seconds", transition_window_seconds),
            ("max_observation_gap_seconds", max_observation_gap_seconds),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and greater than zero.")
        if transition_window_seconds > verification_window_seconds:
            raise ValueError("Transition window cannot exceed verification window.")
        self.verification_window_seconds = verification_window_seconds
        self.transition_window_seconds = transition_window_seconds
        self.max_observation_gap_seconds = max_observation_gap_seconds
        self.torso_angle_threshold = torso_angle_threshold
        self.aspect_ratio_threshold = aspect_ratio_threshold
        self.vertical_drop_threshold = vertical_drop_threshold
        self.posture_change_threshold = posture_change_threshold
        self.confirmation_threshold = confirmation_threshold
        self.history = {}
        self.started_at = {}

    def _lying(self, features):
        return (
            features["torso_angle"] >= self.torso_angle_threshold
            and features["aspect_ratio"] >= self.aspect_ratio_threshold
        )

    def update(self, track_id, fall_score, *, timestamp, fall_candidate, features):
        """Store one observation; return verification, duration, and reason.

        Histories are pruned by timestamp, never by frame count. Entries retain
        score, candidate and all features, including movement and derivatives.
        """
        if not math.isfinite(timestamp):
            raise ValueError("timestamp must be finite.")
        history = self.history.get(track_id)
        if history and timestamp <= history[-1]["timestamp"]:
            raise ValueError("Timestamps must be strictly increasing per track.")
        observation_gap = timestamp - history[-1]["timestamp"] if history else None
        gap_reset = observation_gap is not None and observation_gap > self.max_observation_gap_seconds
        if gap_reset:
            self.reset(track_id)
        history = self.history.setdefault(track_id, deque())
        cutoff = timestamp - self.verification_window_seconds
        while history and history[0]["timestamp"] < cutoff:
            history.popleft()

        lying = self._lying(features)
        reset_reason = "observation_gap" if gap_reset else None
        if not lying:
            if track_id in self.started_at:
                reset_reason = "not_lying"
            self.started_at.pop(track_id, None)
        elif track_id not in self.started_at and fall_candidate and fall_score >= self.confirmation_threshold:
            self.started_at[track_id] = timestamp

        history.append({
            "timestamp": timestamp,
            "fall_score": fall_score,
            "fall_candidate": fall_candidate,
            "features": features.copy(),
        })
        start = self.started_at.get(track_id)
        elapsed = 0.0 if start is None else timestamp - start
        verified = start is not None and elapsed >= self.verification_window_seconds
        return {
            "fall_verified": verified,
            "elapsed_seconds": elapsed,
            "verification_active": start is not None,
            "verification_start_time": start,
            "elapsed_verification_seconds": elapsed,
            "verification_window_seconds": self.verification_window_seconds,
            "timestamp": timestamp,
            "observation_gap_seconds": observation_gap,
            "lying": lying,
            "reset_reason": reset_reason,
            "reason": (
                "sustained_lying_candidate" if verified
                else "observing_candidate" if start is not None
                else "not_lying" if not lying
                else "waiting_for_candidate"
            ),
        }

    def reset(self, track_id):
        """Forget a lost track or explicitly end its clock/session."""
        self.history.pop(track_id, None)
        self.started_at.pop(track_id, None)
