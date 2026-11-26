from __future__ import annotations

import requests

from services.server_client import ServerClient


class FailingSession:
    def request(self, **kwargs):
        raise requests.ConnectionError("connection refused")


def test_server_client_returns_disabled_when_server_is_off():
    client = ServerClient(
        config={"enabled": False},
        device_config={"id": "m10-dev-001"},
        logger=type("L", (), {"warning": lambda *args, **kwargs: None})(),
    )
    assert client.send_heartbeat()["status"] == "disabled"


def test_server_client_returns_offline_when_unreachable():
    client = ServerClient(
        config={
            "enabled": True,
            "base_url": "http://127.0.0.1:9999",
            "heartbeat_endpoint": "/api/devices/heartbeat",
        },
        device_config={"id": "m10-dev-001"},
        logger=type("L", (), {"warning": lambda *args, **kwargs: None})(),
        session=FailingSession(),
    )
    result = client.send_heartbeat()
    assert result["status"] == "offline"
    assert result["reason"] == "server_offline"
