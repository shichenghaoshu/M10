# Server API

The server client is optional and non-blocking.

## Config

`config.yaml`

```yaml
server:
  enabled: false
  base_url: "http://127.0.0.1:9000"
```

## Behavior

- `enabled: false`: returns `{"status": "disabled"}`
- `enabled: true` and server unreachable: returns `{"status": "offline", "reason": "server_offline"}`
- The main program never exits just because the server is offline

## Client Functions

- `register_device()`
- `send_heartbeat()`
- `upload_status(status: dict)`
- `upload_log(level: str, message: str)`
- `poll_commands()`
- `ack_command(command_id: str, status: str, result: dict)`

## Local API Endpoints

- `GET /api/status`
- `GET /api/hardware`
- `GET /api/esp32/status`
- `POST /api/control/forward`
- `POST /api/control/backward`
- `POST /api/control/left`
- `POST /api/control/right`
- `POST /api/control/stop`
- `POST /api/video/snapshot`
- `POST /api/display/face/{face_name}`
- `POST /api/audio/test`
- `POST /api/server/heartbeat`
