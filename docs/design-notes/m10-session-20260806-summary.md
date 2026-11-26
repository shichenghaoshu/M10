> 历史设计 / 调试笔记，不代表所有方案已实现。当前状态以仓库根 README 和 docs/validation.md 为准，文中设备地址与标识已替换。

# M10 项目 — 2026-08-06 调试记录

## 概述

在 RK3566（立创泰山派）Android 11 设备上完成了 USB UVC 摄像头接入、TFLite 人体检测模型的本地推理、HTTP API 扩展，以及跟随控制决策逻辑的端到端联调。

---

## 设备环境

| 项目 | 详情 |
|---|---|
| 设备型号 | `rk3566_tspi` (立创泰山派 V10) |
| Android 版本 | 11 (SDK 30) |
| 连接方式 | ADB USB (`DEVICE_IDENTIFIER`) |
| 已安装应用 | `com.m10.faceui` (面部表情) + `com.example.android.BluetoothChat` (M10 机器人主控) |

---

## 完成事项

### 1. USB 摄像头验证

- USB UVC 摄像头（VID:32e6 PID:9251）**免驱即插即用**
- Android External Camera HAL 自动识别为设备 ID 109
- 支持 640×480 / 800×600 / 1280×720 / 1920×1080，全部 @30fps
- MIPI CSI 摄像头未配置（legacy HAL: 0 devices），确认不可用

### 2. ESP32 串口调试

- FTDI 转接板（0403:6001）不被内核支持（缺 `ftdi_sio` 驱动）
- 切换到 ESP32-S3 原生 USB CDC ACM → `/dev/ttyACM0` 正常识别
- SELinux 阻止普通用户访问 → `adb root` 解决
- 确认蓝牙通信是更优的长远方案（RK3566 蓝牙已开启，地址 `DEVICE_IDENTIFIER`，M10 主控 App 已有 BluetoothChat 代码）

### 3. m10-face-android 改造

#### 3.1 构建系统修复

| 问题 | 解决方案 |
|---|---|
| Gradle 4.4.1 不兼容 JDK 11/17/25 | 升级 Gradle 4.10.3 |
| jcenter 停运导致依赖下载卡死 | 移除 jcenter，仅保留 google() + mavenCentral() |
| `dl.google.com` DNS 劫持（解析到 192.0.2.10） | 添加阿里云 Maven 镜像 `maven.aliyun.com` |
| JDK 8 ARM64 不存在 | 下载 Intel JDK 8 (Temurin 8u502)，通过 Rosetta 2 运行 |

最终构建配置：
- Gradle 4.10.3 + AGP 3.1.2
- JDK 8 (Intel) via Rosetta
- TFLite 1.15.0（最后一个不依赖 AndroidX 的版本）
- 编译成功，APK 约 16MB

#### 3.2 新增文件

| 文件 | 功能 |
|---|---|
| `detect/TFLiteDetector.java` | SSD MobileNet V1 目标检测器。加载 `/data/local/tmp/detect.tflite` 模型，输入 300×300 uint8 RGB，输出检测框列表 |
| `detect/CameraInference.java` | Camera2 API 单帧采集器。打开摄像头 → 拍照 → JPEG→Bitmap → 关闭，每次按需调用 |

#### 3.3 修改文件

| 文件 | 改动 |
|---|---|
| `build.gradle` | 添加 TFLite 1.15.0 依赖、阿里云镜像、移除 jcenter |
| `gradle-wrapper.properties` | Gradle 4.4.1 → 4.10.3 |
| `AndroidManifest.xml` | 添加 `CAMERA` 权限 + `uses-feature` 声明 |
| `HttpControlServer.java` | 新增构造函数参数 Context；新增检测初始化/关闭方法；新增 4 个 API 路由 |
| `MainActivity.java` | 传递 Context 给 HttpControlServer；启动时异步加载检测模型 |

#### 3.4 新增 HTTP API

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/v1/detect/status` | GET | 查询检测器是否就绪 |
| `/api/v1/detect` | POST | 拍照 + 目标检测，返回检测框列表 |
| `/api/v1/follow` | POST | 拍照 + 人体检测 + 跟随控制决策，返回电机指令 |
| 原有端点 | — | `/health`, `/api/v1/state`, `/api/v1/states` 保持不变 |

### 4. TFLite 模型

- 模型：`coco_ssd_mobilenet_v1_1.0_quant_2018_06_29`（SSD MobileNet V1, uint8 量化）
- 大小：4MB
- 输入：`[1, 300, 300, 3]` uint8 RGB
- 输出：detection_boxes `[1,10,4]`, detection_classes `[1,10]`, detection_scores `[1,10]`, num_detections `[1]`
- 存放路径：`/data/local/tmp/detect.tflite`
- 推理耗时：**88ms**（RK3566 4×A55 CPU）

### 5. 跟随控制逻辑

`POST /api/v1/follow` 的决策规则：

| 条件 | 电机指令 |
|---|---|
| `area_ratio > 0.30`（人占画面 30%+） | `backward` — 太近，后退 |
| `area_ratio < 0.06`（人占画面 6%-） | `forward` — 太远，前进 |
| `target_cx < frameW × 0.35` | `left` — 人在左侧，左转 |
| `target_cx > frameW × 0.65` | `right` — 人在右侧，右转 |
| 人在中间且距离合适 | `stop` — 保持 |
| 未检测到人 | `stop` — 安全停车 |

---

## 端到端测试结果

```json
{
  "status": "ok",
  "capture_ms": 522,
  "inference_ms": 75,
  "detection": {
    "label": "person",
    "confidence": 0.367,
    "x": 401, "y": 47,
    "width": 232, "height": 425
  },
  "target_cx": 517,
  "target_cy": 259,
  "area_ratio": 0.321,
  "motor_command": "backward"
}
```

| 指标 | 数值 |
|---|---|
| 摄像头采集 | ~500-600ms |
| TFLite 推理 | ~75-90ms |
| 总延迟 | ~600-700ms |
| 检测置信度 | 35-57% |

---

## 数据流总览

```
USB UVC 摄像头
    │
    ▼
CameraInference (Camera2 API, JPEG 采集)
    │ Bitmap
    ▼
TFLiteDetector (SSD MobileNet V1, CPU 推理, 88ms)
    │ List<Detection>
    ▼
跟随控制决策 (if-else 区域法)
    │ motor_command: "forward" | "backward" | "left" | "right" | "stop"
    ▼
HTTP API :8765  ← 当前输出到这里
    │
    ▼ (待接入)
ESP32 蓝牙 SPP → TB6612 → 电机
```

---

## 待完成

| 优先级 | 任务 | 备注 |
|---|---|---|
| **P0** | ESP32 固件增加蓝牙 SPP server | 替代 USB 串口，无线通信 |
| **P0** | Android 端蓝牙 SPP 发送电机指令 | 复用 M10 主控 App 的 BluetoothChat 代码 |
| P1 | 优化采集延迟（常驻 camera session 替代每次 open/close） | 当前 500ms 采集可降到 ~50ms |
| P1 | 换 NPU 推理（`/vendor/lib64/librknnrt.so` 已就绪） | 当前 CPU 88ms → NPU 预期 <10ms |
| P2 | 前端 Web 控制台接入 hls.js 视频流 | 参考 `m10-uvc-streaming-plan.md` |

---

## 相关文档

- [m10-uvc-streaming-plan.md](m10-uvc-streaming-plan.md) — USB UVC 摄像头 HLS 推流方案
- [m10-mipi-camera-plan.md](m10-mipi-camera-plan.md) — MIPI CSI 摄像头集成方案（备用）
- `m10-face-android/app/build.gradle` — 当前可用构建配置
