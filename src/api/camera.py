"""One application-owned thread, existing context consumer, volatile delivery retry."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
from threading import Event, RLock, Thread
import time

from src.core.fall_detection.camera import CameraUnavailable, GRUCameraSource
from src.caregiver.models import InvalidTransitionError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraConfig:
    enabled: bool = False
    source: str = "0"
    selection: str = "first"
    device: str | None = None

    @classmethod
    def from_env(cls):
        return cls(enabled=os.getenv("FALL_CAMERA_ENABLED", "0") == "1",
                   source=os.getenv("FALL_CAMERA_SOURCE", "0"),
                   selection=os.getenv("FALL_CAMERA_SELECTION", "first"),
                   device=os.getenv("FALL_CAMERA_DEVICE") or None)


def create_source(config):
    return GRUCameraSource(config.source, config.selection, config.device)


class CameraWorker:
    """Camera, model, verifier and pending deliveries have one writer: this thread.

    Status/request access uses a short lock, never around camera/model work.
    Stop is cooperative and joins the thread after the current native operation;
    Python cannot interrupt a hung camera driver or model call safely.
    """
    def __init__(self, context, config=None, *, source_factory=create_source, retry_seconds=1.0):
        self.context = context
        self.config = config or CameraConfig()
        self.source_factory = source_factory
        self.retry_seconds = retry_seconds
        self._lock = RLock()
        self._stop = Event()
        self._thread = None
        self._pending = {}
        self._delivered = set()
        self._episodes = {}
        self._reset_ids = set()
        self._state = "disabled" if not self.config.enabled else "stopped"
        self._message = "Camera mode disabled." if not self.config.enabled else "Worker not started."
        self._frames = 0
        self._last_frame_at = None
        self._diagnostics = {}

    def status(self):
        with self._lock:
            return dict(camera_enabled=self.config.enabled, camera_status=self._state,
                        ai_status=self._state, message=self._message,
                        frames_processed=self._frames, last_frame_at=self._last_frame_at,
                        pending_events=len(self._pending), latched_events=len(self._episodes),
                        reset_requested=bool(self._reset_ids), diagnostics=deepcopy(self._diagnostics))

    def _set_state(self, state, message):
        with self._lock:
            self._state, self._message = state, message

    def start(self):
        with self._lock:
            if not self.config.enabled or self._thread is not None:
                return
            self._set_state("starting", "Opening camera and loading AI models.")
            self._thread = Thread(target=self._run, name="fall-camera", daemon=False)
            try:
                self._thread.start()
            except Exception:
                self._thread = None
                self._set_state("error", "Camera worker could not start. Demo remains available.")
                logger.exception("Camera thread startup failed")

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join()  # No abandoned thread; resource release is in _run finally.

    def request_reset(self):
        with self._lock:
            if self._state != "running" or self._pending or not self._episodes:
                raise InvalidTransitionError("Rearm requires a running worker and delivered camera events.")
            ids = set(self._episodes)
            if not self.context.camera_events_acknowledged(ids):
                raise InvalidTransitionError("Check the person and acknowledge camera alerts before rearming.")
            self._reset_ids.update(ids)
        return self.status()

    def _apply_resets(self, source):
        with self._lock:
            ids = tuple(self._reset_ids)
            self._reset_ids.clear()
        for event_id in ids:
            # Only explicitly requested, already delivered/acknowledged episodes.
            source.reset(self._episodes[event_id])
            with self._lock:
                self._episodes.pop(event_id)

    def _retain(self, result):
        if result.get("state") != "CONFIRMED_FALL" or result.get("event") is None:
            return
        event_id = result["event"]["event_id"]
        with self._lock:
            if event_id not in self._delivered:
                is_new = event_id not in self._pending
                self._pending.setdefault(event_id, deepcopy(result))
                self._episodes[event_id] = result["event"]["track_id"]
                return is_new
        return False

    def _deliver(self):
        with self._lock:
            pending = list(self._pending.items())
        for event_id, result in pending:
            try:
                accepted = self.context.consume_verification_result(deepcopy(result))
                if accepted is None or accepted.event_id != event_id:
                    raise RuntimeError("Consumer did not accept the confirmed event.")
            except Exception:
                logger.exception("Confirmed camera event retained for retry: %s", event_id)
            else:
                with self._lock:
                    self._pending.pop(event_id)
                    self._delivered.add(event_id)

    def _run(self):
        source = None
        next_retry = 0.0
        try:
            source = self.source_factory(self.config)
            source.open()
            while not self._stop.is_set():
                self._apply_resets(source)
                observation = source.read()
                if observation is None:
                    self._set_state("stopped", "Video ended. Demo remains available.")
                    break
                _, results = observation
                for result in results:
                    with self._lock:
                        self._diagnostics = {key: result.get(key) for key in (
                            "buffer_frames", "warmup", "temporal_ready", "transition_supported",
                            "transition_diagnostics",
                            "observation_interval_seconds", "inference_seconds",
                            "person_detected", "fall_probability", "fall_threshold", "state", "reason")}
                        self._diagnostics["event_created"] = result.get("event") is not None
                    if result.get("event") is not None or self._frames % 150 == 0:
                        logger.info("Camera frames=%d diagnostics=%s", self._frames, self._diagnostics)
                    is_new = self._retain(result)
                    if is_new or time.monotonic() >= next_retry:
                        self._deliver()
                        next_retry = time.monotonic() + self.retry_seconds
                if time.monotonic() >= next_retry:
                    self._deliver()
                    next_retry = time.monotonic() + self.retry_seconds
                with self._lock:
                    self._frames += 1
                    self._last_frame_at = datetime.now(timezone.utc)
                self._set_state("running", "Processing camera/video frames. Model warmup requires 60 frames.")
        except CameraUnavailable:
            self._set_state("unavailable", "Camera/video unavailable. Check the source; demo remains available.")
            logger.exception("Camera/video source unavailable")
        except Exception:
            self._set_state("error", "AI worker failed. Check server logs; demo remains available.")
            logger.exception("Camera/GRU worker failed")
        finally:
            if source is not None:
                try:
                    source.close()
                except Exception:
                    self._set_state("error", "Camera cleanup failed. Check server logs.")
                    logger.exception("Camera cleanup failed")
            # Retry even after EOF, camera loss, or inference failure. Keep the
            # original result until accepted, including on shutdown's last try.
            self._deliver()
            while self.status()["pending_events"] and not self._stop.wait(self.retry_seconds):
                self._deliver()
            if self._stop.is_set():
                self._deliver()
                self._set_state("stopped", "Camera worker stopped.")
            if self.status()["pending_events"]:
                logger.warning("Shutdown retains %d undelivered events in memory only",
                               self.status()["pending_events"])
