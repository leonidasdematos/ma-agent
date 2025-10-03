import base64

import pytest

from ma_agent.session import GatewaySession
from ma_agent.protocol.messages import Message, MessageType


class FakeTelemetryPublisher:
    def __init__(self):
        self.registered = []
        self.unregistered = []

    def register_session(self, session):
        self.registered.append(session)

    def unregister_session(self, session):
        self.unregistered.append(session)


class FakeGnssCoordinator:
    def __init__(self):
        self.corrections = []
        self.acks = []
        self.registered = []
        self.unregistered = []

    def register_session(self, session):
        self.registered.append(session)

    def unregister_session(self, session):
        self.unregistered.append(session)

    def handle_correction(self, *, sequence, payload, format, timestamp=None):
        self.corrections.append((sequence, payload, format, timestamp))

    def acknowledge_fix(self, *, sequence, status, timestamp=None):
        self.acks.append((sequence, status, timestamp))


@pytest.fixture
def hello_message():
    return Message(type=MessageType.HELLO, payload={})


def test_hello_registers_session_and_advertises_capabilities(hello_message):
    publisher = FakeTelemetryPublisher()
    coordinator = FakeGnssCoordinator()
    session = GatewaySession(
        telemetry_publisher=publisher,
        gnss_coordinator=coordinator,
    )

    [ack] = session.handle_message(hello_message)

    assert ack.type is MessageType.HELLO_ACK
    assert "telemetry/rtk" in ack.payload["capabilities"]
    assert "corrections/ntrip" in ack.payload["capabilities"]
    assert session.handshake_complete
    assert publisher.registered == [session]
    assert coordinator.registered == [session]
    assert session.telemetry_subscribed is True


def test_close_unregisters_dependencies(hello_message):
    publisher = FakeTelemetryPublisher()
    coordinator = FakeGnssCoordinator()
    session = GatewaySession(
        telemetry_publisher=publisher,
        gnss_coordinator=coordinator,
    )
    session.handle_message(hello_message)

    session.close()

    assert publisher.unregistered == [session]
    assert coordinator.unregistered == [session]


def test_gnss_ack_updates_state(hello_message):
    clock_values = [100.0, 200.0]

    def fake_clock():
        return clock_values.pop(0)

    session = GatewaySession(clock=fake_clock)
    session.handle_message(hello_message)

    ack_message = Message(
        type=MessageType.GNSS_ACK,
        payload={"sequence": 5, "status": "ok", "timestamp": 123.4},
    )

    responses = session.handle_message(ack_message)

    assert responses == []
    assert session.last_ack_sequence == 5
    assert session.last_ack_status == "ok"
    assert session.last_ack_timestamp == 123.4
    assert session.last_heartbeat_at == 100.0
    assert session.awaiting_ack is False


def test_mark_fix_sent_and_ack_clears_pending(hello_message):
    clock_values = [10.0, 20.0]

    def fake_clock():
        return clock_values.pop(0)

    session = GatewaySession(clock=fake_clock)
    session.handle_message(hello_message)

    session.mark_fix_sent(42)
    assert session.awaiting_ack is True
    assert session.last_heartbeat_at == 10.0

    ack_message = Message(
        type=MessageType.GNSS_ACK,
        payload={"sequence": 42, "status": "ok"},
    )
    session.handle_message(ack_message)

    assert session.awaiting_ack is False
    assert session.last_heartbeat_at == 20.0


def test_ntrip_correction_forwards_bytes_and_replies_ack(hello_message):
    coordinator = FakeGnssCoordinator()
    session = GatewaySession(gnss_coordinator=coordinator)
    session.handle_message(hello_message)

    payload_bytes = b"rtcm-data"
    encoded = base64.b64encode(payload_bytes).decode()
    message = Message(
        type=MessageType.NTRIP_CORRECTION,
        payload={
            "sequence": 7,
            "format": "RTCM3",
            "payload": encoded,
            "timestamp": 12.5,
        },
    )

    [ack] = session.handle_message(message)

    assert ack.type is MessageType.NTRIP_CORRECTION_ACK
    assert ack.payload["sequence"] == 7
    assert ack.payload["status"] == "accepted"
    assert coordinator.corrections == [(7, payload_bytes, "RTCM3", 12.5)]
    assert coordinator.acks == []


def test_ntrip_correction_invalid_payload_returns_error(hello_message):
    session = GatewaySession()
    session.handle_message(hello_message)

    message = Message(
        type=MessageType.NTRIP_CORRECTION,
        payload={"sequence": 1, "format": "RTCM3", "payload": "***"},
    )

    [error] = session.handle_message(message)

    assert error.type is MessageType.ERROR
    assert error.payload["code"] == "invalid_payload"



def test_send_message_requires_handshake():
    session = GatewaySession()
    captured: list[Message] = []

    session.attach_sender(captured.append)

    message = Message(type=MessageType.GNSS_FIX, payload={"sequence": 1})

    assert session.send_message(message) is False
    assert captured == []


def test_send_message_marks_fix_when_ready(hello_message):
    clock_values = [111.0]

    def fake_clock():
        return clock_values[0]

    session = GatewaySession(clock=fake_clock)
    captured: list[Message] = []
    session.attach_sender(captured.append)

    session.handle_message(hello_message)

    payload = {
        "latitude": -22.0,
        "longitude": -47.0,
        "altitude": 550.0,
        "sequence": 5,
    }
    message = Message(type=MessageType.GNSS_FIX, payload=payload)

    assert session.send_message(message) is True
    assert captured == [message]
    assert session.awaiting_ack is True