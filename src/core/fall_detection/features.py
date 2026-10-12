import math

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


def bounding_box_width(bbox):
    """Bounding-box width in pixels (xyxy coordinates)."""
    return float(bbox[2] - bbox[0])


def bounding_box_height(bbox):
    """Bounding-box height in pixels (xyxy coordinates)."""
    return float(bbox[3] - bbox[1])


def body_center(bbox):
    """Use the bounding-box center as the body-center proxy, in pixels."""
    return midpoint(bbox[:2], bbox[2:])


def body_center_movement(current_center, previous_center):
    """Euclidean displacement in pixels, not speed."""
    return math.hypot(
        current_center[0] - previous_center[0],
        current_center[1] - previous_center[1],
    )


def _validate_interval(dt):
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("Elapsed time must be finite and greater than zero.")


def vertical_velocity(current_position, previous_position, dt):
    """Hip velocity in pixels/second; positive is downward. dt is seconds."""
    _validate_interval(dt)
    return (current_position - previous_position) / dt


def vertical_acceleration(current_velocity, previous_velocity, dt):
    """Velocity change in pixels/second squared over dt seconds."""
    _validate_interval(dt)
    return (current_velocity - previous_velocity) / dt


def extract_features(keypoints, bbox, previous=None, *, dt=None):
    """Extract posture and motion without owning any tracking state.

    Pass the preceding output for the SAME person as ``previous`` and the
    elapsed seconds as ``dt``. For video datasets, use source timestamps;
    live callers can use a monotonic clock. Coordinates are image pixels.
    Callers must supply valid shoulder/hip coordinates: landmark confidence
    filtering is not performed here, matching the existing feature helpers.

    Velocity requires two observations; acceleration requires three. Missing
    derivatives are None, distinguishing missing history from no motion.
    Acceleration uses the separation between the midpoints of consecutive
    velocity intervals, so unequal sampling intervals are supported.
    ``sample_interval`` is temporal metadata needed by the next call.
    Legacy vertical_drop and movement remain per-observation displacements.
    """
    if dt is not None:
        _validate_interval(dt)
    if previous is not None and dt is None:
        raise ValueError("dt in seconds is required with a previous observation.")

    position = vertical_position(keypoints)
    center = body_center(bbox)
    features = {
        "torso_angle": torso_angle(keypoints),
        "hip_vertical_position": position,
        "bbox_width": bounding_box_width(bbox),
        "bbox_height": bounding_box_height(bbox),
        "aspect_ratio": bounding_box_aspect_ratio(bbox),
        "body_center": center,
        "vertical_drop": 0.0,
        "movement": 0.0,
        "vertical_velocity": None,
        "vertical_acceleration": None,
        "sample_interval": dt if previous is not None else None,
    }
    if previous is not None:
        features["vertical_drop"] = position - previous["hip_vertical_position"]
        features["movement"] = body_center_movement(center, previous["body_center"])
        velocity = vertical_velocity(position, previous["hip_vertical_position"], dt)
        features["vertical_velocity"] = velocity
        if previous["vertical_velocity"] is not None:
            previous_dt = previous["sample_interval"]
            _validate_interval(previous_dt)
            features["vertical_acceleration"] = vertical_acceleration(
                velocity, previous["vertical_velocity"], (dt + previous_dt) / 2,
            )
    return features
