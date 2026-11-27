# M10 开源机器人验证平台

RK3566、ESP32-S3 与两驱差速底盘组成的家庭陪伴机器人实验项目。这里公开硬件验证代码、Linux 控制服务、Android / Web 表情播放器、视觉跟踪核心，以及执行器、国产替代和强化学习方案。

**这是多个独立验证模块的源码快照，整机连续跟随与语音闭环仍在开发。** Android 实机路线与 Linux 工程分别保留，避免把单模块测试写成整机完成。

## 一键复刻

```bash
git clone https://github.com/shichenghaoshu/M10.git
cd M10
./m10.sh
```

启动器自动创建本地虚拟环境、安装固定版本依赖并启动统一控制台。默认电脑演示可切换 10 组表情、测试遥控与急停；电机明确标记为模拟，相机和传感器缺失时不生成假数据。打开终端打印的链接即可配对。

Dreamupers 的原版遥控页、Radxa 电机驱动、INA226 驱动和 FFmpeg / MediaMTX 路线已接入新运行器，固定来源与 MIT 署名保留。硬件配置可选：

```bash
./m10.sh doctor
./m10.sh esp32 --serial /dev/ttyUSB0 --arm
./m10.sh radxa --arm --stream
```

实体模式需匹配接线、固件、系统权限和相机 / 编码驱动；`--arm` 启用实体后端，启动本身不产生非零运动。该入口面向桌面 / Linux，不自动替换 Android 系统。连续目标跟踪与 RL 仍在各自实验路线中。

完整配置、首次图传下载、接口与验收边界见 **[一键复刻指南](docs/one-click.md)**。

## 从哪里开始

- [技术方案总览](docs/technical-summary.md)
- [一键复刻与 Dreamupers 集成](docs/one-click.md)
- [代码导读与模块实现](docs/implementation-guide.md)
- [系统架构与协议边界](docs/architecture.md)
- [HTTP、WebSocket 与电机协议](docs/interfaces.md)
- [视觉跟踪算法](docs/tracking.md)
- [电机接线与执行器](docs/hardware-and-actuators.md)
- [Beni、幻尔与陆吾](docs/domestic-options.md)
- [强化学习与 Sim-to-Real](docs/reinforcement-learning.md)
- [开源小车参考分析](docs/upstream-analysis.md)
- [验证结果与已知限制](docs/validation.md)
- [问题清单与开发路线](docs/problem-log.md)
- [从零复现与验收步骤](docs/reproduction.md)
- [完整技术汇报 PPT](docs/presentations/M10_technical_overview.pptx)

## 当前实现与验证边界

| 模块 | 已有代码 / 证据 | 尚未完成 |
| --- | --- | --- |
| ESP32 电机 | M10 V2 二进制协议、CRC、ACK、300 ms 看门狗、到期停车和急停锁存；已有轮子动作记录 | 整机各方向复核、编码器速度闭环 |
| Linux 主控 | Python / FastAPI、真实设备探测、串口桥接、状态机、Web 控制台 | 与 Android 分支合并、统一正式电机协议 |
| 表情 | Android MediaPlayer 和 Web 播放器，10 组本地表情视频 | 与完整语音流程联动 |
| 视觉 | NMS、同类 IoU 关联、轨迹 ID、状态决策、Mac 仿真；RK3566 单帧 / 单图推理记录 | 常驻采集、板端连续跟踪与真实底盘联合闭环 |
| 语音 | 音频设备自检、流式音频 I/O 代码、设计方案 | ASR / LLM / TTS / AEC / 打断的端到端验收 |
| 强化学习 | Beni 公开策略分析与自身平台训练计划 | M10 专属模型、训练权重与实机部署 |

历史板端测量来自 2026 年 8 月记录，方案整理于 2026 年 11 月。不能把纯模型 FPS 当成整机跟踪速度，不能把串口 ACK 当成轮子真实运动证据。

### 三种证据要分开看

| 标记 | 在本仓库中的含义 | 例子 |
| --- | --- | --- |
| 有代码 / 主机通过 | 实现可以阅读，相关逻辑通过主机测试 | IoU 关联、CRC 编解码、表情状态切换 |
| 历史实机记录 | 特定硬件、系统和模型组合下有过测量 | UVC 取流、单帧推理、电机点动 |
| 待实现 / 待集成 | 接口、实验或工程路线已经设计 | 固定目标锁定、V2 统一适配、M10 专属 RL |

主机验证入口是 `scripts/check.sh`。初次公开版本的 [GitHub Actions](https://github.com/shichenghaoshu/M10/actions/runs/45834323263) 已通过；每次新提交的结果以 [Actions 页面](https://github.com/shichenghaoshu/M10/actions) 为准。

## 工程中真正需要解决什么

1. **把三个电机接口收敛为一个。** Linux 主控发送 `forward\n`，视觉 C++ 使用带 CRC 的文本帧，ESP32 正式候选使用 V2 二进制帧；目前不能直接混接。
2. **让跟踪对象持续保持同一目标。** 当前同类 IoU 关联适合建立基线，仍缺固定目标锁定、时间戳新鲜度门控和遮挡重捕获。
3. **降低采集到动作的总延迟。** Android 的单帧采集比模型推理更慢，先改常驻采集与最新帧队列，再评估模型优化。
4. **区分“收到命令”和“实际运动”。** 串口打开、ACK、目标 PWM、编码器轮速是不同层次的证据，当前尚未形成轮速闭环。
5. **把语音和动作接入统一状态管理。** 已有音频 I/O 与表情播放器，端到端 ASR / LLM / TTS、打断和运动仲裁还需集成。

详细原因、对应源码和验收条件见 [问题清单](docs/problem-log.md)。本次公开的是实现与问题本身，而不是把后续路线写成完成项。

## 目录

```text
m10-robot-core/      Linux 主控、硬件发现、状态机与 FastAPI
m10-hardware-test/   ESP32 固件、接线资料与主机测试
m10-vision/          C++ 视觉核心、Mac 仿真与 RKNN 验证脚本
m10-face-ui/         Web 全屏表情播放器
m10-face-android/    RK3566 Android 表情与单帧检测 APK
video/              Web 播放器使用的 10 组表情资源
cad/                既有 CAD 自动化脚本
docs/               技术总结、原始设计笔记与 PPT
scripts/            发布扫描和本机测试入口
m10_runtime/        一键启动、统一控制、V2 适配与媒体管理
profiles/           电脑、ESP32、Radxa 配置
third_party/        Dreamupers 原版源码快照与来源清单
```

## 快速验证

### 1. 本机测试（不连接电机）

需要 Python 3.9+、C++17 编译器、CMake 和 Ninja。先安装测试依赖，再执行统一检查：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r m10-robot-core/requirements.txt -r m10-face-ui/requirements-dev.txt
./scripts/check.sh
```

测试只验证主机逻辑，不会向真实底盘发运动指令。

### 2. Linux 主控

```bash
cd m10-robot-core
python3 main.py --check
python3 main.py
```

打开 `http://<device-ip>:8000`。缺少串口、摄像头或声卡时应返回 `unavailable` / `error`，不会伪造硬件正常。

### 3. Web 表情

在仓库根目录设置视频路径，然后运行服务：

```bash
export M10_FACE_VIDEO_DIR="$(pwd)/video"
cd m10-face-ui
uvicorn app:app --host 127.0.0.1 --port 8765
```

打开 `http://127.0.0.1:8765`。跨设备访问时按需更改监听地址，并配置 `M10_FACE_API_TOKEN`。

### 4. Android APK

见 [Android 构建说明](m10-face-android/README.md)。这是历史工程，使用 JDK 8、Gradle 4.10.3、AGP 3.1.2 和 TFLite 1.15.0，尚未迁移到新 Android 工具链。目标检测模型外置在设备上，仓库不携带模型权重。

### 5. ESP32 固件

正式候选代码在 `m10-hardware-test/esp32/m10_motor_controller/`。`motor_serial_test` 是旧文本协议接线草图，不能与正式 M10 V2 混用。优先阅读 [协议与固件说明](m10-hardware-test/docs/M10_MOTOR_FIRMWARE.md)。历史烧录脚本依赖本机先构建的固件镜像，预编译镜像不随源码发布。

## 模型与第三方代码

- RKNN 兼容资源通过 `m10-vision/scripts/prepare_models.sh` 从固定上游提交获取。
- YOLO / TFLite / RKNN 权重、Android SDK、Linux 镜像及厂商资料包没有提交到仓库。
- Dreamupers 小车、OpenBeni、幻尔和陆吾项目作为技术参考，不作为本项目原创代码发布。
- 原创代码与文档采用 [MIT](LICENSE)。保留的 Rockchip 代码、Gradle Wrapper 等遵循各自许可，见 [第三方说明](THIRD_PARTY_NOTICES.md)。

## 贡献

欢迎围绕连续采集、固定目标锁定、丢失停车、统一协议和测试复现提交改进。提交前运行 `./scripts/check.sh`，并在 PR 中注明主机测试还是实机测试。设备密钥、真实 Token、无线网络配置和原始调试日志不要提交。
