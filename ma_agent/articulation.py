"""Kinematic helpers to model articulated implements.

This module mirrors the geometry used by the Android monitor so the
gateway can reproduce the same articulation behaviour when streaming
telemetry.  The calculations intentionally operate in the local ENU
frame (meters) where ``x`` points east and ``y`` points north.  Headings
follow the convention used by the mobile app: ``0`` radians points
towards the geographic north and rotations increase clockwise.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional, Tuple


EPS_STEP = 0.01  # Minimum displacement (m) to consider a heading update
EPS_IMPL = 0.01  # Minimum implement displacement (m) considered meaningful


@dataclass(frozen=True)
class Coordinate:
    """Simple 2D coordinate expressed in meters (local ENU frame)."""

    x: float
    y: float

    def delta(self, other: "Coordinate") -> Tuple[float, float]:
        """Return the displacement vector from ``other`` to ``self``."""

        return (self.x - other.x, self.y - other.y)

    def translate(self, dx: float, dy: float) -> "Coordinate":
        """Return a new coordinate translated by the provided offset."""

        return Coordinate(self.x + dx, self.y + dy)

    def distance_to(self, other: "Coordinate") -> float:
        """Return the Euclidean distance to ``other`` in meters."""

        return math.hypot(self.x - other.x, self.y - other.y)


@dataclass(frozen=True)
class ArticulationState:
    """Snapshot describing the articulated implement state."""

    last_center: Coordinate
    current_center: Coordinate
    articulation_point: Coordinate
    axis: Tuple[float, float]
    theta: float
    significant_motion: bool


def compute_articulated_centers(
    last_xy: Coordinate,
    cur_xy: Coordinate,
    *,
    fwd: Tuple[float, float],
    right: Tuple[float, float],
    distancia_antena: float,
    offset_longitudinal: float,
    offset_lateral: float,
    work_width_m: float,
    articulation_to_tool_m: Optional[float] = None,
    impl_theta_rad: Optional[float],
    tractor_heading_rad: Optional[float] = None,
    previous_displacement: Optional[Tuple[float, float]] = None,
    last_fwd: Optional[Tuple[float, float]] = None,
    last_right: Optional[Tuple[float, float]] = None,
) -> ArticulationState:
    """Compute articulated implement centres matching the monitor model.

    Parameters
    ----------
    last_xy, cur_xy:
        Antenna positions (meters) for the previous and current samples.
    fwd, right:
        Unit vectors representing the tractor forward and right directions
        for the current step.
    distancia_antena, offset_longitudinal, offset_lateral:
        Offsets that describe the antenna placement and hitch position
        relative to the tractor reference frame.
    work_width_m:
        Effective work width of the implement. Used to infer the distance
        between the articulation point and the implement centre when no
        dedicated parameter is available.
    articulation_to_tool_m:
        Optional explicit distance (in meters) between the articulation
        point and the implement centre. When omitted the helper derives a
        reasonable estimate from ``work_width_m``.
    impl_theta_rad:
        Cached implement heading (radians) from the previous step. When
        ``None`` the heading is initialised to the tractor heading.
    tractor_heading_rad:
        Optional external heading measurement (radians). Used when the
        displacement is too small to derive a reliable heading.
    previous_displacement:
        Optional displacement vector of the previous step. When provided it
        is used to estimate curvature and therefore the implement lag.
    last_fwd, last_right:
        Optional forward/right vectors associated with ``last_xy``. When
        unavailable the current orientation is used as a reasonable
        approximation.
    """
    """print(
        "\n[compute_articulated_centers] CHAMADA",
        f"\n last_xy = {last_xy}",
        f"\n cur_xy = {cur_xy}",
        f"\n fwd = {fwd}",
        f"\n right = {right}",
        f"\n distancia_antena = {distancia_antena}",
        f"\n offset_longitudinal = {offset_longitudinal}",
        f"\n offset_lateral = {offset_lateral}",
        f"\n work_width_m = {work_width_m}",
        f"\n articulation_to_tool_m = {articulation_to_tool_m}",
        f"\n impl_theta_rad = {impl_theta_rad}",
        f"\n tractor_heading_rad = {tractor_heading_rad}",
        f"\n previous_displacement = {previous_displacement}",
        f"\n last_fwd = {last_fwd}",
        f"\n last_right = {last_right}",
        "\n---------------------------------------------"
    )"""

    long_offset = distancia_antena + offset_longitudinal
    Lhitch = max(long_offset, 0.1)
    if articulation_to_tool_m is not None:
        Limpl = max(float(articulation_to_tool_m), 0.0)
    else:
        Limpl = max(0.5 * work_width_m, 1.0)


    # 1) Articulation point for the current step
    Jx = cur_xy.x - long_offset * fwd[0] + offset_lateral * right[0]
    Jy = cur_xy.y - long_offset * fwd[1] + offset_lateral * right[1]
    articulation_point = Coordinate(Jx, Jy)

    # 2) Tractor heading estimation
    displacement = cur_xy.delta(last_xy)
    dist = math.hypot(*displacement)
    if dist >= EPS_STEP:
        th_trac = math.atan2(displacement[0], displacement[1])
    elif tractor_heading_rad is not None:
        th_trac = tractor_heading_rad
    elif impl_theta_rad is not None:
        th_trac = impl_theta_rad
    else:
        th_trac = 0.0  # default to facing north

    # 2b) Estimate curvature from the change in displacement vectors
    if previous_displacement is not None and dist >= EPS_STEP:
        prev_dx, prev_dy = previous_displacement
        prev_dist = math.hypot(prev_dx, prev_dy)
        if prev_dist >= EPS_STEP:
            prev_heading = math.atan2(prev_dx, prev_dy)
            dpsi = _wrap_angle(math.atan2(displacement[0], displacement[1]) - prev_heading)
            kappa = dpsi / max(dist, 1e-6)
        else:
            kappa = 0.0
    else:
        kappa = 0.0

    # 2c) Update implement heading with a simple lag model
    if impl_theta_rad is None:
        theta_i = th_trac
    else:
        alpha = _clamp(Lhitch / (Lhitch + Limpl), 0.3, 0.9)
        theta_i = _wrap_angle(impl_theta_rad + alpha * kappa * dist)
        heading_error = _wrap_angle(th_trac - theta_i)
        relax_rate = _clamp(dist / max(Limpl, 0.1), 0.0, 1.0)
        theta_i = _wrap_angle(theta_i + (1.0 - alpha) * heading_error * relax_rate)

    # 3) Implement axis and centres
    # The implement trails the tractor, so its centre lies behind the
    # articulation point relative to the heading. The monitor expects the axis
    # to point from the articulation towards the tool (i.e., backwards). Use
    # the negative heading vectors to ensure the implement is positioned
    # behind the hitch instead of in front of the tractor.
    axis_x = -math.sin(theta_i)
    axis_y = -math.cos(theta_i)
    axis_norm = math.hypot(axis_x, axis_y) or 1.0
    axis = (axis_x / axis_norm, axis_y / axis_norm)

    cur_impl = articulation_point.translate(Limpl * axis[0], Limpl * axis[1])

    # Previous articulation point (best effort when orientation data missing)
    fwd_prev = last_fwd if last_fwd is not None else fwd
    right_prev = last_right if last_right is not None else right
    Jlx = last_xy.x - long_offset * fwd_prev[0] + offset_lateral * right_prev[0]
    Jly = last_xy.y - long_offset * fwd_prev[1] + offset_lateral * right_prev[1]
    axis_prev = impl_theta_rad
    if axis_prev is None:
        last_axis = axis
    else:
        last_axis = (
            -math.sin(axis_prev),
            -math.cos(axis_prev),
        )
        norm = math.hypot(*last_axis) or 1.0
        last_axis = (last_axis[0] / norm, last_axis[1] / norm)
    last_impl = Coordinate(Jlx + Limpl * last_axis[0], Jly + Limpl * last_axis[1])

    significant_motion = cur_impl.distance_to(last_impl) >= EPS_IMPL

    print(
        "\n[ARTICULATION DEBUG]",
        f"\n  Tractor:",
        f"\n    last_xy = {last_xy}",
        f"\n    cur_xy = {cur_xy}",
        f"\n    displacement = {displacement}",
        f"\n    dist = {dist:.4f} m",
        f"\n    tractor_heading (rad) = {th_trac:.4f}",
        f"\n",
        f"\n  Curvature:",
        f"\n    previous_displacement = {previous_displacement}",
        f"\n    kappa = {kappa:.6f} rad/m",
        f"\n",
        f"\n  Implement:",
        f"\n    impl_theta (rad) = {theta_i:.4f}",
        f"\n    impl_theta (deg) = {math.degrees(theta_i):.2f}°",
        f"\n    axis = {axis}",
        f"\n    articulation_point = {articulation_point}",
        f"\n    last_center = {last_impl}",
        f"\n    current_center = {cur_impl}",
        f"\n    movement = {cur_impl.distance_to(last_impl):.4f} m",
        f"\n    significant_motion = {significant_motion}",
        "\n---------------------------------------------"
    )


    return ArticulationState(
        last_center=last_impl,
        current_center=cur_impl,
        articulation_point=articulation_point,
        axis=axis,
        theta=theta_i,
        significant_motion=significant_motion,
    )


def _wrap_angle(angle: float) -> float:
    """Wrap an angle to the ``[-pi, pi)`` interval."""

    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Return ``value`` constrained to the ``[minimum, maximum]`` range."""

    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


__all__ = [
    "ArticulationState",
    "Coordinate",
    "EPS_IMPL",
    "EPS_STEP",
    "compute_articulated_centers",
]