"""Adversarial high-probability live regression tests; no camera required."""
from unittest.mock import Mock
import numpy as np
import pandas as pd
import pytest

from test_gru_preprocessing import pose
from src.api.context import ApplicationContext
from src.core.fall_detection.gru_inference import GRUInference
from src.core.fall_detection.preprocessing import ModelPreprocessor, TemporalBuffer, spatial_features
from src.core.fall_detection.model_schema import FEATURE_NAMES


def pipeline():
    model = Mock(input_shape=(None, 60, 20), output_shape=(None, 1))
    model.predict.return_value = [[.9977]]
    return GRUInference(model_loader=lambda _: model)


def step(p, i, x=0, y=0, angle=0, missing=False):
    kp = pose(x, y)
    kp[5:7, 0] += angle
    return p.update(0, None if missing else kp, None if missing else (0, 0, 60, 120), .8, i / 30)


@pytest.mark.parametrize('angle,y', [(0, 0), (30, 30), (100, 60)])
def test_static_startup_never_alerts_even_with_high_probability(angle, y):
    p = pipeline()
    context = ApplicationContext()
    for i in range(220):
        result = step(p, i, angle=angle, y=y)
        assert result['state'] == 'NORMAL'
        assert context.consume_verification_result(result) is None
        if i < 59:
            assert p.model.predict.call_count == 0
            assert result['warmup']
        if i == 59:
            assert p.model.predict.call_count == 1
            assert result['temporal_ready'] and not result['transition_supported']
    assert context.falls.list_all() == []


def test_walking_and_gradual_sitting_with_high_probability():
    p = pipeline()
    for i in range(300):
        x = min(max(i - 65, 0), 70) * 2
        y = min(max(i - 140, 0), 60) * .5
        result = step(p, i, x=x, y=y)
        assert result['event'] is None
        assert not result['fall_confirmed']


@pytest.mark.parametrize('direction', [-1, 1, 0])
def test_fall_transition_stillness_and_deduplicated_alert(direction):
    p = pipeline()
    context = ApplicationContext()
    events = []
    for i in range(220):
        fraction = min(max((i - 65) / 10, 0), 1)
        result = step(p, i, x=direction * 60 * fraction,
                      y=60 * fraction, angle=60 * fraction)
        if result['event']:
            events.append(result['event'])
            context.consume_verification_result(result)
            context.consume_verification_result(result)
    assert len(events) == len(context.falls.list_all()) == 1
    assert events[0]['timestamp'] - events[0]['suspected_at'] >= 3
    assert result['fall_confirmed']


@pytest.mark.parametrize('interruption', ['movement', 'missing'])
def test_interruption_cancels_and_cannot_reuse_transition(interruption):
    p = pipeline()
    suspected = False
    for i in range(270):
        y = 60 if i >= 70 else 0
        result = step(p, i, y=y, x=30 if interruption == 'movement' and i >= 90 else 0,
                      missing=interruption == 'missing' and 90 <= i < 100)
        suspected |= result['state'] == 'FALL_SUSPECTED'
        assert result['event'] is None
        if i == 100 and interruption == 'missing':
            assert result['buffer_frames'] == 1
            assert result['warmup']
    assert suspected
    assert result['state'] == 'NORMAL'


def test_recovery_can_detect_a_new_fall_after_fresh_warmup():
    p = pipeline()
    events = []
    for i in range(310):
        result = step(p, i, missing=70 <= i < 75, y=60 if i >= 150 else 0)
        if result['event']:
            events.append(result['event'])
    assert len(events) == 1


def test_transition_during_warmup_is_not_reused():
    p = pipeline()
    for i in range(220):
        result = step(p, i, y=60 if i >= 50 else 0)
        assert result['state'] == 'NORMAL'


def test_static_initial_posture_does_not_permanently_disable_detection():
    p = pipeline()
    events = []
    for i in range(240):
        result = step(p, i, angle=30, y=30 if i < 100 else 90)
        if result['event']:
            events.append(result['event'])
    assert len(events) == 1


def test_gap_resets_onset_and_latched_confirmation_survives_loss():
    p = pipeline()
    for i in range(200):
        result = step(p, i, y=60 if i >= 70 else 0)
    assert result['fall_confirmed']
    result = p.update(0, timestamp=20)
    assert result['fall_confirmed'] and result['event'] is None
    assert result['buffer_frames'] == 1
    assert not p.transitions[0].history


def test_all_missing_frames_never_confirm_and_recovery_warms_up():
    p = pipeline()
    for i in range(200):
        result = step(p, i, missing=True)
        assert result['person_detected'] == 0
        assert result['state'] == 'NORMAL'
    assert step(p, 200)['buffer_frames'] == 1


def test_online_rows_are_immutable_and_use_saved_medians_scaler():
    pre = ModelPreprocessor()
    buf = TemporalBuffer(pre)
    raw, _ = buf.append(pose(), (0, 0, 60, 120), .8)
    first = buf.filled_rows[0].copy()
    assert np.isnan(raw['hip_vertical_velocity'])
    assert first['hip_vertical_velocity'] == pre.medians['hip_vertical_velocity']
    raw, _ = buf.append(pose(y=10), (0, 0, 60, 120), .8)
    assert np.isnan(raw['hip_vertical_acceleration'])
    assert buf.filled_rows[-1]['hip_vertical_acceleration'] == pre.medians['hip_vertical_acceleration']
    buf.append()
    missing = buf.filled_rows[-1].copy()
    assert missing['hip_center_y'] == 60
    assert missing['person_detected'] == 0
    for i in range(57):
        _, tensor = buf.append(pose(y=100), (0, 0, 60, 120), .8)
    assert buf.filled_rows[0] == first
    assert buf.filled_rows[2] == missing
    expected = pre.scaler.transform(pd.DataFrame(list(buf.filled_rows), columns=FEATURE_NAMES))
    np.testing.assert_allclose(tensor[0], expected, rtol=1e-6, atol=1e-6)


def test_schema_rejects_reordered_frame_or_missing_named_feature():
    pre = ModelPreprocessor()
    row = spatial_features()
    with pytest.raises(ValueError, match='order'):
        pre.transform(pd.DataFrame([row])[list(reversed(FEATURE_NAMES))])
    del row['hip_center_x']
    with pytest.raises(ValueError, match='20 features'):
        pre.transform([row])
