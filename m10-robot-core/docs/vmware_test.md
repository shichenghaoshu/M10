# VMware Test

VMware is a negative-hardware environment for this project.

## Goals

1. Dependencies install
2. `python3 main.py --check` exits with code `0`
3. Hardware discovery runs without crashing
4. Missing hardware is marked truthfully
5. Web console can start when requested

## Run

```bash
chmod +x scripts/*.sh
./scripts/vmware_check.sh
```

## Expected Results

- Serial: usually `unavailable`
- Camera: usually `unavailable`
- Audio: may be `available` or `unavailable` depending on VMware passthrough
- Display: often `available` inside desktop VMware, otherwise `unavailable`
- Battery: `unknown`
- Server: `disabled` or `offline`
