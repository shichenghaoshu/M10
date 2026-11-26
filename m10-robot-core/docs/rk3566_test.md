# RK3566 Test

## Basic Bring-up

```bash
chmod +x scripts/*.sh
./scripts/rk3566_check.sh
```

## Full Runtime

```bash
python3 main.py
```

## What To Verify

1. ESP32 serial appears on one of the configured candidate paths
2. `/dev/video*` exists for the OV5647 path in the active image
3. Audio devices appear in `arecord -l` and `aplay -l`
4. A display backend is detected if the screen stack is active
5. `POST /api/video/snapshot` produces a real image
6. Motion commands fail honestly if the ESP32 bridge is unavailable
