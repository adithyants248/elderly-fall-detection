"""Causal live onset evidence, separate from the trained 20-feature tensor.

Engineering defaults, not learned activity labels: within one second require
hip displacement of 25% of prior box height plus a 20-degree torso change or
0.25 aspect change. A 40% downward displacement also supports an axial collapse.
No absolute final posture is classified as safe or unsafe.

A separate engineering-only temporal route requires a post-warmup stable
baseline, coherent multi-observation descent, and a changed configuration.
It retains qualifying evidence briefly for the caller's unchanged quiet gate.
"""
from collections import deque
import math
from statistics import median


class TransitionEvidence:
    # Initial engineering parameters for the ADDITIONAL route, not clinical
    # thresholds. The original geometry route below is deliberately unchanged.
    BASELINE_SECONDS = .5
    EPISODE_SECONDS = 1.0
    EVIDENCE_SECONDS = .1
    PENDING_SECONDS = 1.0
    TEMPORAL_NAMES = ("shoulder_center_x", "shoulder_center_y", "hip_center_x",
                      "hip_center_y", "bbox_height", "torso_angle", "aspect_ratio")
    # Distances use the frozen baseline box height. Downward/shortening/shrink
    # are signed. Require both whole-body descent and configuration change:
    # upright sitting, horizontal walking and hip-stationary bending do not pass.
    ENDPOINT_FLOORS = {"hip_down": .06, "shoulder_down": .10,
                       "height_shrink": .08, "torso_shortening": .06,
                       "angle_change": 12., "aspect_change": .12}

    def __init__(self):
        self.history = deque(maxlen=120)
        self._reset_temporal()

    def _reset_temporal(self):
        self.baseline_rows = deque(maxlen=120)
        self.baseline = None
        self.endpoint_limits = {}
        self.previous_pose = None
        self.episode_at = None
        self.moving_times = deque(maxlen=120)
        self.hip_path = self.shoulder_path = self.largest_step = 0.
        self.pending_at = None

    def reset(self):
        self.history.clear()
        self._reset_temporal()

    def update(self, row, timestamp, ready, *, max_gap_seconds=.5):
        names = ("hip_center_x", "hip_center_y", "bbox_height", "torso_angle", "aspect_ratio")
        if not ready or row["person_detected"] != 1 or not all(
            math.isfinite(row[n]) for n in names
        ) or row["bbox_height"] <= 0:
            self.reset()
            self.diagnostics = self._diagnostics(row, timestamp, ready)
            self._publish_temporal(False, timestamp, self.diagnostics["false_reason"])
            self.diagnostics["geometry_supported"] = False
            self.diagnostics["geometry_false_reason"] = self.diagnostics["false_reason"]
            self.diagnostics["combined_supported"] = False
            return False
        while self.history and timestamp - self.history[0][0] > 1.0:
            self.history.popleft()
        self.diagnostics = self._diagnostics(row, timestamp, ready)
        supported = False
        for _, prior in self.history:
            dx = row["hip_center_x"] - prior["hip_center_x"]
            dy = row["hip_center_y"] - prior["hip_center_y"]
            height = prior["bbox_height"]
            posture_change = (abs(row["torso_angle"] - prior["torso_angle"]) >= 20
                              or abs(row["aspect_ratio"] - prior["aspect_ratio"]) >= .25)
            if (math.hypot(dx, dy) / height >= .25 and posture_change) or dy / height >= .4:
                supported = True
                break
        self.history.append((timestamp, row.copy()))
        temporal = self._update_temporal(row, timestamp, max_gap_seconds)
        self.diagnostics["geometry_supported"] = supported
        self.diagnostics["geometry_false_reason"] = self.diagnostics["false_reason"]
        self.diagnostics["combined_supported"] = supported or temporal
        if supported or temporal:
            self.diagnostics["false_reason"] = None
        return supported or temporal

    @staticmethod
    def _changes(row, baseline):
        height = baseline["bbox_height"]
        hip_dx = row["hip_center_x"] - baseline["hip_center_x"]
        hip_dy = row["hip_center_y"] - baseline["hip_center_y"]
        shoulder_dx = row["shoulder_center_x"] - baseline["shoulder_center_x"]
        shoulder_dy = row["shoulder_center_y"] - baseline["shoulder_center_y"]
        def length(pose):
            return math.hypot(pose["shoulder_center_x"] - pose["hip_center_x"],
                              pose["shoulder_center_y"] - pose["hip_center_y"])
        return {"hip_distance": math.hypot(hip_dx, hip_dy) / height,
                "shoulder_distance": math.hypot(shoulder_dx, shoulder_dy) / height,
                "hip_down": hip_dy / height, "shoulder_down": shoulder_dy / height,
                "torso_shortening": (length(baseline) - length(row)) / height,
                "height_shrink": (height - row["bbox_height"]) / height,
                "angle_change": abs(row["torso_angle"] - baseline["torso_angle"]),
                "aspect_change": abs(row["aspect_ratio"] - baseline["aspect_ratio"])}

    def _publish_temporal(self, supported, now, reason, changes=None, **extra):
        # Snapshot for this decision. GRUInference reports any subsequent
        # consumption separately; reset() must not erase the decision snapshot.
        self.diagnostics["temporal"] = {
            "baseline_ready": self.baseline is not None,
            "supported": bool(supported),
            "episode_state": ("pending" if self.pending_at is not None else
                              "moving" if self.episode_at is not None else
                              "armed" if self.baseline is not None else "baseline"),
            "episode_age_seconds": None if self.episode_at is None else float(now - self.episode_at),
            "movement_observations": len(self.moving_times),
            "movement_span_seconds": float(self.moving_times[-1] - self.moving_times[0])
                if len(self.moving_times) > 1 else 0.,
            "changes": changes or {}, "endpoint_limits": self.endpoint_limits.copy(),
            "pending": self.pending_at is not None,
            "pending_age_seconds": None if self.pending_at is None else float(now - self.pending_at),
            "rejection_reason": reason, **extra,
        }
        return supported

    def _update_temporal(self, row, now, max_gap_seconds):
        # Missing shoulders cannot disable the independent original geometry route.
        if not all(n in row and math.isfinite(row[n]) for n in self.TEMPORAL_NAMES):
            self._reset_temporal()
            return self._publish_temporal(False, now, "invalid_temporal_geometry")
        row = {n: float(row[n]) for n in self.TEMPORAL_NAMES}
        if math.hypot(row["shoulder_center_x"] - row["hip_center_x"],
                      row["shoulder_center_y"] - row["hip_center_y"]) <= 0:
            self._reset_temporal()
            return self._publish_temporal(False, now, "degenerate_torso")
        previous = self.previous_pose
        if previous is not None and (now <= previous[0] or now - previous[0] > max_gap_seconds):
            self._reset_temporal()
            self.previous_pose = (now, row)
            return self._publish_temporal(False, now, "observation_gap")
        self.previous_pose = (now, row)
        if self.baseline is None:
            self.baseline_rows.append((now, row))
            # Retain the sample straddling the duration boundary, not a FPS assumption.
            while len(self.baseline_rows) > 1 and now - self.baseline_rows[1][0] >= self.BASELINE_SECONDS:
                self.baseline_rows.popleft()
            if len(self.baseline_rows) < 3 or now - self.baseline_rows[0][0] < self.BASELINE_SECONDS:
                return self._publish_temporal(False, now, "collecting_baseline")
            baseline = {n: median(p[n] for _, p in self.baseline_rows) for n in self.TEMPORAL_NAMES}
            changes = [self._changes(p, baseline) for _, p in self.baseline_rows]
            noise = {n: max(abs(c[n]) for c in changes) for n in changes[0]}
            stable = all(noise[n] <= limit for n, limit in (
                ("hip_distance", .015), ("shoulder_distance", .015),
                ("height_shrink", .02), ("torso_shortening", .02),
                ("angle_change", 3.), ("aspect_change", .03)))
            if not stable:
                return self._publish_temporal(False, now, "baseline_unstable")
            self.baseline = baseline
            self.endpoint_limits = {n: max(floor, 4 * noise[n]) for n, floor in self.ENDPOINT_FLOORS.items()}
            self.baseline_rows.clear()
            return self._publish_temporal(False, now, "awaiting_movement")

        changes = self._changes(row, self.baseline)
        endpoint = (all(changes[n] >= self.endpoint_limits[n]
                        for n in ("hip_down", "shoulder_down", "height_shrink"))
                    and (changes["torso_shortening"] >= self.endpoint_limits["torso_shortening"]
                         or (changes["angle_change"] >= self.endpoint_limits["angle_change"]
                             and changes["aspect_change"] >= self.endpoint_limits["aspect_change"])))
        if self.pending_at is not None:
            reason = ("pending_expired" if now >= self.pending_at + self.PENDING_SECONDS else
                      "endpoint_recovered" if not endpoint else None)
            if reason:
                self._reset_temporal()
                return self._publish_temporal(False, now, reason, changes)
            return self._publish_temporal(True, now, None, changes, endpoint_passed=True)

        if self.episode_at is None:
            if max(changes["hip_distance"], changes["shoulder_distance"]) < .025:
                return self._publish_temporal(False, now, "awaiting_movement", changes)
            self.episode_at = previous[0]
        if now > self.episode_at + self.EPISODE_SECONDS:
            self._reset_temporal()
            return self._publish_temporal(False, now, "episode_expired", changes)
        # Compare successive actual observations, never accumulated imputed motion.
        step = self._changes(row, previous[1])
        scale = previous[1]["bbox_height"] / self.baseline["bbox_height"]
        hip_step, shoulder_step = step["hip_distance"] * scale, step["shoulder_distance"] * scale
        self.hip_path += hip_step
        self.shoulder_path += shoulder_step
        self.largest_step = max(self.largest_step, hip_step + shoulder_step)
        dt = now - previous[0]
        if step["hip_down"] * scale / dt >= .02 and step["shoulder_down"] * scale / dt >= .02:
            self.moving_times.append(now)
        persistent = len(self.moving_times) >= 3 and self.moving_times[-1] - self.moving_times[0] >= self.EVIDENCE_SECONDS
        # Net displacement must dominate oscillation, and no single step may
        # account for most of the motion (jump followed by stillness/jitter).
        coherent = (changes["hip_distance"] >= .75 * self.hip_path
                    and changes["shoulder_distance"] >= .75 * self.shoulder_path
                    and self.largest_step <= .65 * (self.hip_path + self.shoulder_path))
        if persistent and coherent and endpoint:
            self.pending_at = now  # Fixed expiry; high probability/stillness never renews it.
        reason = ("insufficient_persistent_motion" if not persistent else
                  "incoherent_motion" if not coherent else
                  "endpoint_not_changed" if not endpoint else None)
        return self._publish_temporal(self.pending_at is not None, now, reason, changes,
                                      endpoint_passed=endpoint, coherent_motion=coherent)

    def _diagnostics(self, row, timestamp, ready):
        """Debug-only snapshot before appending this frame; never drives decisions.

        History count/age describe eligible prior rows used for this decision.
        Scan all rows even when the decision loop would stop at its first match.
        """
        names = ("hip_center_x", "hip_center_y", "bbox_height", "torso_angle", "aspect_ratio")
        geometry_valid = all(math.isfinite(row[n]) for n in names) and row["bbox_height"] > 0
        values = []
        if ready and row["person_detected"] == 1 and geometry_valid:
            for _, prior in self.history:
                dx = row["hip_center_x"] - prior["hip_center_x"]
                dy = row["hip_center_y"] - prior["hip_center_y"]
                values.append((math.hypot(dx, dy) / prior["bbox_height"],
                               dy / prior["bbox_height"],
                               abs(row["torso_angle"] - prior["torso_angle"]),
                               abs(row["aspect_ratio"] - prior["aspect_ratio"])))
        route_1 = any(distance >= .25 and (angle >= 20 or aspect >= .25)
                      for distance, _, angle, aspect in values)
        route_2 = any(downward >= .4 for _, downward, _, _ in values)
        reason = ("model_not_ready" if not ready else
                  "person_not_detected" if row["person_detected"] != 1 else
                  "invalid_geometry" if not geometry_valid else
                  "no_eligible_previous_observation" if not values else
                  "route_thresholds_not_met" if not (route_1 or route_2) else None)
        # Native finite floats/None keep missing poses valid for strict JSON.
        return {
            **{n: float(row[n]) if math.isfinite(row[n]) else None for n in names},
            "history_rows": len(self.history),
            "oldest_history_age_seconds": float(timestamp - self.history[0][0]) if self.history else None,
            **{name: float(max(v[i] for v in values)) if values else None
               for i, name in enumerate(("max_distance_ratio", "max_downward_ratio",
                                         "max_angle_change", "max_aspect_change"))},
            "route_1_passed": route_1,
            "route_2_passed": route_2,
            "model_ready_passed": bool(ready),
            "person_detected_passed": bool(row["person_detected"] == 1),
            "geometry_valid_passed": bool(geometry_valid),
            "eligible_previous_observation": bool(values),
            "false_reason": reason,
        }
