# M10 ESP32-S3 电机控制固件

## 结论

`skill car` 中只有 `esp32/motor_serial_test` 是 ESP32-S3 电机草案。WHEELTEC 压缩包中的完整底盘程序均面向 STM32F103/STM32F407，不能烧录到 ESP32-S3。

为了匹配当前 Android 主控，正式候选固件位于：

```text
esp32/m10_motor_controller/
```

旧 `motor_serial_test` 保留为文本命令和接线验证工具，不作为 M10 正式固件。

## 已实现

- M10 Protocol V2 二进制帧、CRC16-CCITT-FALSE；
- 半包、粘包、噪声、非法长度和 CRC 错误恢复；
- HELLO/HELLO_ACK、HEARTBEAT/ACK、PING/PONG；
- SET_MOTOR、STOP、EMERGENCY_STOP、CLEAR_EMERGENCY_STOP；
- 左右轮组目标值 `-1000..1000` 到 TB6612 PWM 的映射；
- 300 ms 通信看门狗；
- `durationMs` 到期停车；
- 急停锁存；
- 重复 sequence 只重发 ACK，不重复执行运动；
- 未建立 M10 会话时拒绝运动；
- 开机和异常时 STBY 拉低；
- 200 ms 遥测，未配置传感器使用 `0xFFFF` 表示未知。

## 默认硬件配置

构建目标来自本文件夹原始硬件清单：`ESP32-S3 DevKitC-1 N16R8`。

| TB6612 | ESP32-S3 |
| --- | ---: |
| STBY | 外部直连 5V，不占用 GPIO；点动前仍须核对 TB6612 逻辑 VCC |
| PWMA / AIN1 / AIN2 | GPIO9 / GPIO18 / GPIO17 |
| PWMB / BIN1 / BIN2 | GPIO10 / GPIO11 / GPIO12 |

> 2026-08-05 实机连调更新：GPIO12 已明确用于 BIN2，禁止再同时作为
> STBY。现场确认 STBY 外接 5V，因此 `STBY_PIN` 保持 `-1`。根据 Toshiba
> 数据手册，输入绝对上限为 6V，但推荐工作上限为 VCC+0.2V；首次点动前
> 必须确认 TB6612 逻辑 VCC 与 5V STBY、ESP32 3.3V 控制电平兼容。

在确认当前小智板确实是该板型、上述 GPIO 没有被音频/屏幕器件占用、TB6612 接线一致之前，不得接通电机电源。

## 构建产物

N16R8 合并镜像：

```text
output/firmware/m10_motor_controller_n16r8/m10_motor_controller_n16r8_merged.bin
```

参数：

- 芯片：ESP32-S3；
- Flash：16 MB；
- PSRAM：8 MB OPI；
- Flash mode：DIO 80 MHz；
- 分区：3 MB APP + 9.9 MB FATFS；
- 镜像写入地址：`0x0`；
- SHA-256：`1b08b66243dd9cb43b896d03c3eb8b14286be8e5b9f62c74263e3291a823bc45`。

## 覆盖小智

当前 ESP32 的 FT232R 插在 RK3566 Android USB Host 上，macOS 没有看到对应 `/dev/cu.*`，Android 内核也没有创建 `/dev/ttyUSB*`。因此当前连接方式只能由 APP 读写串口，不能让 `esptool` 进入 ROM Bootloader 并擦写 Flash。

烧录前：

1. 断开电机电源，只保留 ESP32 逻辑供电；
2. 将 FT232R/ESP32 USB 直接接到 Mac；
3. 确认板型为 ESP32-S3 N16R8；
4. 确认 IO0/BOOT 与 EN/RST 可以进入下载模式；
5. `arduino-cli board list` 中出现真实串口。

执行：

```bash
cd $M10_ROOT/m10-hardware-test
chmod +x scripts/flash_m10_motor_n16r8.sh
scripts/flash_m10_motor_n16r8.sh /dev/cu.usbserial-实际端口 --erase-xiaozhi
```

脚本会校验镜像 SHA-256，执行整片擦除并从 `0x0` 写入合并镜像。若芯片启用了 Secure Boot 或 Flash Encryption，`esptool` 会拒绝操作；脚本不会使用 `--force` 绕过保护。

## 首次验收

1. 电机电源保持断开，重新把 ESP32 接到 RK3566；
2. APP 应从 `UNKNOWN` 自动切换到 `M10_V2`，不再显示“小智 AI 日志口”；
3. 验证 HELLO_ACK、心跳 ACK 和遥测；
4. 接 TB6612，但底盘必须架空；
5. 先验证急停和 300 ms 断线停车；
6. 最后以低速短脉冲验证左右轮方向。
