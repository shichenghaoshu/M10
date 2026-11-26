# 硬件测试计划

这个测试计划用于逐步验证 RK3566/Linux 上位机、ESP32-S3、TB6612 电机驱动和 R3X 四轮两驱差速底盘。不要跳过架空测试，底盘第一次动起来时最容易因为方向反、线接错或电源不稳出现危险。

## 1. 总体测试顺序

1. RK3566 能正常启动 Ubuntu。
2. Linux 能识别 ESP32 串口。
3. ESP32 固件能响应 `status`。
4. ESP32 能控制 TB6612 左右两路输出。
5. 底盘架空时能完成前进、后退、左转、右转、停车。
6. 不继续发送运动命令时，ESP32 能在超时后自动停车。
7. 落地低速测试，确认方向和电源稳定。
8. 再测试摄像头、屏幕、麦克风、扬声器等其他外设。
9. 最后做电源稳定性测试，确认电机启动不会导致 Linux 上位机或 ESP32 重启。

## 2. 软件测试

在不接硬件的情况下，先验证命令映射和 Python 控制脚本：

```bash
cd $M10_ROOT/m10-hardware-test
g++ -std=c++17 -Wall -Wextra -pedantic tests/test_motor_control_core.cpp -o /tmp/test_motor_control_core
/tmp/test_motor_control_core
python3 -m pytest tests -q
```

通过后再烧录 ESP32。

## 3. ESP32 串口测试

1. 只用 USB 连接 ESP32。
2. 烧录 `esp32/motor_serial_test/motor_serial_test.ino`。
3. 打开串口监视器，波特率 `115200`。
4. 重启 ESP32，应该看到：

```text
M10 R3X two-drive differential motor controller ready
```

5. 发送 `status`，应该看到类似：

```text
STATUS mode=stop left=0 right=0 battery=unknown chassis=r3x_two_drive_diff
```

## 4. Linux 上位机串口测试

在 Linux 上位机中：

```bash
cd $M10_ROOT/m10-hardware-test/rk3566
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ls /dev/ttyACM* /dev/ttyUSB*
python3 serial_control_test.py --device /dev/ttyACM0
```

如果设备是 `/dev/ttyUSB0`，把命令中的设备名改掉。

测试命令：

```text
status
heartbeat
stop
```

这一步不要求电机转，只确认 Linux 能和 ESP32 通信。

## 5. 架空电机测试

开始前：

- 底盘必须架空。
- 手边必须能快速断开电机电源。
- 确认 TB6612、ESP32、电机电源共地。
- 确认 VM 接的是电机电源，不是 ESP32 的 5V。

测试步骤：

1. 发送 `status`，确认 ESP32 在线。
2. 发送 `forward`，观察左右驱动轮是否都向前。
3. 立即发送 `stop`。
4. 发送 `backward`，观察左右驱动轮是否都向后。
5. 立即发送 `stop`。
6. 发送 `left`，观察左轮后退、右轮前进。
7. 立即发送 `stop`。
8. 发送 `right`，观察左轮前进、右轮后退。
9. 立即发送 `stop`。

如果方向不对，按 [wiring.md](wiring.md) 的方向校正方法处理。

## 6. 自动停车测试

1. 底盘保持架空。
2. 发送 `forward`。
3. 不发送 `stop`。
4. 等待约 1 秒。
5. ESP32 应该输出：

```text
OK stop timeout
```

6. 电机应该自动停止。

这个测试必须通过后，才允许落地测试。

## 7. 落地低速测试

建议先把 PWM 降低：

```cpp
static const int kForwardPwm = 120;
static const int kTurnPwm = 100;
```

修改位置：

```text
esp32/motor_serial_test/motor_control_core.h
```

重新烧录后：

1. 清空周围区域。
2. 底盘落地。
3. 发送 `forward` 后马上 `stop`。
4. 确认车向前短距离移动。
5. 再依次测试 `backward`、`left`、`right`。
6. 每次运动后检查 TB6612 和电机温度。

## 8. 通过标准

这一轮底盘控制测试通过的标准：

- Linux 能稳定打开 ESP32 串口。
- `status` 和 `heartbeat` 有响应。
- `forward/backward/left/right/stop` 都有 `OK` 响应。
- 左右电机方向符合预期。
- 1 秒超时停车有效。
- 电机启动时 ESP32 不重启。
- 电机启动时 Linux 上位机不重启。
- TB6612 不明显发烫。
- 电机无持续堵转和异常噪声。

## 9. 常见失败处理

| 失败现象 | 优先检查 |
| --- | --- |
| 没有串口设备 | USB 线、ESP32 上电、`/dev/ttyACM0` 或 `/dev/ttyUSB0` |
| 串口打不开 | Linux 用户串口权限、是否被 Arduino IDE 串口监视器占用 |
| ESP32 有响应但电机不转 | TB6612 VM、STBY、GND 共地、PWM/方向线 |
| 一动就重启 | 电源掉压、电机电源和逻辑电源耦合太重 |
| 方向反 | 交换电机输出线或修改 `inverted` |
| 左右控制反 | 左右电机接到了错误通道 |
| 转向无力 | PWM 太低、电池电压低、机械摩擦大 |
