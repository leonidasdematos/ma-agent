"""Planter field simulator that streams GNSS fixes to the monitor."""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from ..implement import ImplementProfile
from ..protocol.messages import Message, MessageType
from ..telemetry import TelemetryPublisher


_EARTH_RADIUS_M = 6_378_137.0


@dataclass(frozen=True)
class _Point:
    east_m: float
    north_m: float
    active: bool

@dataclass(frozen=True)
class _Sample:
    point: _Point
    heading_deg: float
    speed_mps: float
    time_delta_s: float


class PlanterSimulator(TelemetryPublisher):
    """Simulate a planter performing serpentine passes on a rectangular field."""

    def __init__(
        self,
        *,
        implement_profile: Optional[ImplementProfile] = None,
        field_length_m: float = 300.0,
        headland_length_m: float = 20.0,
        speed_mps: float = 2.5,
        sample_rate_hz: float = 10.0,
        base_lat: float = -22.000000,
        base_lon: float = -47.000000,
        altitude_m: float = 550.0,
        accuracy_m: float = 0.05,
        passes_per_cycle: int = 80,
        loop_forever: bool = True,
    ) -> None:
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if speed_mps <= 0:
            raise ValueError("speed_mps must be positive")
        if field_length_m <= 0:
            raise ValueError("field_length_m must be positive")
        if headland_length_m < 0:
            raise ValueError("headland_length_m must be non-negative")
        if passes_per_cycle < 2:
            raise ValueError("passes_per_cycle must be at least 2")

        self.implement_profile = implement_profile
        self.field_length_m = field_length_m
        self.headland_length_m = headland_length_m
        self.speed_mps = speed_mps
        self.sample_rate_hz = sample_rate_hz
        self.base_lat = base_lat
        self.base_lon = base_lon
        self.altitude_m = altitude_m
        self.accuracy_m = accuracy_m
        self.passes_per_cycle = passes_per_cycle
        self.loop_forever = loop_forever

        width_m = (implement_profile.row_count * implement_profile.row_spacing_m) if implement_profile else 13.0
        self.implement_width_m = width_m
        self.row_count = implement_profile.row_count if implement_profile else 26

        self._workers: dict = {}
        self._lock = threading.Lock()

    # TelemetryPublisher API -------------------------------------------------
    def register_session(self, session) -> None:
        worker = _PlanterWorker(simulator=self, session=session)
        with self._lock:
            self._workers[session] = worker
        worker.start()

    def unregister_session(self, session) -> None:
        with self._lock:
            worker = self._workers.pop(session, None)
        if worker:
            worker.stop()
            worker.join(timeout=2.0)

    def stop(self) -> None:
        """Stop all background workers."""

        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            worker.stop()
        for worker in workers:
            worker.join(timeout=2.0)

    # Helpers ----------------------------------------------------------------
    def _on_worker_finished(self, session) -> None:
        with self._lock:
            self._workers.pop(session, None)

    def _step_distance(self) -> float:
        return self.speed_mps / self.sample_rate_hz

    def _cycle_samples(self) -> List[_Sample]:
        step = self._step_distance()
        points: List[_Point] = []
        lane_index = 0
        direction = 1  # 1 => increasing north, -1 => decreasing
        last_point: Optional[Tuple[float, float]] = None
        passes_completed = 0
        target_passes = max(2, self.passes_per_cycle)

        while passes_completed < target_passes:
            x = lane_index * self.implement_width_m
            start_y = 0.0 if direction > 0 else self.field_length_m
            end_y = self.field_length_m if direction > 0 else 0.0

            for pt in self._interpolate((x, start_y), (x, end_y), step, last_point):
                points.append(_Point(pt[0], pt[1], True))
                last_point = pt

            headland_y = end_y + (direction * self.headland_length_m)
            if self.headland_length_m > 0:
                for pt in self._interpolate((x, end_y), (x, headland_y), step, last_point):
                    if pt == last_point:
                        continue
                    points.append(_Point(pt[0], pt[1], False))
                    last_point = pt

            next_lane = (lane_index + 1) % max(1, self.passes_per_cycle)
            next_x = next_lane * self.implement_width_m
            for pt in self._interpolate((x, headland_y), (next_x, headland_y), step, last_point):
                if pt == last_point:
                    continue
                points.append(_Point(pt[0], pt[1], False))
                last_point = pt

            next_direction = -direction
            start_next_y = 0.0 if next_direction > 0 else self.field_length_m
            for pt in self._interpolate((next_x, headland_y), (next_x, start_next_y), step, last_point):
                if pt == last_point:
                    continue
                points.append(_Point(pt[0], pt[1], False))
                last_point = pt

            lane_index = next_lane
            direction = next_direction
            passes_completed += 1

        samples: List[_Sample] = []
        last_heading = 0.0

        for index, point in enumerate(points):
            if index == 0 and len(points) > 1:
                reference = points[1]
                delta_east = reference.east_m - point.east_m
                delta_north = reference.north_m - point.north_m
            elif index > 0:
                previous = points[index - 1]
                delta_east = point.east_m - previous.east_m
                delta_north = point.north_m - previous.north_m
            else:
                delta_east = 0.0
                delta_north = 0.0

            distance = math.hypot(delta_east, delta_north)
            if distance > 0.0:
                heading = (math.degrees(math.atan2(delta_east, delta_north)) + 360.0) % 360.0
                base_speed = distance * self.sample_rate_hz
                speed_factor = 1.0 + self._speed_variation(index=index, is_active=point.active)
                speed = max(0.05, base_speed * speed_factor)
                last_heading = heading
                time_delta = distance / speed if speed > 0.0 else 1.0 / self.sample_rate_hz
            else:
                heading = last_heading
                speed = 0.0
                time_delta = 1.0 / self.sample_rate_hz

            samples.append(
                _Sample(point=point, heading_deg=heading, speed_mps=speed, time_delta_s=time_delta)
            )

        return samples

    def _speed_variation(self, *, index: int, is_active: bool) -> float:
        """Return a small multiplier offset applied to the base speed.

        The variation is deterministic so the path is repeatable, while still
        adding subtle changes that mimic the tractor slowing down on headlands
        and gentle oscillations along the pass.
        """

        oscillation = math.sin(index * 0.11) * 0.04  # +/- 4 % variation
        headland_adjustment = -0.06 if not is_active else 0.0
        variation = oscillation + headland_adjustment
        return max(-0.15, min(0.08, variation))


    @staticmethod
    def _interpolate(
        start: Tuple[float, float],
        end: Tuple[float, float],
        step: float,
        last_point: Optional[Tuple[float, float]],
    ) -> Iterable[Tuple[float, float]]:
        x0, y0 = start
        x1, y1 = end
        distance = math.hypot(x1 - x0, y1 - y0)
        if distance == 0:
            if last_point != (x0, y0):
                yield (x0, y0)
            return
        steps = max(1, int(math.ceil(distance / step)))
        for index in range(steps + 1):
            t = min(1.0, index / steps)
            point = (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
            if last_point == point:
                continue
            yield point

    def _to_geodetic(self, point: _Point) -> Tuple[float, float]:
        dlat = (point.north_m / _EARTH_RADIUS_M) * (180.0 / math.pi)
        dlon = (point.east_m / (_EARTH_RADIUS_M * math.cos(math.radians(self.base_lat)))) * (
            180.0 / math.pi
        )
        return (self.base_lat + dlat, self.base_lon + dlon)

    def _build_message(self, sample: _Sample, sequence: int) -> Message:
        point = sample.point
        latitude, longitude = self._to_geodetic(point)
        timestamp = time.time()
        sections = [point.active] * self.row_count
        payload = {
            "latitude": latitude,
            "longitude": longitude,
            "altitude": self.altitude_m,
            "accuracy": self.accuracy_m,
            "sequence": sequence,
            "timestamp": timestamp,
            "heading_deg": sample.heading_deg,
            "speed_mps": sample.speed_mps,
            "rtk_state": "FIXED" if point.active else "HOLD",
            "implement": {
                "active": point.active,
                "sections": sections,
            },
        }
        return Message(type=MessageType.GNSS_FIX, payload=payload)


class _PlanterWorker(threading.Thread):
    """Background thread that streams planter telemetry for a session."""

    daemon = True

    def __init__(self, *, simulator: PlanterSimulator, session) -> None:
        super().__init__(name=f"planter-sim-{id(session):x}")
        self.simulator = simulator
        self.session = session
        self._stop_event = threading.Event()
        self._cycle: Optional[List[_Sample]] = None

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        sequence = 1
        while not self._stop_event.is_set():
            if not self.session.can_stream():
                time.sleep(0.2)
                continue
            if self._cycle is None:
                self._cycle = self.simulator._cycle_samples()
                if not self._cycle:
                    return
            for sample in self._cycle:
                if self._stop_event.is_set():
                    break
                message = self.simulator._build_message(sample, sequence)
                sent = self.session.send_message(message)
                if sent:
                    sequence += 1
                time.sleep(sample.time_delta_s)
            if not self.simulator.loop_forever:
                break
        self.simulator._on_worker_finished(self.session)