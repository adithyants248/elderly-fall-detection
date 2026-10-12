"""Load saved GRU once and route probabilities plus RAW motion to verification."""
import math
import os
import time

import numpy as np

from .model_schema import ArtifactPaths, FALL_THRESHOLD
from .preprocessing import ModelPreprocessor, TemporalBuffer
from .transition import TransitionEvidence
from src.core.fall_verification.post_fall import PostFallVerifier


def load_gru(path):
    # Reuse the installed PyTorch CPU/CUDA runtime instead of requiring TensorFlow.
    # An explicitly selected Keras backend remains respected.
    os.environ.setdefault("KERAS_BACKEND", "torch")
    import keras
    return keras.models.load_model(path, compile=False)


class GRUInference:
    def __init__(self, paths=None, *, model_loader=load_gru, verifier=None):
        self.paths = paths or ArtifactPaths()
        if float(self.paths.threshold.read_text().strip()) != FALL_THRESHOLD:
            raise ValueError("Saved threshold must be 0.30.")
        self.preprocessor = ModelPreprocessor(self.paths)
        self.model = model_loader(self.paths.model)
        if tuple(self.model.input_shape) != (None, 60, 20) or tuple(self.model.output_shape) != (None, 1):
            raise ValueError("GRU must accept (None,60,20) and return (None,1).")
        self.verifier = verifier or PostFallVerifier(threshold_path=self.paths.threshold)
        self.buffers = {}
        self.last_observed = {}
        self.last_seen = {}
        self.clocks = {}
        self.transitions = {}

    def update(self, track_id, keypoints=None, bbox=None, confidence=np.nan, timestamp=None):
        source = "monotonic" if timestamp is None else "provided"
        now = time.monotonic() if timestamp is None else float(timestamp)
        if not math.isfinite(now):
            raise ValueError("timestamp must be finite.")
        previous = self.last_observed.get(track_id)
        if previous is not None and (now <= previous or source != self.clocks[track_id]):
            raise ValueError("Use strictly increasing timestamps from one clock per track.")
        buffer = self.buffers.setdefault(track_id, TemporalBuffer(self.preprocessor))
        transition = self.transitions.setdefault(track_id, TransitionEvidence())
        transition_reset_reason = None
        if previous is not None and now - previous > self.verifier.config.max_observation_gap_seconds:
            buffer.reset()  # do not fabricate 60 consecutive frames across an unobserved gap
            transition.reset()
            transition_reset_reason = "observation_gap"
        # First-person mode cannot establish identity across disappearance.
        # Reacquisition starts a fresh model history; missing rows were retained
        # while absent and never counted by the verifier as inactivity.
        if keypoints is not None and buffer.previous is not None and buffer.previous["person_detected"] == 0:
            buffer.reset()
            transition.reset()
            transition_reset_reason = "reacquisition"
        raw, tensor = buffer.append(keypoints, bbox, confidence)
        self.last_observed[track_id], self.clocks[track_id] = now, source
        if raw["person_detected"] == 1:
            self.last_seen[track_id] = now
        else:
            self.last_seen.setdefault(track_id, now)
        probability = None
        inference_seconds = None
        if tensor is not None:
            prediction_started = time.monotonic()
            probability = float(np.asarray(self.model.predict(tensor, verbose=0)).reshape(-1)[0])
            inference_seconds = time.monotonic() - prediction_started
        supported = transition.update(raw, now, tensor is not None,
                                      max_gap_seconds=self.verifier.config.max_observation_gap_seconds)
        limits = self.verifier.config.motion_limits()
        quiet = all(np.isfinite(raw[name]) and abs(raw[name]) <= limit for name, limit in limits.items())
        decision = self.verifier.update(track_id, probability, raw, timestamp=now,
                                        candidate_allowed=supported and quiet)
        transition.diagnostics["quiet"] = bool(quiet)
        transition.diagnostics["reset_before_update"] = transition_reset_reason
        transition.diagnostics["candidate_allowed"] = bool(supported and quiet)
        transition.diagnostics["evidence_cleared_after_decision"] = (
            decision["state"] if decision["state"] != "NORMAL" else
            "movement_resumed" if decision["reason"] == "movement_resumed" else None)
        if decision["state"] != "NORMAL" or decision["reason"] == "movement_resumed":
            transition.reset()  # consume onset; recovery cannot reuse the same fall
        return {**decision, "features": raw, "buffer_frames": len(buffer.rows),
                "warmup": tensor is None, "temporal_ready": tensor is not None,
                "observation_interval_seconds": None if previous is None else now - previous,
                "inference_seconds": inference_seconds,
                "transition_supported": supported, "transition_diagnostics": transition.diagnostics,
                "person_detected": int(raw["person_detected"])}

    def reset(self, track_id):
        self.buffers.pop(track_id, None)
        self.last_observed.pop(track_id, None)
        self.last_seen.pop(track_id, None)
        self.clocks.pop(track_id, None)
        self.transitions.pop(track_id, None)
        self.verifier.reset(track_id)

    def expire_absent(self, visible_ids, timestamp, stale_seconds=10.0):
        """Forget long-absent nonconfirmed tracks; retain unhandled emergencies."""
        stale = [track for track, last in self.last_seen.items()
                 if track not in visible_ids and timestamp - last > stale_seconds]
        for track in stale:
            # Keep the verifier's latched event; release only temporal/model history.
            self.buffers.pop(track, None)
            self.last_observed.pop(track, None)
            self.last_seen.pop(track, None)
            self.clocks.pop(track, None)
            self.transitions.pop(track, None)
            state = self.verifier._tracks.get(track)
            if state is not None and state.state.value != "CONFIRMED_FALL":
                self.verifier.reset(track)
        self.verifier.cleanup_stale_tracks(timestamp=timestamp, stale_seconds=stale_seconds)
        return stale
