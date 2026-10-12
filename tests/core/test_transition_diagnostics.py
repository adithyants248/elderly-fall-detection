"""Diagnostic snapshots must explain the gate without changing its decisions."""
import json

import pytest

from src.core.fall_detection.transition import TransitionEvidence


def row(**changes):
    return dict(hip_center_x=0., hip_center_y=0., bbox_height=100.,
                torso_angle=0., aspect_ratio=.5, person_detected=1) | changes


@pytest.mark.parametrize('ready,changes,reason', [
    (False, {}, 'model_not_ready'),
    (True, {'person_detected': 0}, 'person_not_detected'),
    (True, {'hip_center_x': float('nan')}, 'invalid_geometry'),
    (True, {'bbox_height': 0}, 'invalid_geometry'),
])
def test_invalid_observations_clear_history_and_are_json_safe(ready, changes, reason):
    gate = TransitionEvidence()
    gate.update(row(), 0, True)
    assert not gate.update(row(**changes), .1, ready)
    assert gate.diagnostics['false_reason'] == reason
    assert gate.diagnostics['history_rows'] == 0
    assert gate.diagnostics['max_distance_ratio'] is None
    json.dumps(gate.diagnostics, allow_nan=False)


def test_history_snapshot_excludes_current_row_and_prunes_expired_rows():
    gate = TransitionEvidence()
    assert not gate.update(row(), 0, True)
    assert gate.diagnostics['false_reason'] == 'no_eligible_previous_observation'
    assert not gate.update(row(), 1, True)
    assert gate.diagnostics['history_rows'] == 1
    assert gate.diagnostics['oldest_history_age_seconds'] == 1
    assert gate.diagnostics['false_reason'] == 'route_thresholds_not_met'
    assert not gate.update(row(), 2.01, True)
    assert gate.diagnostics['history_rows'] == 0
    assert gate.diagnostics['oldest_history_age_seconds'] is None


def test_route_one_does_not_combine_maxima_from_different_prior_rows():
    gate = TransitionEvidence()
    gate.update(row(hip_center_x=30, torso_angle=30), 0, True)
    gate.update(row(), .1, True)
    assert not gate.update(row(torso_angle=30), .2, True)
    diagnostic = gate.diagnostics
    assert diagnostic['max_distance_ratio'] == .3
    assert diagnostic['max_angle_change'] == 30
    assert not diagnostic['route_1_passed']
    assert not diagnostic['route_2_passed']


def test_maxima_include_history_after_first_successful_match():
    gate = TransitionEvidence()
    gate.update(row(hip_center_y=0), 0, True)
    gate.update(row(hip_center_y=-20), .1, True)
    assert gate.update(row(hip_center_y=40, torso_angle=20, aspect_ratio=.75), .2, True)
    diagnostic = gate.diagnostics
    assert diagnostic['max_distance_ratio'] == .6
    assert diagnostic['max_downward_ratio'] == .6
    assert diagnostic['max_angle_change'] == 20
    assert diagnostic['max_aspect_change'] == .25
    assert diagnostic['route_1_passed'] and diagnostic['route_2_passed']
    assert diagnostic['false_reason'] is None
