"""Canonical model preprocessing, distinct from the legacy rule-based features.

Offline: interpolate the complete source sequence before scaling/window slicing.
Online: fill each row once from past observations and saved training medians.
Already emitted rows never change when later observations arrive.
Raw motion is always computed BEFORE interpolation, across window boundaries.
"""
from collections import deque
import math

import joblib
import numpy as np
import pandas as pd

from .model_schema import ArtifactPaths, FEATURE_NAMES, WINDOW_SIZE, STRIDE


def spatial_features(keypoints=None, bbox=None, confidence=np.nan):
    """Cell 4: use coordinates directly, including zeros, with no keypoint filter.

    None/empty keypoints represents a readable frame without a person.
    The YOLO caller selects the person (first detection for notebook parity).
    """
    row = dict.fromkeys(FEATURE_NAMES, np.nan)
    row["person_detected"] = 0.0
    if keypoints is None or len(keypoints) == 0:
        return row
    kp = np.asarray(keypoints)
    if kp.ndim != 2 or kp.shape[0] < 17 or kp.shape[1] < 2:
        raise ValueError("Expected 17 keypoints with x/y coordinates.")
    for name, left, right in (("shoulder", 5, 6), ("hip", 11, 12),
                              ("knee", 13, 14), ("ankle", 15, 16)):
        row[f"{name}_center_x"] = (kp[left, 0] + kp[right, 0]) / 2
        row[f"{name}_center_y"] = (kp[left, 1] + kp[right, 1]) / 2
    dx = row["shoulder_center_x"] - row["hip_center_x"]
    dy = row["shoulder_center_y"] - row["hip_center_y"]
    row["torso_angle"] = math.degrees(math.atan2(abs(dx), abs(dy)))
    row["person_detected"] = 1.0
    if bbox is not None:
        x1, y1, x2, y2 = bbox
        width, height = x2 - x1, y2 - y1
        row.update(bbox_width=width, bbox_height=height,
                   aspect_ratio=width / height if height > 0 else np.nan,
                   person_confidence=float(confidence))
    return row


def add_motion(row, previous=None):
    """Equivalent to Cell 4's pandas diff on consecutive raw retained rows."""
    row = row.copy()
    if previous is not None:
        dx = row["hip_center_x"] - previous["hip_center_x"]
        dy = row["hip_center_y"] - previous["hip_center_y"]
        row.update(
            hip_vertical_velocity=dy,
            hip_vertical_acceleration=dy - previous["hip_vertical_velocity"],
            hip_horizontal_velocity=dx,
            body_center_movement=np.sqrt(dx ** 2 + dy ** 2),
            torso_angle_change=row["torso_angle"] - previous["torso_angle"],
            aspect_ratio_change=row["aspect_ratio"] - previous["aspect_ratio"],
        )
    return row


def interpolate_sequence(rows):
    """Cell 6 interpolation. Call separately for each complete source sequence.

    Input already contains raw motion. Detection flags are never interpolated.
    Entirely missing columns remain NaN until saved training-median filling.
    """
    data = pd.DataFrame(rows, columns=FEATURE_NAMES).copy()
    data["person_detected"] = data["person_detected"].astype(float)
    for name in FEATURE_NAMES[:-1]:
        data[name] = data[name].interpolate(method="linear", limit_direction="both")
    return data


class ModelPreprocessor:
    def __init__(self, paths=None):
        self.paths = paths or ArtifactPaths()
        self.scaler = joblib.load(self.paths.scaler)
        self.medians = joblib.load(self.paths.medians)
        if self.scaler.n_features_in_ != 20 or tuple(self.scaler.feature_names_in_) != FEATURE_NAMES:
            raise ValueError("Scaler does not match the canonical 20 features.")
        if not isinstance(self.medians, pd.Series) or tuple(self.medians.index) != FEATURE_NAMES:
            raise ValueError("Training medians must be an ordered 20-feature Series.")
        if not np.isfinite(self.medians.to_numpy()).all():
            raise ValueError("Training medians contain unfillable features.")

    def transform(self, rows, *, interpolated=False):
        if isinstance(rows, pd.DataFrame):
            names = tuple(name for name in rows.columns if name in FEATURE_NAMES)
            if names != FEATURE_NAMES:
                raise ValueError("Model columns must match canonical feature order.")
        elif any(not isinstance(row, dict) or set(row) != set(FEATURE_NAMES) for row in rows):
            raise ValueError("Model rows must name exactly the canonical 20 features.")
        data = (pd.DataFrame(rows, columns=FEATURE_NAMES).copy() if interpolated
                else interpolate_sequence(rows))
        data = data.fillna(self.medians)
        if not np.isfinite(data.to_numpy()).all():
            raise ValueError("Nonfinite model input remains after median filling.")
        # Never fit/fit_transform: all 20 columns use the existing training scaler.
        return self.scaler.transform(data)

    def offline_windows(self, rows, *, interpolated=False):
        # Source tables include notebook metadata and are explicitly projected.
        if isinstance(rows, pd.DataFrame):
            rows = rows.loc[:, list(FEATURE_NAMES)]
        if len(rows) < WINDOW_SIZE:
            return np.empty((0, WINDOW_SIZE, 20), dtype=np.float32)
        scaled = self.transform(rows, interpolated=interpolated)
        return np.asarray([scaled[i:i + WINDOW_SIZE]
                           for i in range(0, len(scaled) - WINDOW_SIZE + 1, STRIDE)],
                          dtype=np.float32)


class TemporalBuffer:
    """One instance per source/person. Missing readable frames MUST be appended.

    Previous raw motion is retained beyond deque eviction. No elapsed-time
    normalization and no per-window derivative restart. No 70% live-window gate.
    Spatial forward filling lasts until reset; derivatives use saved medians
    when unavailable. Filled values are for the model only, never verification.
    """
    def __init__(self, preprocessor):
        self.preprocessor = preprocessor
        self.rows = deque(maxlen=WINDOW_SIZE)
        self.filled_rows = deque(maxlen=WINDOW_SIZE)
        self.last_spatial = {}
        self.previous = None

    def append(self, keypoints=None, bbox=None, confidence=np.nan):
        row = add_motion(spatial_features(keypoints, bbox, confidence), self.previous)
        self.previous = row.copy()
        self.rows.append(row)
        filled = row.copy()
        for name in FEATURE_NAMES[:-1]:
            value = row[name]
            if np.isinf(value):
                raise ValueError("Infinite raw feature.")
            if np.isfinite(value):
                if name in FEATURE_NAMES[:13]:
                    self.last_spatial[name] = value
            else:
                # Carry spatial observations only. Unknown motion must not carry
                # a previous impact indefinitely; use the saved training median.
                filled[name] = self.last_spatial.get(name, self.preprocessor.medians[name])
        self.filled_rows.append(filled)
        tensor = None
        if len(self.rows) == WINDOW_SIZE:
            tensor = self.preprocessor.transform(list(self.filled_rows), interpolated=True).astype(np.float32)[None, ...]
        return row.copy(), tensor

    def reset(self):
        self.rows.clear()
        self.filled_rows.clear()
        self.last_spatial.clear()
        self.previous = None
