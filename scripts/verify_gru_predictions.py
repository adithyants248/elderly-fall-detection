"""Replay actual GRU output as JSONL through the post-fall decision layer.

Each line: {"track_id": 1, "timestamp": 0.0, "fall_probability": 0.3,
            "features": { ... raw training feature values ... }}
This does not run YOLO/GRU and does not send caregiver notifications.
"""
import argparse
import json
from pathlib import Path
import sys

from src.core.fall_verification.post_fall import PostFallVerifier
from src.core.fall_detection.model_schema import ArtifactPaths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSONL predictions file, or - for stdin")
    parser.add_argument("--threshold-path", type=Path,
                        default=ArtifactPaths().threshold)
    args = parser.parse_args()
    verifier = PostFallVerifier(threshold_path=args.threshold_path)
    stream = sys.stdin if args.input == "-" else open(args.input, encoding="utf-8")
    try:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                result = verifier.update(row["track_id"], row["fall_probability"],
                                         row["features"], row["timestamp"])
                verifier.cleanup_stale_tracks(timestamp=row["timestamp"])
            except (KeyError, TypeError, ValueError) as exc:
                parser.error(f"Line {line_number}: {exc}")
            print(json.dumps(result, allow_nan=False))
    finally:
        if stream is not sys.stdin:
            stream.close()


if __name__ == "__main__":
    main()
