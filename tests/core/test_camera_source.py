"""Shared runner/source behavior with fake frames, pose and model dependencies."""
from contextlib import redirect_stdout
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
from src.core.fall_detection.camera import GRUCameraSource, CameraUnavailable, first_person
from src.core.fall_detection.gru_inference import GRUInference
from test_gru_preprocessing import pose, Tensor, Boxes


class CameraSourceTests(unittest.TestCase):
    def source(self, source='0', selection='first'):
        current = GRUCameraSource(source, selection, 'cpu')
        current.capture = Mock()
        current.capture.read.return_value = (True, np.zeros((200, 300, 3), dtype=np.uint8))
        current.camera_source = source.isdecimal()
        current.fps = 30
        current.pose = Mock(return_value=[SimpleNamespace(
            keypoints=SimpleNamespace(xy=Tensor([pose()])), boxes=Boxes())])
        return current

    def test_source_reuses_real_gru_preprocessing_and_verifier(self):
        source = self.source('clip.mp4')
        model = Mock(input_shape=(None, 60, 20), output_shape=(None, 1))
        model.predict.return_value = [[.30]]
        source.inference = GRUInference(model_loader=lambda _: model)
        events = []
        for i in range(200):
            if i == 70:
                source.pose.return_value[0].keypoints.xy = Tensor([pose(y=60)])
            _, results = source.read()
            result = next(results)
            if i < 59:
                self.assertIsNone(result['fall_probability'])
            if result['event']:
                events.append(result['event'])
        self.assertEqual(len(events), 1)
        self.assertEqual(result['state'], 'CONFIRMED_FALL')
        self.assertEqual(model.predict.call_args.args[0].shape, (1, 60, 20))
        source.reset(0)
        self.assertEqual(next(source.read()[1])['buffer_frames'], 1)

    def test_video_timestamps_and_missing_person_are_preserved(self):
        source = self.source('clip.mp4')
        source.pose.return_value = []
        source.inference = Mock(buffers={})
        list(source.read()[1]); list(source.read()[1])
        self.assertEqual(source.inference.update.call_args_list[0].kwargs, {'timestamp': 0})
        self.assertEqual(source.inference.update.call_args_list[1].kwargs, {'timestamp': 1 / 30})

    def test_tracked_source_updates_absent_buffered_people(self):
        source = self.source(selection='tracked')
        source.tracker = Mock()
        source.tracker.track.return_value = [{'track_id': 2, 'keypoints': pose(), 'bbox': (0,0,60,120), 'confidence': .8}]
        source.inference = Mock(buffers={1: object()})
        with patch('src.core.fall_detection.camera.time.monotonic', return_value=12):
            list(source.read()[1])
        source.inference.expire_absent.assert_called_once_with({2}, 12)
        self.assertEqual(source.inference.update.call_args_list[0].args, (1,))
        self.assertEqual(source.inference.update.call_args_list[0].kwargs, {'timestamp': 12})
        self.assertEqual(source.inference.update.call_args_list[1].args, (2,))

    def test_video_eof_and_camera_read_failure_are_distinct(self):
        source = self.source('clip.mp4')
        source.capture.read.return_value = (False, None)
        self.assertIsNone(source.read())
        source.camera_source = True
        with self.assertRaises(CameraUnavailable):
            source.read()

    def test_close_releases_capture_once(self):
        source = self.source()
        capture = source.capture
        source.close(); source.close()
        capture.release.assert_called_once()

    def test_standalone_first_person_import_is_shared(self):
        from scripts.run_gru_pipeline import first_person as exported
        self.assertIs(exported, first_person)

    def test_standalone_main_keeps_display_quit_and_cleanup(self):
        from scripts.run_gru_pipeline import main
        source = Mock()
        source.read.return_value = (np.zeros((200,300,3), dtype=np.uint8), iter([
            dict(track_id=1, state='NORMAL', fall_probability=None, buffer_frames=1,
                 elapsed_seconds=0, reason='prediction_unavailable', fall_confirmed=False, event=None)]))
        cv = Mock()
        cv.getTextSize.return_value = ((100, 10), 0)
        cv.waitKey.return_value = ord('q')
        with patch.dict('sys.modules', {'cv2': cv}), patch('sys.argv', ['run_gru_pipeline']), \
             patch('scripts.run_gru_pipeline.GRUCameraSource', return_value=source):
            main()
        source.open.assert_called_once()
        source.close.assert_called_once()
        cv.imshow.assert_called_once()
        cv.destroyAllWindows.assert_called_once()

    def test_standalone_failure_still_releases_source(self):
        from scripts.run_gru_pipeline import main
        source = Mock()
        source.open.side_effect = CameraUnavailable('no webcam')
        with patch.dict('sys.modules', {'cv2': Mock()}), patch('sys.argv', ['run_gru_pipeline']), \
             patch('scripts.run_gru_pipeline.GRUCameraSource', return_value=source):
            with self.assertRaises(CameraUnavailable):
                main()
        source.close.assert_called_once()
