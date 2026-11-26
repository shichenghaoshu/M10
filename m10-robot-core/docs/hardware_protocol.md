# Hardware Protocol

## ESP32 Serial Commands

The RK3566 side sends plain UTF-8 text lines terminated by `\n`.

Supported commands:

- `forward`
- `backward`
- `left`
- `right`
- `stop`
- `status`
- `heartbeat`

Expected device behavior:

- A real ESP32 should acknowledge each command
- If the serial device is absent, `esp32_bridge.py` must return `serial_device_not_found`
- If serial write fails during motion, the dispatcher attempts `stop`

## Video

- Snapshot source must be a real `/dev/video*`
- Stored under `data/snapshots/`
- No bundled images or placeholders are used as camera results

## Display

- Real display backends: `x11`, `wayland`, or `fbdev`
- If no display backend exists, preview output is written to `data/display_preview.png`
- Preview generation does not claim hardware display success

## Audio

- Input detection uses `arecord -l`
- Output detection uses `aplay -l`
- Recording and playback only run when real devices exist
