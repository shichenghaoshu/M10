import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from m10_runtime.app import create_app
from m10_runtime.settings import load_settings

TOKEN = "runtime-test-token"
HEADERS = {"Authorization": "Bearer " + TOKEN}


@pytest.fixture
def client(tmp_path):
    app = create_app(load_settings("demo"), TOKEN, tmp_path)
    with TestClient(app) as c:
        yield c


def test_health_is_truthful_and_control_requires_header(client):
    assert client.get("/health").json()["simulated"] is True
    assert client.post("/control", json={"action": "forward"}).status_code == 401
    assert client.post("/api/runtime/pair", headers=HEADERS).status_code == 200
    # A media cookie must not grant control authority to a cross-site POST.
    assert client.post("/control", json={"action": "forward"}).status_code == 401


def test_ws_authentication_and_owner_disconnect_stop(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/control/ws", subprotocols=["m10", "m10.token.invalid"]):
            pass
    with client.websocket_connect("/control/ws", subprotocols=["m10", "m10.token." + TOKEN]) as ws:
        ws.send_json({"action": "forward"})
        assert ws.receive_json()["control"]["action"] == "forward"
        ws.send_json({"action": {}})
        assert ws.receive_json()["status"] == "error"
    assert client.get("/api/runtime/status", headers=HEADERS).json()["control"]["action"] == "stop"


def test_status_heartbeats_cannot_renew_old_motion(client):
    result = client.post("/control", headers=HEADERS, json={"action": "forward", "client_id": "test"})
    assert result.status_code == 200
    for _ in range(5):
        client.post("/status_and_heartbeat", headers=HEADERS, json={"client_id": "observer"})
        time.sleep(0.08)
    state = client.get("/api/runtime/status", headers=HEADERS).json()
    assert state["control"]["action"] == "stop"
    assert state["sensors"]["bus_voltage"] is None


def test_face_auth_and_existing_video_routes(client):
    assert client.get("/face").status_code == 200
    assert client.get("/media/1.mp4", headers={"Range": "bytes=0-31"}).status_code == 206
    assert client.post("/api/v1/state", json={"state": "happy"}).status_code == 401
    assert client.post("/api/v1/state", headers=HEADERS, json={"state": "happy"}).status_code == 200


def test_legacy_uses_same_origin_and_fresh_control_adapter(client):
    page = client.get("/dreamupers").text
    assert "10.0.0.229" not in page
    assert "m10Hold(action)" in page and "m10Release(true)" in page
    assert "m10.token." in page and "hls.js@1.6.13" in page
    assert client.post("/set_bitrate", headers=HEADERS, json={"mbps": 2}).status_code == 200


def test_disabled_stream_and_dangerous_host_actions_fail_explicitly(client):
    assert client.post("/start_stream", headers=HEADERS).status_code == 409
    assert client.get("/stream/index.m3u8").status_code == 401
    assert client.post("/sleep", headers=HEADERS).status_code == 501
    assert client.post("/set_laser", headers=HEADERS).status_code == 501


def test_http_motion_requires_distinct_identity_and_valid_action(client):
    assert client.post("/control", headers=HEADERS, json={"action": "forward"}).status_code == 422
    assert client.post("/control", headers=HEADERS, json={"action": "fly", "client_id": "test"}).status_code == 422
    assert client.post("/set_speed", headers=HEADERS, json={"speed": True}).status_code == 422
