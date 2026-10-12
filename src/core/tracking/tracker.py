from ultralytics import YOLO


class PersonTracker:
    """
    Tracks people across video frames using Ultralytics tracking.
    """

    def __init__(
        self,
        model_path: str = "yolov8n-pose.pt",
        confidence: float = 0.5,
        device=None,
        tracker=None,
    ):
        self.model = YOLO(model_path)
        self.confidence = confidence
        self.options = {}
        if device is not None:
            self.options["device"] = device
        if tracker is not None:
            self.options["tracker"] = tracker

    def track(self, frame):
        """
        Track people and estimate their poses.

        Returns:
            list of tracked people.
        """

        results = self.model.track(
            frame,
            persist=True,
            conf=self.confidence,
            classes=[0],
            verbose=False,
            **self.options,
        )

        people = []

        for result in results:

            if result.boxes is None:
                continue

            boxes = result.boxes

            keypoints = None

            if result.keypoints is not None:
                keypoints = result.keypoints.data.cpu().numpy()

            for index, box in enumerate(boxes):

                if box.id is None:
                    continue

                track_id = int(box.id[0])

                x1, y1, x2, y2 = box.xyxy[0].tolist()

                person = {
                    "track_id": track_id,
                    "bbox": (x1, y1, x2, y2),
                    "confidence": float(box.conf[0]),
                }

                if keypoints is not None:
                    person["keypoints"] = keypoints[index]

                people.append(person)

        return people
