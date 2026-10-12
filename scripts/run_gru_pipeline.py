"""GRU camera/video inference; q quits, r resets ML episodes (not caregiver acknowledgement).

First-person selection follows Colab (no identity guarantee). --selection tracked
reuses PersonTracker with ByteTrack; that mode is a deployment difference.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path

from src.core.fall_detection.model_schema import ArtifactPaths
from src.core.fall_detection.camera import GRUCameraSource, first_person



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="0", help="Camera index or video filename")
    parser.add_argument("--selection", choices=("first", "tracked"), default="first")
    parser.add_argument("--device", default=None, help="YOLO device: cpu or 0; auto by default")
    defaults = ArtifactPaths()
    for name in ("model", "scaler", "medians", "threshold", "pose"):
        parser.add_argument(f"--{name}", type=Path, default=getattr(defaults, name))
    args = parser.parse_args()
    import cv2
    paths = replace(defaults, **{name: getattr(args, name) for name in ("model", "scaler", "medians", "threshold", "pose")})
    source = GRUCameraSource(args.source, args.selection, args.device, paths)
    try:
        source.open()
        while True:
            observation = source.read()
            if observation is None:
                break
            frame, results = observation
            for row_index, result in enumerate(results):
                track_id = result["track_id"]
                probability = result["fall_probability"]
                probability_text = "warmup" if probability is None else f"{probability:.3f}"
                label = (f"ID {track_id} {result['state']} | P {probability_text} | "
                         f"{result['buffer_frames']}/60 | {result['elapsed_seconds']:.1f}s | {result['reason']}")
                color = (0, 0, 255) if result["fall_confirmed"] else (0, 255, 0)
                width = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
                scale = 0.5 * min(1.0, (frame.shape[1] - 20) / max(width, 1))
                y = 25 + row_index * 28
                cv2.rectangle(frame, (0, y - 20), (frame.shape[1], y + 5), (0, 0, 0), -1)
                cv2.putText(frame, label, (10, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1)
                if result["event"] is not None:
                    print(json.dumps(result["event"]))  # local event only
            cv2.imshow("GRU Fall Detection - q quit / r reset", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("r"):
                source.reset_all()
    finally:
        source.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
