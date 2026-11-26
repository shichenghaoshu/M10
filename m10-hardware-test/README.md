# M10 硬件测试工程

> 正式候选使用 `esp32/m10_motor_controller/` 和 M10 V2。下文旧文本协议、1 秒超时及旧 GPIO 表仅为接线草图说明；当前引脚与 300 ms 看门狗以 `docs/M10_MOTOR_FIRMWARE.md` 为准。


这个目录用于验证 M10 原型机的底层硬件，当前重点是让 **ESP32-S3 控制 WHEELTEC R3X 四轮两驱差速底盘**，并让 Linux 上位机通过串口发送运动指令。

电机控制采用开环 PWM，霍尔编码器线先预留，后续再做速度闭环 PID。Android 与 ESP32 的正式链路使用 M10 Protocol V2，ESP32 内置 300 ms 通信看门狗和急停锁存。

## 当前硬件

- Linux 上位机：RK3566 开发板，Ubuntu 系统
- 下位机：ESP32-S3 DevKitC-1 N16R8
- 底盘：WHEELTEC R3X 四轮两驱差速底盘，左右两路驱动电机
- 电机驱动：TB6612FNG 或兼容双路 H 桥驱动板
- 供电：电池、降压模块、主开关、保险丝
- 其他外设：屏幕、摄像头、麦克风、扬声器等

## 目录说明

| 路径 | 用途 |
| --- | --- |
| `esp32/m10_motor_controller/` | M10 V2 ESP32-S3 正式候选电机固件 |
| `esp32/motor_serial_test/` | 旧文本命令接线测试草案 |
| `rk3566/serial_control_test.py` | Linux 上位机串口手动控制脚本 |
| `docs/M10_MOTOR_FIRMWARE.md` | 新固件、镜像和覆盖小智流程 |
| `docs/r3x_esp32_usage.md` | R3X + ESP32 详细使用手册 |
| `docs/arduino_quick_run.md` | Arduino CLI 快速烧录和跑通流程 |
| `docs/wiring.md` | 接线说明 |
| `docs/test_plan.md` | 首次上电和硬件测试流程 |
| `docs/power.md` | 电源架构建议 |
| `tests/` | 本地可运行的固件映射和脚本测试 |

## 控制方式

Linux 上位机通过 USB 连接 ESP32。ESP32 在 Linux 中通常显示为 `/dev/ttyACM0` 或 `/dev/ttyUSB0`。

串口参数：

- 波特率：`115200`
- 数据格式：8N1
- 协议：UTF-8 文本，一行一个命令，以换行结束

支持命令：

| 命令 | 动作 |
| --- | --- |
| `forward` | 前进 |
| `backward` | 后退 |
| `left` | 原地左转，左电机反转、右电机正转 |
| `right` | 原地右转，左电机正转、右电机反转 |
| `stop` | 停车 |
| `status` | 查询 ESP32 当前状态 |
| `heartbeat` | 心跳测试 |

ESP32 固件内置 1 秒运动命令超时保护。如果发出 `forward` 后上位机不再继续发送运动命令，ESP32 会自动停车。

## 默认接线

默认使用一块 TB6612FNG 双路驱动板：

| 功能 | ESP32-S3 GPIO |
| --- | ---: |
| TB6612 STBY | 12 |
| 左电机 PWMA/AIN1/AIN2 | 4 / 5 / 6 |
| 右电机 PWMB/BIN1/BIN2 | 7 / 15 / 16 |

完整接线表见 [docs/wiring.md](docs/wiring.md)。

## 快速跑通

当前固件是 Arduino-ESP32 格式的 `.ino` 文件。这里使用 Arduino 只是为了先快速验证底盘，不代表后续必须绑定 Arduino；如果后面要做编码器 PID、FreeRTOS 任务和更复杂协议，可以迁移到 ESP-IDF。

我已经在本机安装并验证了 Arduino CLI：

- `arduino-cli`：`1.4.1`
- ESP32 Arduino core：`esp32:esp32@2.0.17`
- 本项目固件编译目标：`esp32:esp32:esp32s3`

本机快速编译：

```bash
cd $M10_ROOT/m10-hardware-test
arduino-cli compile --fqbn esp32:esp32:esp32s3 esp32/motor_serial_test
```

插上 ESP32-S3 后查看串口：

```bash
arduino-cli board list
```

macOS 常见串口是 `/dev/cu.usbmodemXXXX` 或 `/dev/cu.usbserialXXXX`；Linux 常见串口是 `/dev/ttyACM0` 或 `/dev/ttyUSB0`。

上传固件时把 `<PORT>` 换成实际串口：

```bash
arduino-cli upload -p <PORT> --fqbn esp32:esp32:esp32s3 esp32/motor_serial_test
```

例如 macOS：

```bash
arduino-cli upload -p /dev/cu.usbmodem1101 --fqbn esp32:esp32:esp32s3 esp32/motor_serial_test
```

如果要用 Arduino IDE，也可以按下面流程：

1. 安装 ESP32 开发板支持包。
2. 打开 `esp32/motor_serial_test/motor_serial_test.ino`。
3. 开发板选择 `ESP32S3 Dev Module`，或选择与你的 ESP32-S3 开发板完全匹配的型号。
4. 选择正确串口。
5. 编译并上传。
6. 打开串口监视器，波特率设为 `115200`，发送 `status` 查看响应。

更详细的 Arduino 安装、烧录、串口监视器和 Linux 上位机控制流程见 [docs/arduino_quick_run.md](docs/arduino_quick_run.md)。

## Linux 上位机手动控制

在 RK3566 或其他 Linux 主机上安装依赖：

```bash
cd $M10_ROOT/m10-hardware-test/rk3566
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

连接 ESP32 后，查看串口：

```bash
ls /dev/ttyACM* /dev/ttyUSB*
```

启动手动控制：

```bash
python3 serial_control_test.py --device /dev/ttyACM0
```

进入提示符后依次测试：

```text
status
forward
stop
backward
stop
left
stop
right
stop
heartbeat
```

第一次测试时务必把底盘架空，确认电机方向正确后再落地。

## 首次上电顺序

1. 不接电机，只连接 ESP32 USB，烧录固件。
2. 打开串口监视器或运行 `serial_control_test.py`，确认 `status` 有响应。
3. 断电后连接 TB6612 逻辑线，仍然先不要让车落地。
4. 接上电机和电机电源，底盘架空。
5. 发送 `forward`，观察左右驱动轮是否都向前。
6. 如果方向反了，先发送 `stop`，断开电机电源，再调整电机输出线或固件中的 `inverted` 标志。
7. 依次测试后退、左转、右转、自动超时停车。
8. 确认无异常发热、无重启、无异响后，再低速落地测试。

## 本地验证

电脑上可以先跑软件测试，不需要连接 ESP32：

```bash
cd $M10_ROOT/m10-hardware-test
g++ -std=c++17 -Wall -Wextra -pedantic tests/test_motor_control_core.cpp -o /tmp/test_motor_control_core
/tmp/test_motor_control_core
python3 -m pytest tests -q
```

## 安全提醒

- 不要用 ESP32 或 RK3566 的 5V/3.3V 给电机供电。
- 电机必须通过 TB6612 或其他电机驱动板供电。
- ESP32、TB6612、Linux 上位机、电机电源必须共地。
- 电机供电建议加保险丝和主开关。
- 首次测试一定架空底盘，手边保留断电开关。
- 电机启动电流可能让电源掉压，Linux 上位机应使用独立稳定 5V 电源。
