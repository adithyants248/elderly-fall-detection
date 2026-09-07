from collections import defaultdict, deque


class FallVerifier:
    def __init__(self, window_size=30, confirmation_threshold=0.66):
        self.window_size = window_size
        self.confirmation_threshold = confirmation_threshold

        self.history = defaultdict(
            lambda: deque(maxlen=window_size)
        )

        self.confirmed = set()

    def update(self, track_id, fall_score):
        history = self.history[track_id]
        history.append(fall_score)

        # print(
        #     f"ID {track_id} | score={fall_score:.2f} | "
        #     f"recent={list(history)[-5:]}"
        # )

        # Need a short sequence before making a decision
        if len(history) < 5:
            return {
                "confirmed": False,
                "confidence": 0.0
            }

        # Look at the most recent 5 frames
        recent_scores = list(history)[-5:]

        # Count how many frames look like a fall
        fall_frames = sum(
            score >= self.confirmation_threshold
            for score in recent_scores
        )

        # Confirm if at least 3 of the last 5 frames
        # show a strong fall signal
        confirmed = fall_frames >= 3

        if confirmed:
            self.confirmed.add(track_id)

        confidence = fall_frames / 5

        return {
            "confirmed": confirmed,
            "confidence": confidence
        }

    def reset(self, track_id):
        self.history.pop(track_id, None)
        self.confirmed.discard(track_id)