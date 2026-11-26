# Architecture

`M10 Robot Core v0.1` is a single-process Python service with three layers:

1. Hardware-facing services
2. Runtime orchestration
3. Web and API surface

## Hardware-facing services

- `hardware_discovery.py`: truthful hardware detection
- `esp32_bridge.py`: real serial bridge, no mock transport
- `video_service.py`: real `/dev/video*` snapshot path
- `display_service.py`: real display environment detection, X11 test windows, and direct `fbdev` framebuffer output
- `audio_service.py`: real `arecord` / `aplay` checks
- `battery_manager.py`: reads actual battery telemetry when present, otherwise `unknown`
- `sensor_manager.py`: reports unconfigured sensors as `unknown`

## Runtime orchestration

- `robot_core.py`: startup coordination and status aggregation
- `state_machine.py`: control safety and fault transitions
- `command_dispatcher.py`: web/API command routing with motion safeguards
- `health_monitor.py`: aggregate health view
- `logger.py`: file, stdout, and recent-log buffer

## API and UI

- `web/web_server.py`: FastAPI app
- `web/templates/index.html`: operator console
- `web/static/app.js`: polling and button actions

## No-fake design

The core design rule is to report what the host actually has. VMware is expected to miss most hardware. That is a valid test result and must appear as `unavailable`, `preview_only`, `unknown`, or `offline` instead of fake success.
