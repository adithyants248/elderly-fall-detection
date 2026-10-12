"""Canonical contract recovered from Colab cells 4 and 6."""
from dataclasses import dataclass
from pathlib import Path

FALL_THRESHOLD = 0.30
WINDOW_SIZE = 60
STRIDE = 15
FEATURE_NAMES = (
    "shoulder_center_x", "shoulder_center_y", "hip_center_x", "hip_center_y",
    "knee_center_x", "knee_center_y", "ankle_center_x", "ankle_center_y",
    "torso_angle", "bbox_width", "bbox_height", "aspect_ratio",
    "person_confidence", "hip_vertical_velocity", "hip_vertical_acceleration",
    "hip_horizontal_velocity", "body_center_movement", "torso_angle_change",
    "aspect_ratio_change", "person_detected",
)
ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ArtifactPaths:
    # Original artifacts remain read-only; generated artifacts have one location.
    model: Path = ROOT / "colab_reference/ur_gru_fall_detector.keras"
    scaler: Path = ROOT / "colab_reference/scaler.pkl"
    medians: Path = ROOT / "models/fall_detection/train_medians.pkl"
    threshold: Path = ROOT / "colab_reference/selected_threshold.txt"
    pose: Path = ROOT / "models/pose/yolov8n-pose.pt"
