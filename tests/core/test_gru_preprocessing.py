"""Notebook parity, saved-artifact checks and GRU-to-decision integration."""
import ast
from contextlib import redirect_stdout
import io
import json
import math
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from src.core.fall_detection.model_schema import ArtifactPaths, FEATURE_NAMES, ROOT
from src.core.fall_detection.preprocessing import (
    ModelPreprocessor, TemporalBuffer, add_motion, interpolate_sequence, spatial_features,
)
from src.core.fall_detection.gru_inference import GRUInference
from scripts.validate_gru_artifacts import validate
from scripts.run_gru_pipeline import first_person


def pose(x=0, y=0):
    kp = np.zeros((17, 2), dtype=np.float32)
    for left, right, cy in ((5, 6, 10), (11, 12, 50), (13, 14, 90), (15, 16, 120)):
        kp[left] = (x + 10, y + cy)
        kp[right] = (x + 30, y + cy)
    return kp


class Tensor:
    def __init__(self, value):
        self.value = np.asarray(value)
    def __getitem__(self, key):
        return Tensor(self.value[key])
    def __len__(self):
        return len(self.value)
    def cpu(self):
        return self
    def numpy(self):
        return self.value


class Boxes:
    def __init__(self):
        self.xyxy = Tensor([[0, 0, 60, 120]])
        self.conf = Tensor([0.8])
    def __len__(self):
        return 1


class GRUPreprocessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preprocessor = ModelPreprocessor()

    def test_order_matches_notebook_and_scaler(self):
        notebook = json.loads((ROOT / "colab_reference/Fall_Detection_Dataset.ipynb").read_text(encoding="utf-8"))
        tree = ast.parse("".join(notebook["cells"][5]["source"]))
        assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == "FEATURE_COLUMNS" for t in n.targets))
        expected = tuple(ast.literal_eval(assignment.value)) + ("person_detected",)
        self.assertEqual(FEATURE_NAMES, expected)
        self.assertEqual(tuple(self.preprocessor.scaler.feature_names_in_), expected)
        self.assertEqual(len(spatial_features()), 20)

    def test_unsigned_angle_and_spatial_centers(self):
        kp = pose()
        kp[5:7, 0] += 40
        row = spatial_features(kp, (0, 0, 60, 120), 0.8)
        self.assertEqual(row["torso_angle"], 45)
        self.assertEqual(row["hip_center_x"], 20)
        self.assertEqual(row["knee_center_y"], 90)
        self.assertEqual(row["ankle_center_y"], 120)
        self.assertEqual(row["person_confidence"], 0.8)
        self.assertEqual(row["person_detected"], 1)
        self.assertEqual(row["aspect_ratio"], 0.5)

    def test_raw_motion(self):
        first = add_motion(spatial_features(pose(), (0, 0, 60, 120), 0.8))
        second = add_motion(spatial_features(pose(3, 4), (0, 0, 120, 120), 0.8), first)
        third = add_motion(spatial_features(pose(9, 14), (0, 0, 120, 120), 0.8), second)
        self.assertTrue(np.isnan(first["hip_vertical_velocity"]))
        self.assertTrue(np.isnan(second["hip_vertical_acceleration"]))
        self.assertEqual(second["hip_vertical_velocity"], 4)
        self.assertEqual(second["hip_horizontal_velocity"], 3)
        self.assertEqual(second["body_center_movement"], 5)
        self.assertEqual(second["aspect_ratio_change"], 0.5)
        self.assertEqual(third["hip_vertical_acceleration"], 6)
        self.assertEqual(third["torso_angle_change"], 0)

    def test_angle_change_is_unsigned_angle_difference(self):
        first = add_motion(spatial_features(pose()))
        kp = pose()
        kp[5:7, 0] += 40
        second = add_motion(spatial_features(kp), first)
        self.assertEqual(second["torso_angle_change"], 45)

    def test_missing_rows_and_box_guard(self):
        row = spatial_features()
        self.assertEqual(row["person_detected"], 0)
        self.assertTrue(all(np.isnan(row[k]) for k in FEATURE_NAMES[:-1]))
        row = spatial_features(pose())
        self.assertEqual(row["person_detected"], 1)
        self.assertTrue(np.isnan(row["bbox_width"]))
        self.assertTrue(np.isnan(spatial_features(pose(), (0, 0, 10, 0))["aspect_ratio"]))

    def test_motion_does_not_bridge_missing_rows(self):
        a = add_motion(spatial_features(pose()))
        b = add_motion(spatial_features(), a)
        c = add_motion(spatial_features(pose(10, 10)), b)
        d = add_motion(spatial_features(pose(12, 12)), c)
        self.assertTrue(np.isnan(c["hip_vertical_velocity"]))
        self.assertEqual(d["hip_vertical_velocity"], 2)
        self.assertTrue(np.isnan(d["hip_vertical_acceleration"]))

    def test_interpolation_edges_and_detection_flag(self):
        rows = [spatial_features(), spatial_features(pose()), spatial_features(), spatial_features(pose(10, 10)), spatial_features()]
        data = interpolate_sequence(rows)
        np.testing.assert_array_equal(data.hip_center_x, [20, 20, 25, 30, 30])
        np.testing.assert_array_equal(data.person_detected, [0, 1, 0, 1, 0])
        self.assertTrue(data.bbox_width.isna().all())

    def test_medians_are_saved_training_values_not_zero(self):
        row = spatial_features()
        scaled = self.preprocessor.transform([row])
        expected = self.preprocessor.medians.copy()
        expected["person_detected"] = 0
        np.testing.assert_allclose(scaled, self.preprocessor.scaler.transform(pd.DataFrame([expected])))
        self.assertNotEqual(self.preprocessor.medians["hip_center_y"], 0)

    def test_loads_scaler_and_medians_never_fits(self):
        with patch.object(StandardScaler, "fit", side_effect=AssertionError("must not fit")):
            with patch("src.core.fall_detection.preprocessing.joblib.load", wraps=joblib.load) as loader:
                preprocessor = ModelPreprocessor()
                preprocessor.transform([spatial_features()])
                self.assertEqual(loader.call_count, 2)
                self.assertEqual(loader.call_args_list[0].args[0], ArtifactPaths().scaler)
                self.assertEqual(loader.call_args_list[1].args[0], ArtifactPaths().medians)

    def test_60_frame_buffer_and_motion_survive_eviction(self):
        buffer = TemporalBuffer(self.preprocessor)
        for i in range(65):
            row, tensor = buffer.append(pose(0, i), (0, 0, 60, 120), 0.8)
            if i < 59:
                self.assertIsNone(tensor)
            else:
                self.assertEqual(tensor.shape, (1, 60, 20))
                self.assertEqual(tensor.dtype, np.float32)
                self.assertEqual(row["hip_vertical_velocity"], 1)
                self.assertEqual(row["hip_vertical_acceleration"], 0)
        self.assertEqual(len(buffer.rows), 60)
        buffer.reset()
        self.assertIsNone(buffer.previous)

    def test_offline_stride_boundaries(self):
        for count, windows in ((59, 0), (60, 1), (74, 1), (75, 2), (90, 3)):
            rows = [spatial_features(pose(), (0, 0, 60, 120), 0.8)] * count
            self.assertEqual(self.preprocessor.offline_windows(rows).shape, (windows, 60, 20))

    def test_live_does_not_see_future_interpolation(self):
        rows = [spatial_features(pose(), (0, 0, 60, 120), 0.8)] + [spatial_features()] * 59
        online = self.preprocessor.transform(rows)
        offline = self.preprocessor.transform(rows + [spatial_features(pose(100, 0), (0, 0, 60, 120), 0.8)])
        self.assertNotEqual(online[-1, 2], offline[59, 2])

    def test_artifact_reconstruction_matches_all_supplied_arrays(self):
        result = validate()
        for split in result.values():
            self.assertEqual(split["max_abs_error"], 0.0)

    def test_notebook_extraction_equivalence(self):
        notebook = json.loads((ROOT / "colab_reference/Fall_Detection_Dataset.ipynb").read_text(encoding="utf-8"))
        tree = ast.parse("".join(notebook["cells"][3]["source"]))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "extract_sequence")
        observations = [pose(), pose(3, 4), None, pose(7, 10), pose(10, 15)]
        def model(frame, **kwargs):
            kp = observations[frame]
            return [SimpleNamespace(keypoints=None if kp is None else SimpleNamespace(xy=Tensor([kp])), boxes=Boxes())]
        import os
        namespace = dict(os=os, cv2=SimpleNamespace(imread=lambda p: p), np=np, pd=pd,
                         math=math, find_pngs=lambda _: list(range(5)), model=model)
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<read-only notebook extraction>", "exec"), namespace)
        with redirect_stdout(io.StringIO()):
            reference = namespace["extract_sequence"]("synthetic", 0)
        actual, previous = [], None
        for kp in observations:
            row = add_motion(spatial_features(kp, np.array([0, 0, 60, 120]), 0.8), previous)
            actual.append(row)
            previous = row
        np.testing.assert_allclose(pd.DataFrame(actual)[list(FEATURE_NAMES)], reference[list(FEATURE_NAMES)], equal_nan=True)

    def test_first_person_selection(self):
        selected = first_person([SimpleNamespace(keypoints=SimpleNamespace(xy=Tensor([pose(), pose(100, 0)])), boxes=Boxes())])
        np.testing.assert_array_equal(selected["keypoints"], pose())
        self.assertEqual(first_person([]), {})

    def test_model_loads_once_probability_reaches_verifier(self):
        model = Mock(input_shape=(None, 60, 20), output_shape=(None, 1))
        model.predict.return_value = np.array([[0.30]])
        loader = Mock(return_value=model)
        pipeline = GRUInference(model_loader=loader)
        events = []
        for i in range(200):
            # A real onset after warmup, followed by observed stillness.
            result = pipeline.update(1, pose(y=60 if i >= 70 else 0), (0, 0, 60, 120), 0.8, timestamp=i / 30)
            if i < 59:
                self.assertIsNone(result["fall_probability"])
            if i == 59:
                self.assertEqual(result["fall_probability"], .30)
                self.assertEqual(result["state"], "NORMAL")
            if result["event"]:
                events.append(result["event"])
        loader.assert_called_once()
        self.assertEqual(len(events), 1)
        self.assertEqual(result["state"], "CONFIRMED_FALL")

    def test_missing_raw_motion_not_imputed_for_verifier(self):
        model = Mock(input_shape=(None, 60, 20), output_shape=(None, 1))
        model.predict.return_value = [[0.9]]
        pipeline = GRUInference(model_loader=lambda _: model)
        for i in range(61):
            pipeline.update(1, pose(), (0, 0, 60, 120), 0.8, timestamp=i / 30)
        result = pipeline.update(1, timestamp=61 / 30)
        self.assertEqual(result["state"], "NORMAL")
        self.assertEqual(result["reason"], "missing_motion")
        self.assertTrue(np.isnan(result["features"]["body_center_movement"]))

    def test_tracks_gap_and_timestamp_validation(self):
        model = Mock(input_shape=(None, 60, 20), output_shape=(None, 1))
        model.predict.return_value = [[0.1]]
        pipeline = GRUInference(model_loader=lambda _: model)
        for i in range(60):
            pipeline.update(1, pose(), timestamp=i / 30)
        self.assertEqual(pipeline.update(2, pose(), timestamp=2)["buffer_frames"], 1)
        self.assertEqual(pipeline.update(1, pose(), timestamp=4)["buffer_frames"], 1)
        with self.assertRaises(ValueError):
            pipeline.update(1, pose(), timestamp=4)

    def test_real_model_loads_and_predicts_saved_input(self):
        pipeline = GRUInference()
        tensor = np.load(ROOT / "colab_reference/X_test.npy")[:1]
        probability = np.asarray(pipeline.model.predict(tensor, verbose=0))
        self.assertEqual(probability.shape, (1, 1))
        self.assertTrue(np.isfinite(probability).all())
        self.assertTrue(0 <= probability[0, 0] <= 1)


if __name__ == "__main__":
    unittest.main()
