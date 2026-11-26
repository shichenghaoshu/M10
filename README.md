# M10 开源机器人验证平台

RK3566、ESP32-S3 与两驱差速底盘组成的家庭陪伴机器人实验项目。这里公开硬件验证代码、Linux 控制服务、Android / Web 表情播放器、视觉跟踪核心，以及执行器、国产替代和强化学习方案。

**这是多个独立验证模块的源码快照，整机连续跟随与语音闭环仍在开发。** Android 实机路线与 Linux 工程分别保留，避免把单模块测试写成整机完成。

## 从哪里开始

- [技术方案总览](docs/technical-summary.md)
- [系统架构与协议边界](docs/architecture.md)
- [视觉跟踪算法](docs/tracking.md)
- [电机接线与执行器](docs/hardware-and-actuators.md)
- [Beni、幻尔与陆吾](docs/domestic-options.md)
- [强化学习与 Sim-to-Real](docs/reinforcement-learning.md)
- [开源小车参考分析](docs/upstream-analysis.md)
- [验证结果与已知限制](docs/validation.md)
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
