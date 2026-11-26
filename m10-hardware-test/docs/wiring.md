# 接线说明

本文档说明 Linux 上位机、ESP32-S3、TB6612FNG 电机驱动板和 WHEELTEC R3X 四轮两驱差速底盘之间的接线。

详细使用流程见 [r3x_esp32_usage.md](r3x_esp32_usage.md)。

## 1. Linux 上位机到 ESP32

开发阶段推荐直接使用 USB 线连接 Linux 上位机和 ESP32-S3。

USB 连接同时提供：

- ESP32 固件烧录通道
- 串口调试通道
- 上位机控制通道
- ESP32 开发阶段供电

Linux 中常见设备名：

- `/dev/ttyACM0`
- `/dev/ttyUSB0`

串口参数：

- 波特率：`115200`
- 数据位：8
- 校验：无
- 停止位：1
- 流控：无

控制命令是一行一个文本命令：

| 命令 | 说明 |
| --- | --- |
| `forward` | 前进 |
| `backward` | 后退 |
| `left` | 原地左转 |
| `right` | 原地右转 |
| `stop` | 停车 |
| `status` | 查询状态 |
| `heartbeat` | 心跳测试 |

## 2. 直连 UART 预留方案

如果后续不用 USB，而是让 RK3566 的 UART 直接连接 ESP32：

| RK3566 | ESP32 |
| --- | --- |
| TX | RX |
| RX | TX |
| GND | GND |

注意：

- 先确认两边 UART 都是 3.3V 电平。
- 不要把 5V TTL 串口直接接到 ESP32 RX。
- 直连 UART 时必须共地。

## 3. ESP32 到 TB6612

R3X 四轮两驱差速底盘按左右两路驱动处理：一个左驱动电机，一个右驱动电机。使用一块 TB6612FNG 双路驱动板即可。

默认固件接线：

| TB6612 引脚 | ESP32-S3 引脚 | 说明 |
| --- | ---: | --- |
| VCC | 3V3 | TB6612 逻辑电源 |
| GND | GND | 必须和 ESP32、电机电源共地 |
| STBY | GPIO12 | 待机控制，固件拉高后驱动板工作 |
| PWMA | GPIO4 | 左电机 PWM |
| AIN1 | GPIO5 | 左电机方向 |
| AIN2 | GPIO6 | 左电机方向 |
| PWMB | GPIO7 | 右电机 PWM |
| BIN1 | GPIO15 | 右电机方向 |
| BIN2 | GPIO16 | 右电机方向 |
| VM | 电机电源正极 | 接电池或电机稳压输出 |
| AO1/AO2 | 左驱动电机 | 接左电机两根动力线 |
| BO1/BO2 | 右驱动电机 | 接右电机两根动力线 |

## 4. 电机线

WHEELTEC 的霍尔编码器直流电机通常包含：

- 两根粗一些的电机动力线，用于驱动电机正反转。
- 多根编码器线，用于测速。

第一版开环固件只接电机动力线：

- 左电机动力线接 TB6612 `AO1/AO2`
- 右电机动力线接 TB6612 `BO1/BO2`

编码器线先不要乱接，避免把 5V 编码器电源接错到 ESP32 GPIO。后续做闭环时再单独确认编码器供电、电平和 A/B 相信号。

## 5. 电源接线

推荐电源结构：

```text
电池
  -> 主开关
  -> 保险丝
  -> 电源分配
       -> TB6612 VM，给电机供电
       -> 5V 稳压，给 RK3566/Linux 上位机
       -> USB 或稳压，给 ESP32
```

关键规则：

- 所有 GND 必须连接在一起。
- 电机电流不要经过 ESP32。
- 电机电流不要经过 RK3566。
- Linux 上位机建议独立 5V 稳压供电。
- 电机电源建议串联 3A 到 5A 保险丝。
- 首次测试时用手能快速断开的主开关。

## 6. 方向校正

发送 `forward` 后，期望左右驱动轮都让车向前。

如果方向不对：

| 现象 | 处理方式 |
| --- | --- |
| 左右都反了 | 同时交换 AO1/AO2 和 BO1/BO2，或把左右 `inverted` 都改为 `true` |
| 只有左侧反了 | 交换 AO1/AO2，或只改左侧 `inverted` |
| 只有右侧反了 | 交换 BO1/BO2，或只改右侧 `inverted` |
| 左右转向相反 | 检查左电机是否接到了 B 路、右电机是否接到了 A 路 |

软件方向配置在：

```text
esp32/motor_serial_test/motor_serial_test.ino
```

默认：

```cpp
static const MotorPins LEFT_DRIVE = {"left_drive", 4, 5, 6, false};
static const MotorPins RIGHT_DRIVE = {"right_drive", 7, 15, 16, false};
```

最后一个参数是 `inverted`。改为 `true` 会反转该侧电机方向。
