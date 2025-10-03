from __future__ import annotations

import time

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

    assert len(active_msg.payload["implement"]["sections"]) == implement.row_count
    assert all(active_msg.payload["implement"]["sections"])
    assert not any(inactive_msg.payload["implement"]["sections"])