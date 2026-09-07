import cv2
from ultralytics import YOLO

from src.core.fall_detection.detector import FallDetector
from src.core.fall_verification.verifier import FallVerifier


MODEL_PATH = "models/pose/yolov8n-pose.pt"


def main():
    model = YOLO(MODEL_PATH)

    fall_detector = FallDetector()
    fall_verifier = FallVerifier()

    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        raise RuntimeError("Could not open webcam.")

    while True:
        success, frame = camera.read()

        if not success:
            break

        results = model.track(
            frame,
            persist=True,
            conf=0.5,
            classes=[0],
            verbose=False,
        )

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

                verification = fall_verifier.update(
                    track_id,
                    detection["score"],
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

                label = (
                    f"ID {track_id} "
                    f"Fall: {detection['score']:.2f}"
                )

                cv2.putText(
                    frame,
                    label,
                    (x1, max(y1 - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                )

                if verification["confirmed"]:

                    cv2.putText(
                        frame,
                        "FALL CONFIRMED",
                        (50, 50),
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