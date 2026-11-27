# 一键复刻：M10 + Dreamupers

仓库新增统一启动器 `m10.sh` 与 `m10_runtime/`。它连接现有 Web 表情、Dreamupers 遥控页、Radxa GPIO 驱动和 FFmpeg 图传配置，并提供与正式 ESP32 固件匹配的 V2 串口适配。

## 1. 电脑上先跑起来

需要 Python 3.9+、Git 与首次安装的网络连接。支持 macOS / Linux；Windows 可在适当的 Linux / WSL 环境尝试，本次没有验证 Windows 硬件访问。

```bash
git clone https://github.com/shichenghaoshu/M10.git
cd M10
./m10.sh
```

第一次运行自动创建仓库内 `.m10/venv`，安装固定版本的运行依赖；以后依赖清单未变化时直接启动。不会安装进系统 Python，也不会自动刷写固件、修改接线或安装 BSP。

点击终端打印的完整链接即可进入已配对控制台，默认地址为 `http://127.0.0.1:8000`。配对码在 URL fragment 中，页面读取后清除 fragment；不要把含配对码的链接公开分享。

默认 `demo` 模式没有实体运动：可以验证遥控消息、动作期限、急停、表情切换和 Dreamupers 页面。相机、电流、电压未连接时保持不可用或 null，不生成假帧与假读数。

## 2. 三种配置

| 配置 | 启动命令 | 实际接入 |
| --- | --- | --- |
| 电脑演示 | `./m10.sh demo` | 明确标记的模拟电机、10 组真实表情资源、统一控制台 |
| M10 ESP32 | `./m10.sh esp32 --serial /dev/ttyUSB0 --arm` | V2 握手、CRC、匹配 ACK、有限期限左右轮目标 |
| Dreamupers Radxa | `./m10.sh radxa --arm` | 调用原版 `TB6612MotorDriver`，沿用其 GPIO / PWM 路线 |

`--arm` 是启用实体后端的启动参数，不会在启动时发出非零运动。未启用、握手失败或硬件缺失时拒绝运动，不自动退回模拟后端。初次实体运动仍先架空、低速短脉冲验证轮向。

Radxa 默认引脚来自原作者的 ZERO 3W 配置，不能照搬到其他 RK3566 板卡。当前 M10 Android 实机路线仍使用独立 APK；这个 Python 启动器面向桌面 / Linux，不会一键把 Android 变成 Linux。

## 3. 自检与配置

```bash
./m10.sh doctor
./m10.sh doctor --profile esp32 --serial /dev/ttyUSB0
./m10.sh doctor --profile radxa
```

检查源代码快照哈希、表情文件、设备节点和对应依赖，不对设备发送运动命令。报告 ready 只代表这些前置检查通过，不是整机验收。普通用户还需具备串口、GPIO、PWM 和相机的相应权限。

本地覆盖文件示例：

```yaml
# 保存为仓库外配置文件，或 .m10/local.yaml。
serial_port: /dev/ttyACM0
speed_percent: 15
lease_ms: 250
media:
  device: /dev/video2
  input_format: mjpeg
  video_size: 1280x720
  encoder: libx264
```

```bash
./m10.sh esp32 --config .m10/local.yaml --arm
```

参数模板见 [profiles/default.yaml](../profiles/default.yaml)、[esp32.yaml](../profiles/esp32.yaml)、[radxa.yaml](../profiles/radxa.yaml)。未知配置键会报错。GPIO 参数必须对应设备真实引脚；串口和 PWM 目标没有自动变成物理轮速。

## 4. Dreamupers 融入了什么

| 上游内容 | 在当前工程里的使用方式 |
| --- | --- |
| `motor.py` | Radxa 后端直接导入并调用原驱动，外加统一动作期限和控制权 |
| `vc.py` | 配置 `sensor.enabled: true` 后，导入原 INA226 驱动；缺失或读取失败如实返回 |
| `templates/ws_index.html` | `/dreamupers` 提供原遥控页，经运行时适配改为同源服务与短动作续发 |
| `rtsp/ffmpeg_cmd.json` | 作为 V4L2 → H264 → RTSP 命令模板，替换设备、编码器和端口 |
| `rtsp/mediamtx.yml` | 沿用媒体组织方式及超时设置，生成仅监听本机的精简配置 |
| LICENSE / 原始源码 | 保留原作者 MIT 署名，记录固定提交与逐文件 SHA-256 |

固定提交为 `c6d6b428322cf0311b0059f7d5bdd287b4bf65a2`。原始文本在 [third_party/dreamupers](../third_party/dreamupers/README.md)，保持逐字节不变；适配代码全部放在 `m10_runtime/`。原仓库 PNG 不在此文本快照中，兼容页图标使用 M10 自有 SVG。

没有直接运行原 `ws_main.py` 的主程序，因此不会执行其中的全局进程清理、默认硬编码地址和主机休眠功能。激光与休眠接口明确返回 501，不假装已执行。

## 5. 摄像头与图传

```bash
# 检查 FFmpeg、编码器、相机节点和 MediaMTX 是否齐备。
./m10.sh doctor --profile radxa --stream

# Linux 首次启用图传会自动下载并校验固定版本 MediaMTX。
./m10.sh radxa --arm --stream
```

也可以独立安装媒体组件后自检：`./m10.sh doctor --profile radxa --fetch-media`。下载来源和官方归档 SHA-256 固定在 [media-assets.json](../m10_runtime/media-assets.json)，目前支持 Linux arm64 / amd64；可通过配置指定已安装的二进制。

启动后在控制台点击“启动图传”。只启动与本实例关联的 MediaMTX / FFmpeg 子进程，停止时只清理这些进程，不按进程名终止其他程序。媒体进程运行和实际收到 HLS 输出分别显示。

FFmpeg 及硬件编码器、内核 V4L2 / RGA / MPP 支持需要在系统层准备。Radxa 使用 `h264_rkmpp`；通用 USB 相机配置可以使用软件 `libx264`。没有匹配的 BSP / 驱动时，pip 不能替代这些依赖。

MediaMTX 的 RTSP / HLS 只监听本机，网页通过统一入口获取受保护的预览。普通浏览器首次播放 HLS 需要加载固定版本 hls.js；Dreamupers 原版样式还依赖 Tailwind CDN。基础 M10 控制页和本地表情不依赖这些 CDN，完整图传离线打包尚待补齐。

## 6. 控制契约

- HTTP 写入使用 Bearer 配对码，WebSocket 使用子协议传递凭据；媒体 Cookie 只能用于读预览，不授予运动写权限。
- 按住方向时浏览器每 100 ms 发新命令，默认每条命令只有 250 ms 租期；普通状态心跳不续期。
- 同时只允许一个连接持有运动租期；旁观连接断开不影响当前控制者，控制者断开则尝试停止。
- ESP32 同时受固件自身看门狗和非零动作期限约束；GPIO 直驱的停车依赖本机进程，SIGKILL / 系统卡死时不能获得独立 MCU 兜底。
- 急停锁存需要显式解除。连接 / ACK 异常会阻止继续运动，重新连接不自动恢复上次动作。
- 视频预览不进入动作闭环。本运行器没有接入连续目标识别 / 身份跟踪，也没有部署 RL 权重。

## 7. 运行器 API

| 入口 | 用途 |
| --- | --- |
| `GET /health` | 基础服务和模拟标记 |
| `POST /api/runtime/pair` | 配对并建立媒体读取 Cookie |
| `GET /api/runtime/status` | 电机、动作租期、传感器、媒体和上游来源 |
| `WS /control/ws` | 短期方向命令；子协议 `m10`、`m10.token.<配对码>` |
| `POST /api/runtime/control` 或 `/control` | `action`；非停止的 HTTP 命令还要求 `client_id` |
| `POST /api/runtime/emergency_stop` | 急停锁存 |
| `POST /api/runtime/clear_emergency_stop` | 显式清除 |
| `POST /api/runtime/reconnect` | 停止后重新连接后端 |
| `POST /start_stream`、`/stop_stream` | 媒体进程控制 |
| `GET /face`、`/dreamupers` | 表情与上游兼容页面 |

已有 `/api/v1/state` 等表情接口直接接入统一服务。旧的独立主控服务和视觉演示仍保留各自协议，启动新运行器不会自动改写这些旧工程。

## 8. 验证边界

新增测试涵盖模拟固件的分片 / CRC / ACK / 超时、租期与控制权、急停、鉴权、表情复用、原版 GPIO 驱动的注入式测试、媒体命令和归档校验。它们不会驱动真实底盘。

本次没有在 Radxa 上完成 GPIO、INA226、硬件编码或相机实测，也没有刷写 ESP32。硬件路线必须在实际板卡上验收。运行 `bash scripts/check.sh` 可复现主机检查；CI 同时验证干净虚拟环境的一键安装和自检。
