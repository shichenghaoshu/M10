# Deployment

## Local Run

```bash
python3 main.py
```

## Background Run

```bash
./scripts/start.sh
./scripts/stop.sh
```

## Systemd

Generate a unit file:

```bash
./scripts/create_service.sh
```

Review the generated `m10-robot-core.service`, then copy it into the target systemd directory if needed.

## Network Access

The web console binds to `0.0.0.0:8000` by default. Restrict that in `config.yaml` if the environment requires tighter exposure.
