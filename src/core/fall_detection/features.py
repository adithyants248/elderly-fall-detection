import math
import numpy as np

from src.core.pose.keypoints import KEYPOINTS


def get_point(keypoints, name):
    """
    Get (x, y) coordinates of a keypoint.
    """

    index = KEYPOINTS[name]

    point = keypoints[index]

    return float(point[0]), float(point[1])


def midpoint(point_a, point_b):
    """
    Calculate midpoint between two points.
    """

    return (
        (point_a[0] + point_b[0]) / 2,
        (point_a[1] + point_b[1]) / 2,
    )


def torso_angle(keypoints):
    """
    Calculate torso angle relative to the vertical direction.
    """

    left_shoulder = get_point(keypoints, "left_shoulder")
    right_shoulder = get_point(keypoints, "right_shoulder")

    left_hip = get_point(keypoints, "left_hip")
    right_hip = get_point(keypoints, "right_hip")

    shoulder_center = midpoint(
        left_shoulder,
        right_shoulder,
    )

    hip_center = midpoint(
        left_hip,
        right_hip,
    )

    dx = hip_center[0] - shoulder_center[0]
    dy = hip_center[1] - shoulder_center[1]

    angle = math.degrees(math.atan2(abs(dx), abs(dy)))

    return angle


def vertical_position(keypoints):
    """
    Use hip center as the person's vertical body position.
    """

    left_hip = get_point(keypoints, "left_hip")
    right_hip = get_point(keypoints, "right_hip")

    hip_center = midpoint(left_hip, right_hip)

    return hip_center[1]


def bounding_box_aspect_ratio(bbox):
    """
    Calculate width / height of person's bounding box.
    """

    x1, y1, x2, y2 = bbox

    width = x2 - x1
    height = y2 - y1

    if height <= 0:
        return 0.0

    return width / height