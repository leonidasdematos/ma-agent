from __future__ import annotations

import json
import time

import pytest

from ma_agent.implement import load_implement_profile
from ma_agent.protocol.messages import Message, MessageType
from ma_agent.session import GatewaySession
from ma_agent.simulators import PlanterSimulator


def test_planter_simulator_generates_rows_and_headland():
    implement = load_implement_profile()
    simulator = PlanterSimulator(
        implement_profile=implement,
        field_length_m=20.0,
        headland_length_m=3.0,
        speed_mps=130.0,
        sample_rate_hz=5.0,
        passes_per_cycle=2,
        loop_forever=False,
        base_lat=-22.0,
        base_lon=-47.0,
    )

    session = GatewaySession(telemetry_publisher=simulator)
    captured = []
    session.attach_sender(captured.append)

    hello = Message(type=MessageType.HELLO, payload={})
    session.handle_message(hello)

    # Wait for the simulator worker to finish emitting the cycle.
    deadline = time.time() + 5.0
    while True:
        with simulator._lock:  # type: ignore[attr-defined]
            worker = simulator._workers.get(session)  # type: ignore[attr-defined]
        if worker is None or not worker.is_alive():
            break
        if time.time() > deadline:
            raise AssertionError("planter simulator worker did not finish in time")
        time.sleep(0.05)

    session.close()

    assert captured, "expected simulator to emit telemetry messages"
    active_states = [msg.payload["implement"]["active"] for msg in captured]
    assert any(active_states), "should have planter active during passes"
    assert any(not state for state in active_states), "should disable planter on headland"

    active_msg = next(msg for msg in captured if msg.payload["implement"]["active"])
    inactive_msg = next(msg for msg in captured if not msg.payload["implement"]["active"])

    full_mask = (1 << implement.row_count) - 1
    assert active_msg.payload["implement"]["sections_mask"] == full_mask
    assert inactive_msg.payload["implement"]["sections_mask"] == 0

    implement_payloads = [msg.payload["implement"] for msg in captured]
    assert any(payload.get("mode") == "articulated" for payload in implement_payloads)


def test_planter_simulator_accepts_explicit_route_points():
    simulator = PlanterSimulator(
        field_length_m=20.0,
        headland_length_m=0.0,
        speed_mps=5.0,
        sample_rate_hz=5.0,
        passes_per_cycle=2,
        loop_forever=False,
        route_points=[
            {"east_m": 0.0, "north_m": 0.0, "active": False},
            {"east_m": 0.0, "north_m": 10.0, "active": True},
            (2.0, 10.0, True),
        ],
    )

    samples = simulator._cycle_samples()
    assert len(samples) >= 3
    assert samples[0].point.active is False
    assert samples[1].point.active is True
    assert any(sample.point.east_m == pytest.approx(2.0) for sample in samples)


def test_planter_simulator_loads_geojson_route(tmp_path):
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"active": True},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-47.0, -22.0],
                        [-46.999, -21.9995],
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {"active": False},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-46.9985, -21.9992],
                        [-46.998, -21.9990],
                    ],
                },
            },
        ],
    }
    route_file = tmp_path / "route.geojson"
    route_file.write_text(json.dumps(geojson))

    simulator = PlanterSimulator(
        field_length_m=20.0,
        headland_length_m=0.0,
        speed_mps=5.0,
        sample_rate_hz=5.0,
        passes_per_cycle=2,
        loop_forever=False,
        base_lat=-22.0,
        base_lon=-47.0,
        route_file=str(route_file),
    )

    samples = simulator._cycle_samples()
    assert len(samples) >= 4
    actives = [sample.point.active for sample in samples]
    assert actives[0] is True
    assert actives[-1] is False

def test_planter_simulator_limits_speed_on_sparse_routes():
    simulator = PlanterSimulator(
        field_length_m=20.0,
        headland_length_m=0.0,
        speed_mps=2.5,
        sample_rate_hz=5.0,
        passes_per_cycle=2,
        loop_forever=False,
        route_points=[
            {"east_m": 0.0, "north_m": 0.0, "active": True},
            {"east_m": 200.0, "north_m": 0.0, "active": True},
        ],
    )

    samples = simulator._cycle_samples()
    speeds = [sample.speed_mps for sample in samples]

    assert min(speeds) > 2.0
    assert max(speeds) < 3.0

def test_planter_simulator_limits_time_delta_on_sparse_routes():
    simulator = PlanterSimulator(
        field_length_m=20.0,
        headland_length_m=0.0,
        speed_mps=2.5,
        sample_rate_hz=2.0,
        passes_per_cycle=2,
        loop_forever=False,
        route_points=[
            {"east_m": 0.0, "north_m": 0.0, "active": True},
            {"east_m": 250.0, "north_m": 0.0, "active": True},
        ],
    )

    samples = simulator._cycle_samples()
    assert samples
    max_delta = max(sample.time_delta_s for sample in samples)

    assert max_delta <= 0.55




def test_planter_simulator_resolves_repo_route_paths():
    simulator = PlanterSimulator(
        field_length_m=20.0,
        headland_length_m=0.0,
        speed_mps=5.0,
        sample_rate_hz=5.0,
        passes_per_cycle=2,
        loop_forever=False,
        base_lat=-22.0,
        base_lon=-47.0,
        route_file="rota_plantio_terracos.geojson",
    )

    samples = simulator._cycle_samples()
    assert samples, "should load samples from packaged routes"


def test_planter_simulator_resolves_agent_root_routes(tmp_path, monkeypatch):
    from ma_agent import simulators as simulator_pkg

    route_dir = tmp_path / "config" / "routes"
    route_dir.mkdir(parents=True)
    geojson = {
        "type": "Feature",
        "properties": {"active": True},
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [-47.0, -22.0],
                [-46.9995, -21.9995],
            ],
        },
    }
    route_path = route_dir / "agent_root_route.geojson"
    route_path.write_text(json.dumps(geojson))

    monkeypatch.setattr(simulator_pkg.planter, "AGENT_ROOT", tmp_path)

    simulator = simulator_pkg.PlanterSimulator(
        field_length_m=20.0,
        headland_length_m=0.0,
        speed_mps=5.0,
        sample_rate_hz=5.0,
        passes_per_cycle=2,
        loop_forever=False,
        base_lat=-22.0,
        base_lon=-47.0,
        route_file="agent_root_route.geojson",
    )

    samples = simulator._cycle_samples()
    assert samples, "should load samples from AGENT_ROOT-configured routes"