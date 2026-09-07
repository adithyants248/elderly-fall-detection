from ultralytics import YOLO


class PersonDetector:
    """
    Detects people in images/video frames using a pretrained YOLO model.
    """

    PERSON_CLASS_ID = 0

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        confidence: float = 0.5,
    ):
        self.model = YOLO(model_path)
        self.confidence = confidence

    def detect(self, frame):
        """
        Detect people in a single frame.

        Returns:
            list of dictionaries containing bounding box and confidence.
        """

        results = self.model(
            frame,
            conf=self.confidence,
            verbose=False,
        )

        detections = []

        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                class_id = int(box.cls[0])

                if class_id != self.PERSON_CLASS_ID:
                    continue

                x1, y1, x2, y2 = box.xyxy[0].tolist()
                confidence = float(box.conf[0])

                detections.append(
                    {
                        "bbox": (x1, y1, x2, y2),
                        "confidence": confidence,
                    }
                )

        return detections