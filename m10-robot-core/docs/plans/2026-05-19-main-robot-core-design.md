# Main Robot Core Design

## Goal

Build `m10-robot-core` into the RK3566 Linux-side main repository for the robot. The service owns hardware discovery, ESP32 chassis control, Wi-Fi provisioning, ToF obstacle safety, camera viewing, voice input/output, and server communication.

## Current Hardware Findings

- Board SSH: `root@192.0.2.10` using `YOUR_DEVICE_SSH_KEY`.
- OS: Ubuntu 20.04.6 on aarch64, Python 3.8.10.
- ESP32 is present on `/dev/ttyACM0` and responds to `status`.
- Camera nodes exist under `/dev/video0` through `/dev/video8`; the active driver is Rockchip ISP, not a simple USB camera.
- A direct `v4l2-ctl` frame capture from `/dev/video0` currently fails with `VIDIOC_STREAMON returned -1 (No such device)`, so camera code must expose real diagnostics and avoid fake success.
- Audio capture/playback devices are visible through ALSA.
- Wi-Fi is managed by NetworkManager, supports AP mode, and has `nmcli`, `dnsmasq`, `iw`, and `wpa_cli`; `hostapd` is not currently installed.
- `python3-serial` and `python3-opencv` are not installed, but are available from apt.

## Architecture

The project stays a single Python service with FastAPI. Hardware-facing services stay separate from the API layer so device failures can be represented truthfully and tested locally. The robot process remains useful without all peripherals attached: missing devices return explicit `unavailable` or `error` states.

The device initiates communication with the remote server. First implementation uses polling and ACK endpoints for commands because it is easier to test behind NAT. The server can request chassis movement, status upload, camera status, and eventually voice/AI actions. A later WebSocket transport can reuse the same command dispatcher.

Camera viewing is local-first in this phase. The RK3566 service exposes a local MJPEG stream endpoint and reports that URL to the server. If the server and viewer are not on the same network, a later phase can add device-originated WebSocket or WebRTC streaming.

Wi-Fi provisioning uses NetworkManager where possible. On first boot or when Wi-Fi credentials are missing, the board can create an AP and expose a small configuration endpoint. After receiving SSID/password, it stores credentials, joins the target network, and then starts normal server connectivity.

## Components

- `services/esp32_bridge.py`: serial communication with ESP32 chassis firmware.
- `services/command_dispatcher.py`: validates and executes movement commands, always respecting state-machine safety.
- `services/server_client.py`: server registration, heartbeat, status upload, command polling, and command ACK.
- `services/video_service.py`: camera device discovery, snapshot, diagnostics, and MJPEG frame generation.
- `services/wifi_provisioning_service.py`: AP startup, credential intake, and NetworkManager station connection.
- `services/sensor_manager.py`: ToF distance reading and obstacle status for the state machine.
- `services/audio_service.py`: ALSA checks, recording/playback, wake-word pipeline placeholder, local speech-to-text hook, and upload path.
- `web/web_server.py`: local API, provisioning endpoints, control endpoints, and video stream route.
- `scripts/deploy_rk3566.sh`: sync repository to the board, install dependencies, and run checks.

## Data Flow

Startup loads config, discovers hardware, connects ESP32, checks sensors, and starts the API. If provisioning is enabled and Wi-Fi credentials are missing, NetworkManager creates a robot AP and the API accepts Wi-Fi credentials from the user.

For server control, the robot periodically polls the command endpoint. Each command is validated, dispatched through `CommandDispatcher`, and acknowledged with the result. Motion commands are blocked when ESP32 is disconnected, the state machine has a fault, battery is critical, or ToF reports an obstacle closer than the configured stop distance.

For video, the server can request the advertised local stream URL. The stream endpoint emits multipart MJPEG from real camera frames. If frames cannot be captured, the API returns a diagnostic status instead of placeholder media.

For voice, the microphone path waits for a wake-word event, records the utterance, runs local speech-to-text when configured, uploads recognized text to the server AI endpoint, and plays server-provided audio or local TTS through ALSA.

## Error Handling

Every hardware service returns structured dictionaries with `status`, `reason`, and optional details. Expected absence is `unavailable`; permission or runtime failures are `error`. The API should surface these states without pretending hardware is available.

Movement failures attempt an immediate stop command. If both movement and stop fail, the dispatcher logs a critical error and keeps the state machine in a safe state.

## Testing

Local tests run with pytest and do not require hardware. They cover command parsing, server polling/ACK logic, provisioning command generation, camera fallback diagnostics, and state-machine safety.

Board tests run over SSH on `root@192.0.2.10`. They install apt dependencies, start the service, verify `/api/status`, verify `/dev/ttyACM0` ESP32 status, check camera diagnostics, and exercise only safe `status`/`stop` commands by default.

## Open Hardware Items

- Confirm the exact ToF sensor model and bus/address before enabling real distance reads. Until then, ToF service should support a disabled/unconfigured state.
- Confirm whether the camera ISP media pipeline needs extra setup commands or a vendor camera stack. The first implementation should expose diagnostics to make that failure visible.
- Confirm server base URL, auth token, and AI endpoints before enabling production server communication.
