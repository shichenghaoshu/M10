# Power Architecture

Recommended power structure:

```text
2S 7.4V 18650 battery pack
  ->
BMS
  ->
Main switch
  ->
Fuse
  ->
Power distribution

Branch 1: 5V 5A DC-DC -> RK3566 + screen + camera
Branch 2: 5V 2A DC-DC -> ESP32 + sensors
Branch 3: battery voltage or 6V buck -> motor driver board
```

## Key Rules

- Motor startup current can cause voltage droop, so the motor rail should not directly share an unstable supply with RK3566.
- All grounds must be tied together.
- Add INA226 or INA219 current and voltage monitoring if possible.
- Add a 3A to 5A fuse near the battery output.
- Validate thermal behavior of the DC-DC modules under load before closing the chassis.
