"""Synthetic camera geometry, NOT recordings or clinical validation.

The bed fixture models simultaneous hip/shoulder descent and torso foreshortening
with every original geometry route below threshold. No user-provided live
recording is replayed here; these tests establish the admission contract only.
"""
import json
import math

import numpy as np
import pytest

from src.core.fall_detection.preprocessing import spatial_features
from src.core.fall_detection.transition import TransitionEvidence
from src.api.context import ApplicationContext
from test_live_safety import pipeline


def observation(fraction=0., activity="bed", jitter=0.):
    kp = np.zeros((17, 2), dtype=np.float32)
    kp[5:7] = [(90, 60), (110, 60)]
    kp[11:13] = [(90, 120), (110, 120)]
    width, height = 80., 200.
    if activity == "bed":
        kp[5:7, 1] += 40 * fraction
        kp[11:13, 1] += 20 * fraction
        height -= 30 * fraction
    elif activity == "sitting":
        kp[5:7, 1] += 40 * fraction
        kp[11:13, 1] += 40 * fraction
        height -= 50 * fraction
    elif activity == "bending":
        kp[5:7, 1] += 40 * fraction
        kp[11:13, 1] += 2 * fraction
        height -= 30 * fraction
    elif activity == "walking":
        kp[:, 0] += 35 * fraction
    kp[5:7] += jitter
    kp[11:13] -= jitter * .5
    return kp, (50., 0., 50. + width, height + jitter)


def raw(fraction=0., activity="bed", jitter=0.):
    return spatial_features(*observation(fraction, activity, jitter), .9)


def baseline(gate, fps=30):
    for i in range(fps + 1):
        assert not gate.update(raw(), i / fps, True)
    assert gate.diagnostics["temporal"]["baseline_ready"]


def qualify(gate, fps=30):
    baseline(gate, fps)
    first = None
    for i in range(1, int(.5 * fps) + 1):
        t = 1 + i / fps
        supported = gate.update(raw(min(i / fps / .5, 1)), t, True)
        assert not gate.diagnostics["geometry_supported"]
        if supported and first is None:
            first = t
    assert first is not None
    return first, t


@pytest.mark.parametrize("fps", [10, 15, 30, 60])
def test_bed_like_temporal_route_below_original_thresholds(fps):
    gate = TransitionEvidence()
    qualify(gate, fps)
    d = gate.diagnostics
    assert d["temporal"]["supported"] and d["combined_supported"]
    assert d["max_distance_ratio"] < .25
    assert d["max_downward_ratio"] < .4
    assert d["max_angle_change"] < 20
    assert d["max_aspect_change"] < .25
    assert not d["route_1_passed"] and not d["route_2_passed"]
    assert d["false_reason"] is None
    json.dumps(d, allow_nan=False)


@pytest.mark.parametrize("activity", ["standing", "sitting", "bed", "jitter", "bending", "walking", "rapid_sitting"])
def test_high_probability_negative_activities_never_enter_suspicion(activity):
    p = pipeline()
    for i in range(230):
        t = i / 30
        f = min(max((t - 3) / .5, 0), 1)
        kind, jitter = "bed", 0.
        if activity == "standing":
            f = 0
        elif activity in ("sitting", "bed"):
            kind, f = activity, 1  # Static from first observation, including warmup.
        elif activity == "jitter":
            f, jitter = 0, 1.2 * math.sin(i * 1.7) + .5 * math.sin(i * .37)
        elif activity == "bending":
            kind, f = activity, max(0, 1 - abs(t - 3.5) / .5)
        elif activity == "walking":
            kind, f = activity, max(t - 3, 0)
        else:
            kind = "sitting"
        result = p.update(0, *observation(f, kind, jitter), .9, t)
        assert result["state"] == "NORMAL", (activity, t, result["transition_diagnostics"])
        assert result["event"] is None


@pytest.mark.parametrize("fps", [10, 30, 60])
def test_temporal_fall_runs_full_verification_and_deduplicates(fps):
    p = pipeline()
    context = ApplicationContext()
    start = 60 / fps + 1.
    events, suspected = [], None
    for i in range(math.ceil((start + 4.5) * fps)):
        t = i / fps
        f = min(max((t - start) / .5, 0), 1)
        result = p.update(0, *observation(f), .9, t)
        if result["state"] == "FALL_SUSPECTED" and suspected is None:
            suspected = t
            assert result["elapsed_seconds"] == 0
            assert result["transition_diagnostics"]["temporal"]["supported"]
            assert not result["transition_diagnostics"]["geometry_supported"]
            assert not p.transitions[0].pending_at
        if result["event"]:
            events.append(result["event"])
            context.consume_verification_result(result)
            context.consume_verification_result(result)
    assert suspected is not None
    assert len(events) == len(context.falls.list_all()) == 1
    assert events[0]["timestamp"] - suspected >= 3.
    assert result["state"] == "CONFIRMED_FALL"


def test_pending_expiry_is_fixed_and_static_endpoint_does_not_rearm():
    gate = TransitionEvidence()
    first, last = qualify(gate)
    expired = False
    for i in range(1, 100):
        t = last + i / 30
        supported = gate.update(raw(1), t, True)
        if t >= first + 1:
            assert not supported
        expired |= gate.diagnostics["temporal"]["rejection_reason"] == "pending_expired"
    assert expired


def test_return_to_baseline_clears_pending_and_cannot_reuse_episode():
    gate = TransitionEvidence()
    _, last = qualify(gate)
    assert not gate.update(raw(), last + .1, True)
    assert gate.diagnostics["temporal"]["rejection_reason"] == "endpoint_recovered"
    for i in range(1, 60):
        assert not gate.update(raw(), last + .1 + i / 30, True)


@pytest.mark.parametrize("kind", ["missing", "invalid_shoulder", "gap", "reset"])
def test_temporal_evidence_reset(kind):
    gate = TransitionEvidence()
    _, last = qualify(gate)
    r = raw(1)
    t = last + .1
    if kind == "missing":
        r["person_detected"] = 0
    elif kind == "invalid_shoulder":
        r["shoulder_center_y"] = float("nan")
    elif kind == "gap":
        t = last + .6
    else:
        gate.reset()
    assert not gate.update(r, t, True)
    assert not gate.diagnostics["temporal"]["baseline_ready"]
    assert not gate.diagnostics["temporal"]["pending"]
    for i in range(1, 40):
        assert not gate.update(raw(1), t + i / 30, True)


@pytest.mark.parametrize("hold", [False, True])
def test_single_frame_jump_even_held_cannot_qualify(hold):
    gate = TransitionEvidence()
    baseline(gate)
    for i in range(1, 70):
        f = 1 if hold or i == 1 else 0
        assert not gate.update(raw(f, jitter=.15 * math.sin(i)), 1 + i / 30, True)


def test_warmup_motion_cannot_be_reused_by_temporal_route():
    gate = TransitionEvidence()
    for i in range(150):
        f = min(max((i - 30) / 15, 0), 1)
        assert not gate.update(raw(f), i / 30, i >= 59)


def test_slow_episode_expires_without_absorbing_movement_into_baseline():
    gate = TransitionEvidence()
    baseline(gate)
    original = gate.baseline.copy()
    expired = False
    for i in range(1, 100):
        assert not gate.update(raw(min(i / 90, 1)), 1 + i / 30, True)
        if gate.episode_at is not None:
            assert gate.baseline == original
        expired |= gate.diagnostics["temporal"]["rejection_reason"] == "episode_expired"
    assert expired


@pytest.mark.parametrize("interruption", ["movement", "missing", "gap"])
def test_temporal_suspicion_interrupted_and_evidence_not_reused(interruption):
    p = pipeline()
    suspected = False
    for i in range(230):
        t = i / 30 + (1 if interruption == "gap" and i >= 120 else 0)
        f = min(max((i / 30 - 3) / .5, 0), 1)
        kp, box = observation(f)
        if interruption == "missing" and i == 120:
            kp, box = None, None
        elif interruption == "movement" and i >= 120:
            kp[:, 0] += 30
        result = p.update(0, kp, box, .9, t)
        suspected |= result["state"] == "FALL_SUSPECTED"
        assert result["event"] is None
        if i >= 120:
            assert result["state"] == "NORMAL"
    assert suspected


def test_pending_motion_waits_for_quiet_then_starts_full_three_seconds():
    p = pipeline()
    pending_at = suspected_at = None
    events = []
    for i in range(115):
        t = i / 10
        f = min(max((t - 7) / .5, 0), 1)
        kp, box = observation(f)
        # Same normalized geometry, larger image-space motion exceeds unchanged
        # per-frame verifier limits until the person stops moving.
        result = p.update(0, kp * 10, tuple(v * 10 for v in box), .9, t)
        d = result["transition_diagnostics"]
        if d["temporal"]["supported"] and not d["quiet"]:
            pending_at = t if pending_at is None else pending_at
            assert result["state"] == "NORMAL"
        if result["state"] == "FALL_SUSPECTED" and suspected_at is None:
            suspected_at = t
            assert d["temporal"]["supported"] and d["quiet"]
            assert result["elapsed_seconds"] == 0
        if result["event"]:
            events.append(result["event"])
    assert pending_at is not None and suspected_at > pending_at
    assert len(events) == 1
    assert events[0]["timestamp"] - suspected_at >= 3


def test_probability_threshold_remains_required_for_temporal_onset():
    p = pipeline()
    p.model.predict.return_value = [[.29]]
    seen_temporal = False
    for i in range(200):
        t = i / 30
        result = p.update(0, *observation(min(max((t - 3) / .5, 0), 1)), .9, t)
        seen_temporal |= result["transition_diagnostics"]["temporal"]["supported"]
        assert result["state"] == "NORMAL"
    assert seen_temporal


def test_irregular_sampling_and_independent_track_state():
    gate, other = TransitionEvidence(), TransitionEvidence()
    for t in (0, .07, .13, .26, .41, .52, .65, .81, 1.):
        assert not gate.update(raw(), t, True)
    supported = False
    for t in (1.04, 1.09, 1.17, 1.23, 1.34, 1.42, 1.5):
        supported |= gate.update(raw((t - 1) / .5), t, True)
        assert not other.update(raw(1), t, True)
    assert supported


def test_unstable_baseline_cannot_arm_temporal_route():
    gate = TransitionEvidence()
    for i in range(90):
        gate.update(raw(.5 + .3 * math.sin(i * .7)), i / 30, True)
        assert not gate.diagnostics["temporal"]["baseline_ready"]
        assert not gate.diagnostics["temporal"]["supported"]


def test_rotation_with_aspect_change_can_support_temporal_endpoint():
    gate = TransitionEvidence()
    baseline(gate)
    supported = False
    for i in range(1, 16):
        f = i / 15
        r = raw()
        angle = math.radians(16 * f)
        r["hip_center_y"] += 20 * f
        r["shoulder_center_y"] = r["hip_center_y"] - 60 * math.cos(angle)
        r["shoulder_center_x"] = r["hip_center_x"] + 60 * math.sin(angle)
        r["torso_angle"] = math.degrees(angle)
        r["bbox_height"] -= 30 * f
        r["aspect_ratio"] = (80 + 20 * f) / r["bbox_height"]
        supported |= gate.update(r, 1 + i / 30, True)
        assert not gate.diagnostics["geometry_supported"]
    assert supported
    assert gate.diagnostics["temporal"]["changes"]["torso_shortening"] < .06
