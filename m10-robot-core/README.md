# M10 Robot Core

## Overview

M10 Robot Core is the RK3566 Linux-side runtime for the M10 family pet companion robot. This repository focuses on hardware-aware startup, health detection, a web console, and an API surface that reports real device state.

Current scope:

- RK3566 Ubuntu process runtime
- Real serial detection for ESP32
- Real camera detection and snapshots
- Real audio device detection
- Real display environment detection and framebuffer output
- REST API and web console
- Optional server client scaffolding

Out of scope in this phase:

- App
- Mini program
- Skill marketplace
- Cloud backend
- SLAM
- Auto docking
- AI recognition
- Full voice assistant

## No Mock Principle

This project does not use mock hardware data. If a device is missing or inaccessible, the service returns a real state such as:

```json
{
  "status": "unavailable",
  "reason": "device_not_found"
}
```

or:

```json
{
  "status": "error",
  "reason": "permission_denied"
}
```

The web console and API must never claim hardware success when the hardware is not present.

## Project Structure

```text
m10-robot-core/
  ├── main.py
  ├── config.yaml
  ├── services/
  ├── web/
  ├── scripts/
  ├── docs/
  ├── tests/
  ├── logs/
  └── data/
```

## Install

```bash
cd m10-robot-core
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If `opencv-python` fails to install in VMware or on RK3566:

- Try `pip install opencv-python-headless`
- Or install system packages first, then re-run `pip install -r requirements.txt`
- The program still starts without OpenCV, but camera snapshot calls will return an error instead of crashing

## VMware Testing

VMware validation is for startup and truthful absence reporting, not fake hardware success.

```bash
cd m10-robot-core
chmod +x scripts/*.sh
./scripts/vmware_check.sh
```

Expected behavior in VMware:

- Dependencies install
- Tests run
- `python3 main.py --check` exits with code `0`
- Missing serial, camera, audio, and display hardware show `unavailable`, `preview_only`, or explicit errors
- If VMware exposes a virtual `/dev/fb0`, display actions write to the framebuffer instead of pretending there is no screen

## RK3566 Testing

```bash
cd m10-robot-core
chmod +x scripts/*.sh
./scripts/rk3566_check.sh
```

Then start the full service:

```bash
python3 main.py
```

## Web Console

Run:

```bash
python3 main.py
```

Open:

```text
http://<device-ip>:8000
```

The page shows:

- Robot core state
- Real hardware discovery results
- ESP32 status
- Camera status
- Display status
- Audio status
- Server status
- Recent logs

## Display Testing

Use:

- `POST /api/display/face/idle`
- `POST /api/display/face/happy`
- `POST /api/display/face/error`

Display behavior is backend-specific:

- `x11`: opens a real test window
- `fbdev`: writes pixels directly to `/dev/fb*`
- `wayland`: currently falls back to `preview_only`
- no display backend: returns `display_environment_not_found`

## ESP32 Connection

Default serial candidates come from `config.yaml`:

- `/dev/ttyUSB0`
- `/dev/ttyACM0`
- `/dev/ttyS0`
- `/dev/ttyS1`
- `/dev/ttyS2`
- `/dev/ttyS3`

The bridge only connects to a real device path that exists. If no serial port exists, it returns:

```json
{
  "connected": false,
  "status": "unavailable",
  "reason": "serial_device_not_found"
}
```

## Camera Testing

Use the API or web button:

- `POST /api/video/snapshot`

If `/dev/video*` is missing, the result is `camera_device_not_found`.

## Audio Testing

Use:

- `POST /api/audio/test`

This checks:

- `arecord -l`
- `aplay -l`

If no devices exist, the result remains truthful and unavailable.

## Common Errors

- `serial_device_not_found`: no candidate serial device exists
- `camera_device_not_found`: no `/dev/video*` exists
- `opencv_not_installed`: OpenCV import failed
- `display_environment_not_found`: no `DISPLAY`, `WAYLAND_DISPLAY`, or `/dev/fb*`
- `framebuffer_device_not_found`: display backend was `fbdev` but no framebuffer node was accessible
- `framebuffer_unsupported_pixel_format`: framebuffer pixel layout is not supported by the current renderer
- `framebuffer_write_failed`: framebuffer open, ioctl, or write failed
- `arecord_no_device`: no capture device was reported
- `aplay_no_device`: no playback device was reported
- `server_offline`: configured server is unreachable

## Useful Commands

Startup check without long-running web service:

```bash
python3 main.py --check
```

Start service:

```bash
python3 main.py
```

Run tests:

```bash
pytest
```
