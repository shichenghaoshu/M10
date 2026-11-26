# R3X 四轮两驱差速底盘 ESP32 使用手册

本文档说明如何用 ESP32-S3 驱动 WHEELTEC R3X 四轮两驱差速底盘，并让 Linux 上位机通过串口控制底盘前进、后退、转向和停车。

## 1. 系统结构

控制链路如下：

```text
Linux 上位机
  |
  | USB 串口，115200 baud，文本命令
  v
ESP32-S3
  |
  | PWM + 方向控制信号
  v
TB6612FNG 双路电机驱动
  |
  | AO1/AO2、BO1/BO2
  v
R3X 左右驱动电机
```

第一版固件不使用编码器闭环，只做开环 PWM。这样更适合先验证电机方向、接线、电源稳定性和上位机通信。

## 2. 准备硬件

需要准备：

- ESP32-S3 开发板
- WHEELTEC R3X 四轮两驱差速底盘
- TB6612FNG 或兼容双路电机驱动板
- 电池或电机供电电源
- 5V 稳压模块，用于 Linux 上位机或其他外设
- USB 数据线
- 杜邦线、万用表、主开关、保险丝

建议准备：

- 可调电源，用于桌面调试
- 小车支架或垫块，用于架空底盘
- 备用 TB6612 驱动板

## 3. 供电原则

不要把电机接到 ESP32 或 Linux 板子的 5V 引脚上。电机是大电流感性负载，启动瞬间会拉低电压，轻则重启，重则烧板。

推荐供电：

```text
电池
  -> 主开关
  -> 保险丝
  -> 电源分配
       -> 电机电源 VM，进入 TB6612
       -> 5V 稳压，供 Linux 上位机
       -> USB 或独立稳压，供 ESP32
```

必须共地：

- ESP32 GND
- TB6612 GND
- 电机电源负极
- Linux 上位机 GND，若使用直连 UART

开发阶段如果 Linux 和 ESP32 通过 USB 连接，USB 线已经提供了信号地；但 TB6612 的 GND 仍然要和 ESP32 GND 接在一起。

## 4. TB6612 接线

默认固件使用下面的 GPIO：

| TB6612 引脚 | ESP32-S3 引脚 | 说明 |
| --- | ---: | --- |
| VCC | 3V3 | 逻辑电源 |
| GND | GND | 逻辑地，必须和电机电源共地 |
| STBY | GPIO12 | 驱动待机控制，固件启动后拉高 |
| PWMA | GPIO4 | 左电机 PWM |
| AIN1 | GPIO5 | 左电机方向 |
| AIN2 | GPIO6 | 左电机方向 |
| PWMB | GPIO7 | 右电机 PWM |
| BIN1 | GPIO15 | 右电机方向 |
| BIN2 | GPIO16 | 右电机方向 |
| VM | 电机电源正极 | 按驱动板规格接入，一般接电池或电机稳压输出 |
| AO1/AO2 | 左驱动电机两根动力线 | 如果方向反了，交换 AO1/AO2 |
| BO1/BO2 | 右驱动电机两根动力线 | 如果方向反了，交换 BO1/BO2 |

R3X 霍尔编码器线第一版先不接入 ESP32 控制逻辑。建议把编码器插头保留好，后续做速度闭环时再接。

## 5. ESP32 固件说明

固件路径：

```text
esp32/motor_serial_test/motor_serial_test.ino
```

运动映射核心路径：

```text
esp32/motor_serial_test/motor_control_core.h
```

默认 PWM：

- 前进/后退：`180`
- 原地转向：`160`
- 最大 PWM：`255`

命令映射：

| 命令 | 左电机 | 右电机 |
| --- | ---: | ---: |
| `forward` | +180 | +180 |
| `backward` | -180 | -180 |
| `left` | -160 | +160 |
| `right` | +160 | -160 |
| `stop` | 0 | 0 |

如果实车速度太快，可以先把 `motor_control_core.h` 里的 `kForwardPwm` 和 `kTurnPwm` 调小，例如调到 `120` 和 `100`。

如果某一侧方向反了，有两种修法：

- 硬件修法：交换该侧电机在 TB6612 输出端的两根线。
- 软件修法：把 `motor_serial_test.ino` 中对应电机的 `inverted` 从 `false` 改成 `true`。

例如右侧反了：

```cpp
static const MotorPins RIGHT_DRIVE = {"right_drive", 7, 15, 16, true};
```

## 6. 烧录固件

### Arduino IDE 方式

1. 打开 Arduino IDE。
2. 安装 ESP32 开发板支持包。
3. 打开 `esp32/motor_serial_test/motor_serial_test.ino`。
4. 开发板选择 `ESP32S3 Dev Module`。
5. 选择 ESP32 对应串口。
6. 点击编译。
7. 点击上传。
8. 打开串口监视器，设置 `115200` 波特率。
9. 发送 `status`，应看到类似：

```text
STATUS mode=stop left=0 right=0 battery=unknown chassis=r3x_two_drive_diff
```

### arduino-cli 方式

如果系统装了 `arduino-cli`：

```bash
cd $M10_ROOT/m10-hardware-test
arduino-cli compile --fqbn esp32:esp32:esp32s3 esp32/motor_serial_test
arduino-cli upload -p /dev/ttyACM0 --fqbn esp32:esp32:esp32s3 esp32/motor_serial_test
```

如果没有 `arduino-cli`，用 Arduino IDE 即可。

## 7. Linux 上位机控制

安装 Python 依赖：

```bash
cd $M10_ROOT/m10-hardware-test/rk3566
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

确认串口：

```bash
ls /dev/ttyACM* /dev/ttyUSB*
```

启动控制脚本：

```bash
python3 serial_control_test.py --device /dev/ttyACM0
```

如果你的串口是 `/dev/ttyUSB0`，就改成：

```bash
python3 serial_control_test.py --device /dev/ttyUSB0
```

进入提示符后输入：

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

每条运动命令第一次都只让电机转很短时间，然后马上 `stop`。

## 8. 首次实车测试流程

### 8.1 不接电机测试通信

1. 只用 USB 连接 ESP32。
2. 烧录固件。
3. 运行 `serial_control_test.py`。
4. 输入 `status`。
5. 确认 ESP32 有响应。

### 8.2 接驱动板但架空底盘

1. 断电。
2. 按接线表连接 ESP32 和 TB6612。
3. 连接左右驱动电机到 AO1/AO2、BO1/BO2。
4. 连接电机电源到 VM 和 GND。
5. 把底盘架空。
6. 上电。
7. 输入 `forward`，观察两侧轮子方向。
8. 输入 `stop`。

### 8.3 检查方向

期望现象：

- `forward`：左右驱动轮都让车向前。
- `backward`：左右驱动轮都让车向后。
- `left`：左轮后退，右轮前进。
- `right`：左轮前进，右轮后退。

如果 `forward` 变成后退，左右两侧都反了。可以交换两侧电机输出线，或者在固件里把左右 `inverted` 都改成 `true`。

如果只有一侧反了，只调整那一侧。

### 8.4 落地低速测试

1. 把 `kForwardPwm` 和 `kTurnPwm` 调低，例如 `120` 和 `100`。
2. 重新烧录。
3. 保持周围空旷。
4. 发送 `forward` 后马上 `stop`。
5. 确认车不会冲出去，再逐步延长运动时间。

## 9. 常见问题

| 现象 | 可能原因 | 处理方式 |
| --- | --- | --- |
| Linux 找不到 `/dev/ttyACM0` | USB 线不是数据线，或驱动/权限问题 | 换数据线，执行 `lsusb`，检查 `/dev/ttyUSB0` |
| 脚本提示权限不足 | 当前用户无串口权限 | 临时用 `sudo` 测试，长期把用户加入 `dialout` 组 |
| ESP32 有响应但电机不转 | TB6612 未供 VM、电机电源未开、STBY 未接对 | 查 VM 电压、GND 共地、STBY 接 GPIO12 |
| 只有一个电机转 | 另一侧 PWM/方向线或电机输出线接错 | 按接线表逐线检查 |
| 一发送前进板子重启 | 电机电源拉低逻辑电源 | 电机和 Linux/ESP32 分开供电，检查稳压模块电流 |
| 前进方向反了 | 电机输出极性相反 | 交换电机输出线或改 `inverted` |
| 车左右转向相反 | 左右电机接反 | 交换左右电机通道，或调整固件左右定义 |
| 电机发热明显 | 堵转、负载过大、PWM 太高、驱动电流不足 | 立即断电，降低 PWM，检查机械阻力 |

## 10. 下一步建议

第一版跑通后，再做这些升级：

1. 接入左右霍尔编码器。
2. 增加速度测量。
3. 做左右电机速度闭环 PID。
4. 把协议从简单方向命令升级为 `cmd_vel vx wz`。
5. 迁移到 ESP-IDF，使用 FreeRTOS 任务拆分串口、电机控制、编码器采样和安全保护。
