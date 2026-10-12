"""Shared camera/video orchestration; inference and verification remain unchanged.

All methods belong to one processing thread. Imports/model loading are lazy so
the dashboard-only application does not import ML or open a camera.
"""
import math
import time


class CameraUnavailable(RuntimeError):
    pass


def first_person(results):
    """Notebook selection, including keypoints-without-boxes behavior."""
    if not results or results[0].keypoints is None or len(results[0].keypoints.xy) == 0:
        return {}
    result = results[0]
    person = {"keypoints": result.keypoints.xy[0].cpu().numpy()}
    if result.boxes is not None and len(result.boxes) > 0:
        person.update(bbox=result.boxes.xyxy[0].cpu().numpy(),
                      confidence=float(result.boxes.conf[0].cpu().numpy()))
    return person


class GRUCameraSource:
    def __init__(self, source="0", selection="first", device=None, paths=None):
        self.source, self.selection, self.device = str(source), selection, device
        self.paths = paths
        self.capture = None
        self.inference = None
        self.frame_index = 0

    def open(self):
        if not self.source.strip() or self.selection not in ("first", "tracked"):
            raise ValueError("Camera source must be nonempty and selection must be first or tracked.")
        import cv2
        import torch
        from ultralytics import YOLO
        from .model_schema import ArtifactPaths
        from .gru_inference import GRUInference
        from src.core.tracking.tracker import PersonTracker

        self.cv2 = cv2
        self.paths = self.paths or ArtifactPaths()
        self.camera_source = self.source.isdecimal()
        self.capture = cv2.VideoCapture(int(self.source) if self.camera_source else self.source)
        if not self.capture.isOpened():
            raise CameraUnavailable(f"Cannot open source: {self.source}")
        self.fps = self.capture.get(cv2.CAP_PROP_FPS)
        if not self.camera_source and (not math.isfinite(self.fps) or self.fps <= 0):
            raise CameraUnavailable("Video has no valid FPS for source timestamps.")
        self.inference = GRUInference(self.paths)
        if self.device is None:
            self.device = 0 if torch.cuda.is_available() else "cpu"
        if self.selection == "tracked":
            self.tracker = PersonTracker(str(self.paths.pose), confidence=0.25,
                                         device=self.device, tracker="bytetrack.yaml")
        else:
            self.pose = YOLO(str(self.paths.pose))

    def read(self):
        ok, frame = self.capture.read()
        if not ok:
            if self.camera_source:
                raise CameraUnavailable("Camera stopped returning frames.")
            return None
        timestamp = time.monotonic() if self.camera_source else self.frame_index / self.fps
        self.frame_index += 1
        return frame, self._results(frame, timestamp)

    def _results(self, frame, timestamp):
        if self.selection == "tracked":
            people = {p["track_id"]: {k: p[k] for k in ("keypoints", "bbox", "confidence") if k in p}
                      for p in self.tracker.track(frame)}
        else:
            people = {0: first_person(self.pose(frame, device=self.device, conf=0.25, verbose=False))}
        visible = {track for track, person in people.items() if person.get("keypoints") is not None}
        self.inference.expire_absent(visible, timestamp)
        for track_id in sorted(set(people) | set(self.inference.buffers)):
            # Yield immediately: an event is handed off before another person's
            # inference can fail. Never accumulate an entire frame's events first.
            yield self.inference.update(track_id, timestamp=timestamp, **people.get(track_id, {}))

    def reset(self, track_id):
        self.inference.reset(track_id)

    def reset_all(self):
        for track_id in list(self.inference.verifier._tracks):
            self.reset(track_id)

    def close(self):
        if self.capture is not None:
            self.capture.release()
            self.capture = None
