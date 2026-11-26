from __future__ import annotations

from typing import Any

import requests


class ServerClient:
    def __init__(self, config: dict, device_config: dict, logger, session: requests.Session | None = None) -> None:
        self.config = config
        self.device_config = device_config
        self.logger = logger
        self.session = session or requests.Session()

    def get_status(self) -> dict:
        if not self.config.get("enabled", False):
            return {"status": "disabled"}
        return {"status": "configured", "base_url": self.config.get("base_url")}

    def _request(self, method: str, endpoint_key: str, payload: dict[str, Any] | None = None) -> dict:
        if not self.config.get("enabled", False):
            return {"status": "disabled"}

        base_url = self.config.get("base_url", "").rstrip("/")
        endpoint = self.config.get(endpoint_key, "")
        url = f"{base_url}{endpoint}"
        headers = {}
        token = self.config.get("token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            response = self.session.request(method=method, url=url, json=payload, timeout=5, headers=headers)
            response.raise_for_status()
            return {"status": "online", "code": response.status_code, "data": response.json() if response.content else {}}
        except requests.RequestException as exc:
            self.logger.warning("Server request failed for %s: %s", url, exc)
            return {"status": "offline", "reason": "server_offline", "details": str(exc)}

    def register_device(self) -> dict:
        return self._request("POST", "device_register_endpoint", payload={"device": self.device_config})

    def send_heartbeat(self) -> dict:
        return self._request("POST", "heartbeat_endpoint", payload={"device_id": self.device_config.get("id")})

    def upload_status(self, status: dict) -> dict:
        return self._request("POST", "status_endpoint", payload=status)

    def upload_log(self, level: str, message: str) -> dict:
        return self._request("POST", "log_endpoint", payload={"level": level, "message": message})

    def poll_commands(self) -> dict:
        return self._request("GET", "command_poll_endpoint")

    def ack_command(self, command_id: str, status: str, result: dict) -> dict:
        payload = {"command_id": command_id, "status": status, "result": result}
        return self._request("POST", "command_ack_endpoint", payload=payload)
