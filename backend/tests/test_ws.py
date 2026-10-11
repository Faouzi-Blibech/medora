import json

import pytest
from starlette.websockets import WebSocketDisconnect

from app.iot import publisher
from app.ws.hub import Client, hub, wants
from tests.helpers import login

NURSE_C = Client(ws=None, user_id="u-0002", role="nurse", ward="Cardiology")
NURSE_IM = Client(ws=None, user_id="u-0003", role="nurse", ward="Internal Medicine")
DOCTOR = Client(ws=None, user_id="u-0001", role="doctor", ward="Cardiology")
ADMIN = Client(ws=None, user_id="u-0004", role="admin", ward=None)
SCOPE = {"patient_id": "p-0001", "ward": "Cardiology", "doctor_id": "u-0001"}


def test_filtering():
    vital = {"type": "vital", "data": {}, "scope": SCOPE}
    assert wants(NURSE_C, vital) and wants(DOCTOR, vital)
    assert not wants(NURSE_IM, vital) and not wants(ADMIN, vital)
    status = {"type": "device_status", "data": {}, "scope": SCOPE}
    assert wants(ADMIN, status) and wants(NURSE_C, status)
    other_doc = {"type": "alert", "data": {}, "scope": dict(SCOPE, doctor_id="u-0099")}
    assert not wants(DOCTOR, other_doc)


def test_ws_rejects_bad_token(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/ws?token=junk") as ws:
            ws.receive_json()
    assert e.value.code == 4401


def test_ws_rejects_patient(client):
    token = login(client, "patient@medora.tn")["Authorization"].split()[1]
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"/ws?token={token}") as ws:
            ws.receive_json()
    assert e.value.code == 4403


def test_ws_receives_scoped_frame_without_scope(client):
    token = login(client, "nurse@medora.tn")["Authorization"].split()[1]
    with client.websocket_connect(f"/ws?token={token}") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
        hub.broadcast({"type": "vital", "data": {"patient_id": "p-0002"},
                       "scope": dict(SCOPE, patient_id="p-0002", ward="Internal Medicine")})
        hub.broadcast({"type": "vital", "data": {"patient_id": "p-0001"}, "scope": SCOPE})
        assert ws.receive_json() == {"type": "vital", "data": {"patient_id": "p-0001"}}


class FakeMqtt:
    def __init__(self):
        self.sent = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.sent.append((topic, json.loads(payload), qos, retain))


def test_publisher_topics(monkeypatch):
    fake = FakeMqtt()
    monkeypatch.setattr(publisher, "_client", fake)
    publisher.publish_schedule("bsu-001", {"schedule_version": 1})
    publisher.publish_command("bsu-001", {"type": "alert", "text": "hi"})
    publisher.publish_ws_frame({"type": "vital", "data": {}, "scope": SCOPE})
    assert fake.sent[0] == ("hospital/device/bsu-001/schedule", {"schedule_version": 1}, 1, True)
    assert fake.sent[1][0] == "hospital/device/bsu-001/command" and fake.sent[1][2:] == (1, False)
    assert fake.sent[2][0] == "ward/internal/ws" and fake.sent[2][2:] == (0, False)


def test_api_publishes_through_the_connected_relay_client(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.ws import relay

    class FakeRelay:
        def loop_stop(self):
            pass

        def disconnect(self):
            pass

    fake = FakeRelay()
    monkeypatch.setattr(relay, "start", lambda: fake)
    with TestClient(app):
        assert publisher._client is fake  # not a lazily-connecting client that drops the first QoS 0 frame
