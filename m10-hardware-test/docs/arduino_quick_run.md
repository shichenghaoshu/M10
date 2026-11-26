# Arduino CLI 快速跑通 R3X 底盘

本文档用于最快速度把 ESP32-S3 固件编译、烧录并和 Linux 上位机串口控制跑通。

这里说的 Arduino 指 Arduino 开发环境和 Arduino-ESP32 core。它不是硬件上必须存在的一块板，也不是最终架构必须长期依赖的框架。我们用它的原因是首版底盘调试速度快：不用先搭完整 ESP-IDF 工程，就能验证接线、电机方向、电源和串口协议。

## 1. 本机已安装内容

当前这台 Mac 已经安装：

```bash
arduino-cli version
```

已验证版本：

```text
arduino-cli 1.4.1
```

ESP32 开发板核心也已经安装：

```bash
arduino-cli core list
```

已验证：

```text
esp32:esp32 2.0.17
```

项目固件已经编译通过：

```bash
cd $M10_ROOT/m10-hardware-test
arduino-cli compile --fqbn esp32:esp32:esp32s3 esp32/motor_serial_test
```

编译通过时会看到类似：

```text
Sketch uses 276989 bytes (21%) of program storage space.
Global variables use 18984 bytes (5%) of dynamic memory.
```

## 2. 如果换一台电脑重新安装

macOS 推荐用 Homebrew：

```bash
brew install arduino-cli
arduino-cli config init --overwrite
arduino-cli config set board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli config set network.connection_timeout 600s
arduino-cli core update-index
arduino-cli core install esp32:esp32@2.0.17
```

如果网络中断，直接重复最后一条安装命令即可：

```bash
arduino-cli core install esp32:esp32@2.0.17
```

## 3. 插上 ESP32 后找串口

先只插 ESP32 USB，不接电机电源。

查看串口：

```bash
arduino-cli board list
```

macOS 常见端口：

```text
/dev/cu.usbmodem1101
/dev/cu.usbserial-0001
/dev/cu.wchusbserialXXXX
```

Linux 常见端口：

```text
/dev/ttyACM0
/dev/ttyUSB0
```

如果 `arduino-cli board list` 里没有新串口，检查：

- USB 线必须是数据线，不是只能充电的线。
- ESP32 是否需要按住 `BOOT` 再点 `RESET` 进入下载模式。
- macOS 是否弹出过 USB 配件权限。
- CH340/CP210x 串口芯片是否需要驱动。

## 4. 编译固件

进入工程：

```bash
cd $M10_ROOT/m10-hardware-test
```

编译：

```bash
arduino-cli compile --fqbn esp32:esp32:esp32s3 esp32/motor_serial_test
```

如果你的板子不是通用 ESP32-S3 Dev Module，可以先列出可选板型：

```bash
arduino-cli board search esp32s3
```

当前推荐先用：

```text
esp32:esp32:esp32s3
```

## 5. 上传固件

把 `<PORT>` 换成实际串口：

```bash
arduino-cli upload -p <PORT> --fqbn esp32:esp32:esp32s3 esp32/motor_serial_test
```

macOS 示例：

```bash
arduino-cli upload -p /dev/cu.usbmodem1101 --fqbn esp32:esp32:esp32s3 esp32/motor_serial_test
```

Linux 示例：

```bash
arduino-cli upload -p /dev/ttyACM0 --fqbn esp32:esp32:esp32s3 esp32/motor_serial_test
```

如果上传时一直等待连接，按住 ESP32 的 `BOOT` 键，再点一下 `RESET`，看到开始写入后松开 `BOOT`。

## 6. 串口快速自检

上传完成后先不接电机电源，只验证 ESP32 串口响应。

打开串口监视器：

```bash
arduino-cli monitor -p <PORT> -c baudrate=115200
```

输入：

```text
status
```

期望看到：

```text
STATUS mode=stop left=0 right=0 battery=unknown chassis=r3x_two_drive_diff
```

再输入：

```text
heartbeat
```

期望看到心跳响应。如果串口监视器输入不方便，也可以后面直接用 Python 上位机脚本测试。

## 7. 接线后第一次让轮子转

首次电机测试一定架空底盘。

最小接线：

| TB6612 | ESP32-S3 | 说明 |
| --- | ---: | --- |
| VCC | 3V3 | 逻辑供电 |
| GND | GND | 必须共地 |
| STBY | GPIO12 | 驱动使能 |
| PWMA | GPIO4 | 左电机 PWM |
| AIN1 | GPIO5 | 左电机方向 |
| AIN2 | GPIO6 | 左电机方向 |
| PWMB | GPIO7 | 右电机 PWM |
| BIN1 | GPIO15 | 右电机方向 |
| BIN2 | GPIO16 | 右电机方向 |
| VM | 电机电源正极 | 不要接 ESP32 5V |
| AO1/AO2 | 左电机动力线 | 方向反了就交换 |
| BO1/BO2 | 右电机动力线 | 方向反了就交换 |

测试顺序：

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
```

注意：固件有 1 秒运动超时保护，即使忘记发送 `stop`，也会自动停车。但第一次测试仍然建议每条运动命令后马上手动 `stop`。

## 8. Linux 上位机控制

在 RK3566/Linux 上位机：

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

启动控制：

```bash
python3 serial_control_test.py --device /dev/ttyACM0
```

如果 ESP32 显示为 `/dev/ttyUSB0`：

```bash
python3 serial_control_test.py --device /dev/ttyUSB0
```

进入交互界面后输入命令即可控制底盘。

## 9. 常见问题

### 编译成功但上传失败

优先检查端口是否选错：

```bash
arduino-cli board list
```

如果端口对，但无法进入下载模式，按住 `BOOT`，点 `RESET`，开始上传后松开 `BOOT`。

### Linux 没权限打开串口

临时方式：

```bash
sudo chmod 666 /dev/ttyACM0
```

长期方式是把当前用户加入串口用户组。Ubuntu 常见是：

```bash
sudo usermod -aG dialout $USER
```

执行后重新登录。

### 车轮方向反了

先断开电机电源，再处理。推荐先用硬件方式交换该侧电机输出线。也可以改固件里的 `inverted` 参数：

```cpp
static const MotorPins LEFT_DRIVE = {"left_drive", 4, 5, 6, true};
static const MotorPins RIGHT_DRIVE = {"right_drive", 7, 15, 16, false};
```

改完后重新编译上传。

### 一发前进 ESP32 就重启

通常是电机启动电流让电源掉压。检查：

- 电机 VM 是否没有从 ESP32 取电。
- ESP32、TB6612、电机电源是否共地。
- 电机电源电流是否足够。
- Linux 上位机是否用独立稳定 5V 供电。
