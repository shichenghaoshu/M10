# Board Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn `m10-robot-core` into a board-tested RK3566 robot runtime with server command polling, ESP32 chassis control, camera viewing, Wi-Fi provisioning hooks, ToF safety hooks, and audio command hooks.

**Architecture:** Keep FastAPI as the local control plane and keep hardware logic in small services. Use test-first changes for command parsing, server polling, provisioning command generation, and stream behavior. Board verification runs over SSH to `root@192.0.2.10` after local tests pass.

**Tech Stack:** Python 3.8+, FastAPI, requests, pyserial, OpenCV when available, NetworkManager `nmcli`, ALSA tools, pytest, SSH/rsync deployment.

---

### Task 1: Server Command Polling and Dispatch

**Files:**
- Modify: `services/server_client.py`
- Modify: `services/command_dispatcher.py`
- Modify: `services/robot_core.py`
- Modify: `web/web_server.py`
- Test: `tests/test_server_client.py`
- Create: `tests/test_command_dispatcher.py`

**Step 1: Write failing tests**

Add tests that prove:
- `ServerClient.poll_commands()` normalizes a single command object and a list of command objects.
- disabled server polling returns no commands.
- `CommandDispatcher.dispatch_server_command()` accepts `forward`, `backward`, `left`, `right`, `stop`, `status`, `snapshot`, and rejects unknown commands.

**Step 2: Run tests to verify failure**

Run: `. .venv/bin/activate && python -m pytest tests/test_server_client.py tests/test_command_dispatcher.py -q`

Expected: new tests fail because normalization and dispatch method do not exist.

**Step 3: Implement minimal code**

Add server command normalization and a dispatcher method that maps command names to existing methods. Add a `RobotCore.poll_server_once()` helper that polls, dispatches, and ACKs commands.

**Step 4: Run tests**

Run: `. .venv/bin/activate && python -m pytest tests/test_server_client.py tests/test_command_dispatcher.py -q`

Expected: PASS.

**Step 5: Commit**

Run:

```bash
git add services/server_client.py services/command_dispatcher.py services/robot_core.py web/web_server.py tests/test_server_client.py tests/test_command_dispatcher.py
git commit -m "feat: dispatch server commands"
```

### Task 2: Camera Snapshot and MJPEG Stream Endpoint

**Files:**
- Modify: `services/video_service.py`
- Modify: `web/web_server.py`
- Test: `tests/test_video_service.py`

**Step 1: Write failing tests**

Add tests that prove:
- camera devices are filtered to real `/dev/videoN` nodes and skip encoder/decoder pseudo nodes.
- when OpenCV is missing, frame capture returns `opencv_not_installed`.
- MJPEG generator yields multipart frame bytes when `_read_frame_jpeg()` returns a frame.

**Step 2: Run tests to verify failure**

Run: `. .venv/bin/activate && python -m pytest tests/test_video_service.py -q`

Expected: FAIL because stream helpers do not exist.

**Step 3: Implement minimal code**

Add `_read_frame_jpeg()`, `mjpeg_frames()`, `stream_status()`, and `/api/video/stream.mjpg`. Keep snapshot truthful if no frames can be read.

**Step 4: Run tests**

Run: `. .venv/bin/activate && python -m pytest tests/test_video_service.py -q`

Expected: PASS.

**Step 5: Commit**

Run:

```bash
git add services/video_service.py web/web_server.py tests/test_video_service.py
git commit -m "feat: expose camera mjpeg stream"
```

### Task 3: Wi-Fi Provisioning Hooks

**Files:**
- Create: `services/wifi_provisioning_service.py`
- Modify: `services/robot_core.py`
- Modify: `web/web_server.py`
- Modify: `config.yaml`
- Test: `tests/test_wifi_provisioning_service.py`

**Step 1: Write failing tests**

Add tests for:
- AP creation command generation uses `nmcli device wifi hotspot`.
- credential connection command generation uses `nmcli device wifi connect`.
- disabled provisioning returns `wifi_provisioning_disabled`.

**Step 2: Run tests to verify failure**

Run: `. .venv/bin/activate && python -m pytest tests/test_wifi_provisioning_service.py -q`

Expected: FAIL because service does not exist.

**Step 3: Implement minimal code**

Add a small service wrapping `nmcli`, plus API endpoints:
- `GET /api/wifi/status`
- `POST /api/wifi/hotspot/start`
- `POST /api/wifi/connect`

**Step 4: Run tests**

Run: `. .venv/bin/activate && python -m pytest tests/test_wifi_provisioning_service.py -q`

Expected: PASS.

**Step 5: Commit**

Run:

```bash
git add services/wifi_provisioning_service.py services/robot_core.py web/web_server.py config.yaml tests/test_wifi_provisioning_service.py
git commit -m "feat: add wifi provisioning service"
```

### Task 4: ToF and Audio Control Hooks

**Files:**
- Modify: `services/sensor_manager.py`
- Modify: `services/audio_service.py`
- Modify: `services/command_dispatcher.py`
- Modify: `services/robot_core.py`
- Modify: `web/web_server.py`
- Modify: `config.yaml`
- Test: `tests/test_sensor_manager.py`
- Test: `tests/test_audio_service.py`

**Step 1: Write failing tests**

Add tests for:
- disabled ToF returns `sensor_not_configured`.
- available ToF distance below stop threshold blocks motion through the state machine.
- audio command capture returns explicit `speech_recognition_not_configured` when local recognizer is not configured.

**Step 2: Run tests to verify failure**

Run: `. .venv/bin/activate && python -m pytest tests/test_sensor_manager.py tests/test_audio_service.py tests/test_state_machine.py -q`

Expected: FAIL for new service behavior.

**Step 3: Implement minimal code**

Add configurable ToF reading hooks and audio command hooks without pretending recognition works before a recognizer is installed.

**Step 4: Run tests**

Run: `. .venv/bin/activate && python -m pytest tests/test_sensor_manager.py tests/test_audio_service.py tests/test_state_machine.py -q`

Expected: PASS.

**Step 5: Commit**

Run:

```bash
git add services/sensor_manager.py services/audio_service.py services/command_dispatcher.py services/robot_core.py web/web_server.py config.yaml tests/test_sensor_manager.py tests/test_audio_service.py tests/test_state_machine.py
git commit -m "feat: add tof and audio command hooks"
```

### Task 5: RK3566 Deployment and Smoke Test

**Files:**
- Create: `scripts/deploy_rk3566.sh`
- Modify: `docs/deployment.md`
- Modify: `docs/rk3566_test.md`
- Modify: `README.md`

**Step 1: Add deployment script**

Create a script that rsyncs the repository to `/opt/m10-robot-core`, installs apt dependencies `python3-venv python3-serial python3-opencv`, installs pip requirements, and runs `python3 main.py --check`.

**Step 2: Run local tests**

Run: `. .venv/bin/activate && python -m pytest tests -q`

Expected: PASS.

**Step 3: Run board deployment**

Run: `./scripts/deploy_rk3566.sh root@192.0.2.10`

Expected: sync succeeds, dependencies are installed, startup check exits `0`.

**Step 4: Run board smoke checks**

Run SSH commands that verify:
- `curl http://127.0.0.1:8000/api/status`
- `curl -X POST http://127.0.0.1:8000/api/control/status`
- `curl http://127.0.0.1:8000/api/video/stream/status`

Expected: service responds, ESP32 status is available, camera reports available or a concrete diagnostic reason.

**Step 5: Commit**

Run:

```bash
git add scripts/deploy_rk3566.sh docs/deployment.md docs/rk3566_test.md README.md
git commit -m "chore: add rk3566 deployment workflow"
```
