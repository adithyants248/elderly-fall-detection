from collections import deque

from .features import (
    torso_angle,
    vertical_position,
    bounding_box_aspect_ratio,
)


class FallDetector:
    """
    Rule-based fall detector.

    Uses:
    - torso angle
    - vertical movement
    - bounding-box aspect ratio
    """

    def __init__(
        self,
        history_size: int = 30,
        torso_angle_threshold: float = 45.0,
        vertical_drop_threshold: float = 50.0,
        aspect_ratio_threshold: float = 1.2,
    ):

        self.torso_angle_threshold = torso_angle_threshold
        self.vertical_drop_threshold = vertical_drop_threshold
        self.aspect_ratio_threshold = aspect_ratio_threshold

        self.history = {}

        self.history_size = history_size

    def _get_history(self, track_id):

        if track_id not in self.history:

            self.history[track_id] = deque(
                maxlen=self.history_size
            )

        return self.history[track_id]

    def analyze(self, person):

        track_id = person["track_id"]
        keypoints = person["keypoints"]
        bbox = person["bbox"]

        history = self._get_history(track_id)

        current_position = vertical_position(keypoints)

        current_angle = torso_angle(keypoints)

        current_ratio = bounding_box_aspect_ratio(bbox)

        history.append(
            {
                "position": current_position,
                "angle": current_angle,
                "ratio": current_ratio,
            }
        )

        if len(history) < 2:

            return {
                "fall_detected": False,
                "score": 0.0,
                "features": {
                    "torso_angle": current_angle,
                    "vertical_drop": 0.0,
                    "aspect_ratio": current_ratio,
                },
            }

        previous_position = history[-2]["position"]

        vertical_drop = current_position - previous_position

        angle_signal = (
            current_angle >= self.torso_angle_threshold
        )

        drop_signal = (
            vertical_drop >= self.vertical_drop_threshold
        )

        ratio_signal = (
            current_ratio >= self.aspect_ratio_threshold
        )

        signals = sum(
            [
                angle_signal,
                drop_signal,
                ratio_signal,
            ]
        )

        score = signals / 3.0

        fall_detected = signals >= 2

        return {
            "fall_detected": fall_detected,
            "score": score,
            "features": {
                "torso_angle": current_angle,
                "vertical_drop": vertical_drop,
                "aspect_ratio": current_ratio,
            },
        }