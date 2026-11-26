# M10 电机实机连调记录（2026-08-05）

## 当前结论

- RK3566 ADB 设备：`DEVICE_IDENTIFIER`，型号 `rk3566_tspi`。
- RK3566 USB Host 已识别 FTDI：VID:PID `0403:6001`，产品名
  `FT232R USB UART`，序列号 `DEVICE_IDENTIFIER`。
- Android 应用 `com.example.android.BluetoothChat` 已获 USB 权限并以
  115200 baud 建立连接。
- 自动协议探测成功选择 `M10_V2`；调试页显示 CRC=0、malformed=0。
- 已发送显式 STOP。通信日志中 STOP 帧后收到对应 ACK，遥测左右目标为
  `0 / 0`。
- 未向当前固件发送运动命令，因为当前运行固件使用旧 GPIO 映射，与现场
  提供的新接线表不一致。

## 现场提供的新映射

| TB6612 | ESP32-S3 |
| --- | ---: |
| PWMA | GPIO9 |
| PWMB | GPIO10 |
| AIN2 | GPIO17 |
| AIN1 | GPIO18 |
| BIN1 | GPIO11 |
| BIN2 | GPIO12 |
| STBY | 外部直连 5V，不连接 ESP32 GPIO |

旧固件把 GPIO12 用作 STBY；新接线把 GPIO12 用作 BIN2。两者不能复用。
`m10_motor_controller.ino` 已更新六根控制线，并把 `STBY_PIN` 设为
`-1`，与现场 STBY 外部常高接法一致。

## 构建与测试

构建目标：

```text
esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB
```

构建产物目录：

```text
output/firmware/m10_motor_controller_20260805_stby_pending/
```

验证结果：

- Arduino 编译通过，Sketch 280273 bytes，RAM 19428 bytes。
- `test_motor_control_core.cpp`：通过。
- `test_m10_protocol_core.cpp`：通过。
- `test_serial_control_test.py`：1 passed。

## 当前物理阻塞

1. STBY 已确认外部直连 5V；首次点动前仍须确认 TB6612 逻辑 VCC，以保证
   STBY=5V 和 ESP32=3.3V 控制电平都处于推荐工作范围。
2. ESP32 已临时接到 Mac，识别为 `/dev/cu.usbmodem101`；刷完需接回 RK3566。
3. 刷入正确引脚固件后，首测只执行 STOP -> 低速 200 ms -> STOP，并以
   现场轮子动作作为最终证据。串口 ACK 不能替代物理动作确认。

## STOP/ACK 证据样例

```text
TX AA 55 02 11 AC 1B 00 00 8D 3D
RX AA 55 02 04 AC 1B 02 00 AC 1B 11 6B
```

Android 系统时钟当前显示 2024-05-14，与真实日期不一致；上述帧来自本次
2026-08-05 会话导出的实时通信环形日志。

## 2026-08-05 Mac 刷写结果

- Mac 端口：`/dev/cu.usbmodem101`。
- 端口实际设备：Espressif `USB JTAG/serial debug unit`，不是 FT232R
  运行串口。
- 芯片：ESP32-S3 revision v0.2，MAC `DEVICE_IDENTIFIER`。
- Flash：16MB，quad 模式。
- 固件目录：
  `output/firmware/m10_motor_controller_20260805_stby_5v/`。
- 应用镜像 SHA-256：
  `1fd182f18390139cdadd1f707618e52928c25c52af2a6cc09b56869cfbab9ea1`。
- bootloader、分区表、boot_app0、应用四段均已写入，esptool 对每段报告
  `Hash of data verified`，随后硬复位成功。

`USB CDC On Boot` 在当前构建中为 Disabled，协议代码的 `Serial` 继续走
UART/FT232R。这是 RK3566 运行连接所需的配置。因此从原生 USB-JTAG 端口
发送 HELLO 没有收到响应属于端口不同，不应为 Mac 验证而切换 CDC 配置。
接回 RK3566/FT232R 后再执行 HELLO、STOP 和低速点动验收。

## 2026-08-05 新引脚固件 RK3566 点动结果

- FT232R 回接后，Android 自动识别 `M10_V2`，CRC=0、malformed=0。
- 手动速度设为 `240/1000`，固件换算 PWM 约为 `62/255`。
- 运动窗口内发出 11 个 `SET_MOTOR`，左右目标均为 `240/240`；每个命令
  均收到对应 ACK。
- 首个运动帧：Android 时钟 `10:12:32.700`。
- 最后一个运动帧：Android 时钟 `10:12:33.700`。
- STOP：`10:12:33.768` 发出，`10:12:33.780` 收到 ACK。
- `10:12:33.949` 遥测恢复为左右 `0/0`，之后冗余 STOP 也收到 ACK。
- 无协议故障、CRC 错误或连接重连。

本次实际运动命令窗口约 1.0 秒，不是预期的 200 ms。原因是 Android
`input motionevent` 每次调用存在较大的固定延迟，虽然内部 sleep 为 200 ms，
DOWN 和 UP 之间仍被拉长。输出只有 24%，且 STOP/ACK/零目标均已确认，但
后续不得再用 ADB 长按方式做严格短脉冲；应让应用调用带 `durationMs` 的
`remoteMove(..., 200)`，由 ESP32 到期自行停车。

串口证据只确认 ESP32 已执行目标和停车逻辑。轮子是否真实转动、抖动或
蜂鸣仍需现场观察后才能填写最终物理结论。

## 2026-08-05 Arduino IDE 测试草图兼容

- 用户用 Arduino IDE 验证轮子可动后将 ESP32 接回 RK3566；该草图不再返回
  `M10_V2` 的 `HELLO_ACK`，对 `status\n` 探测也无任何回包，Android 调试页
  显示 `RX=0`。
- APK 新增显式 `ARDUINO_V1_NO_ACK` 模式，采用 MiniBalance V1 原始方向字节：
  前进 `0x01`、后退 `0x05`、左转 `0x07`、右转 `0x03`、停车 `0x00`。
- 新增“Arduino V1 前进点动 200ms”入口，运动期限由 Android Service 的
  `CommandScheduler` 执行，不依赖 ADB 或触摸松手时延。
- RK3566 已覆盖安装新 Debug APK，界面显示
  `已连接（Arduino V1 无回包） · USB CDC/串口`。
- 实机通信日志确认每个点动窗口发出两个 100ms 间隔的 `0x01`，随后发出
  `0x00`。界面自动化滚动误触点动按钮数次，但每次都在 200ms 内停车，
  最后一个 `0x00` 时间为 Android 板载时钟 `10:23:06.182`。
- 因当前草图无 ACK/遥测，本条只能证明 APK 已向 FT232R 写出方向和停车字节；
  轮子是否实际动作仍必须以现场观察为最终证据。

## 2026-08-05 恢复 M10 V2 固件

- Arduino 测试草图确认不能响应 APK 后，将 ESP32-S3 原生 USB 下载口重新接到
  Mac，端口为 `/dev/cu.usbmodem101`。
- esptool 再次识别 ESP32-S3 revision v0.2，MAC
  `DEVICE_IDENTIFIER`。
- 已刷回现场正确引脚版本 `m10_motor_controller_20260805_stby_5v`：bootloader
  `0x0`、分区表 `0x8000`、boot_app0 `0xe000`、应用 `0x10000`。
- 四段写入均报告 `Hash of data verified`；随后独立执行 `verify_flash`，四段均
  报告 `verify OK (digest matched)`，最后硬复位成功。
- 应用镜像仍为 280640 bytes，SHA-256
  `1fd182f18390139cdadd1f707618e52928c25c52af2a6cc09b56869cfbab9ea1`。
- 刷写后 RK3566 的 ADB 连接暂时不在线；待 RK3566 与 FT232R 恢复连接后，
  继续执行 APK `AUTO -> M10_V2` 握手、STOP 和短点动验证。

## 2026-08-05 恢复后的 APK 安全点动

- RK3566 与 FT232R 接回后，APK 以 115200 baud 打开串口，并从有效帧自动
  选择 `M10_V2`。调试页显示 RX 持续增长、CRC=0、malformed=0、reconnect=0，
  心跳延迟约 14ms。
- APK 的测试入口已改为通用“安全前进点动 200ms”，M10 V2 与显式 Arduino
  V1 模式都由 Android Service 的 `CommandScheduler` 定时停车。
- 本次完整点动帧证据：
  - `10:14:34.155`：`SET_MOTOR`，左右 `120/120`，duration `200ms`。
  - `10:14:34.169`：对应 ACK。
  - `10:14:34.319`：遥测左右目标 `120/120`。
  - `10:14:34.356`：Service 发送 `STOP`。
  - `10:14:34.369`：STOP ACK。
  - `10:14:34.519`：遥测恢复 `0/0`。
- 板端导出日志：
  `/sdcard/Android/data/com.example.android.BluetoothChat/files/m10-logs/`
  `m10-communication-20240514-101439.log`。
- 上述证据确认 APK、FT232R、ESP32 协议执行和停车链路正常；物理轮子是否
  转动仍需现场观察确认。

## 2026-08-05 物理方向验收与左轮反相修正

- 用户现场确认安全点动时轮子有转动，但表现为“左轮向后、右轮向前”。
  这证明供电、TB6612、两路 PWM 和电机均能动作，同时确认左电机物理极性
  与逻辑坐标相反。
- 方向修正放在 ESP32 电机层：`LEFT_INVERTED=true`、
  `RIGHT_INVERTED=false`。未在 APK 中把前进改成异号目标，以免破坏手动、
  远程和 AI 控制的一致坐标系。
- 修正固件已通过两项 C++ 测试及 Python 测试，并用 ESP32 Arduino 2.0.17
  编译成功：Sketch 280273 bytes，RAM 19428 bytes。
- 新固件目录：
  `output/firmware/m10_motor_controller_20260805_left_inverted/`。
- 新应用镜像 SHA-256：
  `ef6fe86f61ae309595e327b701dde0b0c30ee81e548a78e7bd4a6afcc6cdc631`。
- ESP32-S3 原生 USB 下载口再次接入 Mac 后，esptool 识别 revision v0.2、
  MAC `DEVICE_IDENTIFIER`，已将方向修正版完整刷入：bootloader `0x0`、
  分区表 `0x8000`、boot_app0 `0xe000`、应用 `0x10000`。
- 四段写入阶段均报告 `Hash of data verified`；随后独立执行
  `verify_flash`，四段均为 `verify OK (digest matched)`，并通过 RTS 硬复位
  启动新固件。
- 待接回 RK3566 后复测；协议和遥测通过后，只执行一次 200ms 的
  `+240/+240` 点动。两轮是否同向前进仍以现场观察为最终结论。

## 2026-08-05 左轮反相刷写后与 8 方向验收

- 方向修正版固件已完整刷入 ESP32-S3；bootloader、分区表、boot_app0、
  应用四段均通过独立 `verify_flash`，结果为 `verify OK (digest matched)`。
- 接回时曾误用 ESP32 原生 USB-JTAG `303a:1001`；当前固件
  `USB CDC On Boot=Disabled`，M10 协议实际走 UART/FT232R，因此该端口不会
  收到协议。换回 FT232R `0403:6001`、序列号 `DEVICE_IDENTIFIER` 后恢复正常。
- 用户确认修正后的安全前进点动两轮均能正常动作。
- APK 新增“8方向安全自检（每项250ms）”：左转、前进、右转、左前、
  右前、左后、后退、右后，统一使用 24% 输出，每步 250ms，步间自动停车；
  手动输入、STOP 或急停会使未执行步骤失效。
- 手动控制默认速度从过低的 `50/1000` 调整为已经实机验证能带动轮子的
  `240/1000`；用户仍可通过滑杆调整，松手立即停车的行为不变。
- Android 单元测试与最终 Debug 构建通过，`BUILD SUCCESSFUL`（32 tasks）；
  最终 APK SHA-256 为
  `918b671e4d10c2325f0711519fc1005e2be33f6fc1ca73d2cdf8ad5d65d27bf3`。
- 实机序列共观察到开始前 STOP、8 次到期 STOP 和结束冗余 STOP。完成后
  调试状态为 `M10_V2`、RX=1011、CRC=0、malformed=0、reconnect=0、
  heartbeat=14ms；首页遥测左右轮 `0/0`、故障 `NONE`。
- 上述数据证明 8 组目标均已按时发送并停车；各方向的物理运动语义仍须由
  现场观察确认后才能完成最终验收。
