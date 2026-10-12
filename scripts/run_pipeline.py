from src.core.fall_detection.detector import FallDetector


MODEL_PATH = "models/pose/yolov8n-pose.pt"


def display_status(track_id, detection):
    """Build one per-person status line from the detector's actual result."""
    state = (
        "FALL CONFIRMED" if detection["fall_confirmed"]
        else "FALL VERIFIED" if detection["fall_verified"]
        else "FALL CANDIDATE" if detection["fall_candidate"]
        else "NORMAL"
    )
    verification = detection["verification"]
    inactivity = detection["inactivity"]
    text = (
        f"ID {track_id} {state} | "
        f"V {verification['elapsed_seconds']:.1f}/{verification['verification_window_seconds']:.1f}s "
        f"I {inactivity['elapsed_seconds']:.1f}/{inactivity['required_seconds']}s | "
        f"{verification['reset_reason'] or (inactivity['reason'] if detection['fall_verified'] else verification['reason'])}"
    )
    return text


def main():
    import cv2
    from ultralytics import YOLO

    model = YOLO(MODEL_PATH)

    # Explicit duration: webcam FPS must not determine the stillness wait.
    fall_detector = FallDetector(inactivity_seconds=2.0)

    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        raise RuntimeError("Could not open webcam.")

    while True:
        success, frame = camera.read()

        if not success:
            break

        fall_detector.cleanup_stale_tracks()

        results = model.track(
            frame,
            persist=True,
            conf=0.5,
            classes=[0],
            verbose=False,
        )

        status_row = 0
        for result in results:

            if result.boxes is None:
                continue

            if result.keypoints is None:
                continue

            boxes = result.boxes

            # Get pose keypoints
            keypoints = result.keypoints.data.cpu().numpy()

            for index, box in enumerate(boxes):

                if box.id is None:
                    continue

                track_id = int(box.id[0])

                bbox = box.xyxy[0].tolist()

                person_keypoints = keypoints[index]

                # ------------------------------------------------
                # DRAW 17 POSE KEYPOINTS
                # ------------------------------------------------

                for x, y, confidence in person_keypoints:

                    if confidence < 0.5:
                        continue

                    cv2.circle(
                        frame,
                        (int(x), int(y)),
                        5,
                        (255, 0, 0),
                        -1,
                    )

                # ------------------------------------------------
                # FALL DETECTION
                # ------------------------------------------------

                person = {
                    "track_id": track_id,
                    "bbox": tuple(bbox),
                    "keypoints": person_keypoints,
                }

                detection = fall_detector.analyze(person)

                # Temporary per-person debug output.
                verification = detection["verification"]
                print(
                    f"ID: {track_id} | Score: {detection['score']:.2f} | "
                    f"Candidate: {detection['fall_candidate']} | "
                    f"Verified: {detection['fall_verified']} | "
                    f"Inactive: {detection['post_fall_inactive']} | "
                    f"Confirmed: {detection['fall_confirmed']} | "
                    f"Active: {verification['verification_active']} | "
                    f"Start: {verification['verification_start_time']} | "
                    f"Elapsed: {verification['elapsed_verification_seconds']:.3f}s | "
                    f"Window: {verification['verification_window_seconds']:.2f}s | "
                    f"Timestamp: {verification['timestamp']:.3f} | "
                    f"Gap: {verification['observation_gap_seconds']} | "
                    f"Lying: {verification['lying']} | "
                    f"Reason: {verification['reason']} | "
                    f"Reset: {verification['reset_reason']} | "
                    f"Still: {detection['inactivity']['elapsed_seconds']:.2f}s | "
                    f"Movement: {detection['inactivity']['movement']:.2f}px | "
                    f"Inactivity reason: {detection['inactivity']['reason']}"
                )

                # ------------------------------------------------
                # DRAW BOUNDING BOX
                # ------------------------------------------------

                x1, y1, x2, y2 = map(int, bbox)

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    2,
                )

                # ------------------------------------------------
                # DISPLAY INFORMATION
                # ------------------------------------------------

                label = display_status(track_id, detection)
                color = (0, 0, 255) if detection["fall_confirmed"] else (0, 255, 0)
                scale = 0.5
                text_width = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0]
                scale *= min(1.0, (frame.shape[1] - 20) / max(text_width, 1))
                row_y = 22 + status_row * 28
                status_row += 1
                cv2.rectangle(frame, (0, row_y - 20), (frame.shape[1], row_y + 5), (0, 0, 0), -1)

                cv2.putText(
                    frame,
                    label,
                    (10, row_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    scale,
                    color,
                    1,
                )

                if detection["fall_confirmed"]:

                    cv2.putText(
                        frame,
                        f"ID {track_id}: FALL CONFIRMED",
                        (10, min(frame.shape[0] - 10, y2)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.0,
                        (0, 0, 255),
                        3,
                    )

        cv2.imshow(
            "Elderly Fall Detection",
            frame,
        )

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break

    camera.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
