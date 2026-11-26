> 历史设计 / 调试笔记，不代表所有方案已实现。当前状态以仓库根 README 和 docs/validation.md 为准，文中设备地址与标识已替换。

# M10 智能小车实时视频流自动跟踪系统方案

> 基于现有 M10 项目（RK3566 + ESP32-S3）硬件和软件基础，设计完整的实时视频流自动跟踪闭环方案。

---

## 1. 系统概述

### 1.1 目标

构建一个人/宠物自动跟踪系统：车载 USB UVC 摄像头实时采集画面 → NPU 推理检测目标 → 跟踪器维持目标 ID → 行为状态机决策 → PID 控制差速底盘实时跟随。系统需支持远程 Web 监控与控制。

### 1.2 硬件基础（现有）

| 部件 | 型号 | 当前状态 |
|------|------|----------|
| 主控 | 立创·泰山派 RK3566 (Cortex-A55 ×4) | Android 11 userdebug, ADB root |
| NPU | Rockchip RKNPU 0.4.2 / Runtime 1.0.0 | 已验证稳定 |
| 下位机 | ESP32-S3 DevKitC-1 N16R8 | V2 固件已部署，8 方向验证通过 |
| 电机/底盘 | WHEELTEC R3X + TB6612FNG | 差速驱动，实机联调通过 |
| 摄像头 | USB UVC 32e6:9251 | 1280×720 MJPEG @ ~30fps 已验证 |
| 表情屏 | 原生 Android APK | 10 个表情动画，HTTP 控制接口 |

### 1.3 软件资产（现有可复用）

| 资产 | 路径 | 状态 |
|------|------|------|
| C++ 视觉库 | `m10-vision/native/common/m10_core.{hpp,cpp}` | NMS, IoU, SimpleTracker, BehaviorMachine (12 状态), GestureDebouncer 均已实现 |
| SSD Inception v2 | `m10-vision/models/` | NPU 推理 ~6.8 FPS, 147ms/帧 |
| M10 V2 电机协议 | `m10-hardware-test/esp32/m10_motor_controller/` | 二进制帧 AA 55, CRC16, SET_MOTOR ±1000 |
| UVC 推流代码 | `m10-uvc-streaming-plan.md` | CameraCapture / StreamEncoder / HlsServer 完整 Java 源码 |
| Web 控制接口 | `m10-robot-core/web/` | FastAPI REST API 模板 |
| 表情 APK | `m10-face-android/` | HTTP :8765 接口完整 |

---

## 2. 总体架构

```
+------------------------------------------------------------------+
|                     M10 Auto-Track 闭环                            |
|                                                                  |
|  +------------------+    +------------------+    +--------------+ |
|  | Layer 1          |    | Layer 2          |    | Layer 3      | |
|  | 视频采集与传输    | -> | 目标检测与跟踪    | -> | 运动控制     | |
|  |                  |    |                  |    |              | |
|  | USB UVC 摄像头   |    | NPU 推理引擎     |    | PID 控制器   | |
|  |   ↓              |    |   ↓              |    |   ↓          | |
|  | Camera2 API      |    | 检测后处理+NMS  |    | 速度/方向解算 | |
|  |   ↓              |    |   ↓              |    |   ↓          | |
|  | MediaCodec H.264 |    | SimpleTracker   |    | M10 V2 协议帧 | |
|  |   ↓              |    |   ↓              |    |   ↓          | |
|  | RTSP / WebRTC    |    | BehaviorMachine |    | ESP32 + TB6612| |
|  +------------------+    +------------------+    +--------------+ |
|           |                       |                      |        |
|           +--------- [协调层: ZMQ / Shm / 消息队列] -----+        |
|                              |                                    |
|                     +------------------+                          |
|                     | 安全守护         |                          |
|                     | 看门狗 + 急停    |                          |
|                     | 碰撞检测 + 限速  |                          |
|                     +------------------+                          |
+------------------------------------------------------------------+
```

### 2.1 数据流

```
摄像头 → YUV/NV12帧 ──┬──→ MediaCodec 编码 → RTSP/WebRTC → 远程监控/Web控制台
                      │
                      └──→ 缩放到 640×640 → NPU 推理(RKNN)
                              │
                              ▼
                      检测框 [cls, x1,y1,x2,y2, conf]
                              │
                              ▼
                      NMS 去重 → SimpleTracker(IoU匹配) 分配 track_id
                              │
                              ▼
                      BehaviorMachine 状态决策
                              │
                              ▼
                      目标位置 (cx, cy, depth_est) → PID 解算
                              │
                              ▼
                      左右轮速度 (L,R) → M10 V2 二进制帧 → ESP32
```

---

## 3. 各模块详细设计

### 3.1 视频采集与传输模块

#### 3.1.1 采集链路

```
方案 A（推荐 — 当前 Android 平台）:
  USB UVC 摄像头 → Android Camera2 API
    → ImageReader(YUV_420_888, 640×640, 2 buffer)
    → 一路送 NPU 推理（零拷贝 NV21 直接送入 RKNN）
    → 一路送 MediaCodec H.264 编码 → RTSP/WebRTC 推流

方案 B（未来 Linux 切换后）:
  USB UVC 摄像头 → V4L2 (/dev/video9)
    → MMAP 零拷贝采集 YUYV/MJPEG
    → FFmpeg + rkmpp 硬编码 H.264 → RTSP (rtsp-simple-server)
```

#### 3.1.2 推流协议选型

| 协议 | 延迟 | 复杂度 | 浏览器支持 | 推荐场景 |
|------|------|--------|------------|----------|
| **WebRTC** | 50-150ms | 高 | 原生支持 | 实时远程操控，低延迟要求 |
| **RTSP** | 100-300ms | 中 | 需插件/转码 | 局域网监控，与 NPU 同机处理 |
| HLS | 2-5s | 低 | 原生支持 | 仅观看回放，不适合跟踪控制 |

**推荐**: 第一阶段用 **RTSP**（局域网内监控 + 本地 NPU 推理共用同一帧源），第二阶段补充 **WebRTC** 用于手机端远程操控。

#### 3.1.3 帧管理策略

```
RingBuffer<Frame> (容量 = 8)
  - 采集线程写入，推理线程读取（单生产者单消费者，无锁）
  - 每帧携带 timestamp_us，推理完成后丢弃旧帧（drop-oldest）
  - 空闲时相机降帧到 5fps 省电，检测到运动后升到 30fps
```

#### 3.1.4 采集指标

| 参数 | 目标值 | 备注 |
|------|--------|------|
| 采集分辨率 | 640×640 | NPU 模型输入尺寸，无需额外缩放 |
| 推流分辨率 | 1280×720 | 远程监控画质 |
| 采集帧率 | 15-30 fps | 自适应：空闲 5fps → 跟踪 30fps |
| 编码格式 | H.264 Baseline | 低延迟优先 |
| 码率 | 1-2 Mbps | VBR，局域网内画质保障 |

---

### 3.2 目标检测与识别模块

#### 3.2.1 模型选型

当前 NPU Runtime 版本 **1.0.0** 是核心约束。需分两阶段：

**阶段一：SSD Inception v2（已部署，立即可用）**
- 检测类别：COCO 80 类（含 person, dog, cat）
- NPU 推理：~6.8 FPS，147ms/帧
- 优势：稳定，已验证
- 劣势：FPS 偏低，无宠物细分类

**阶段二：YOLOv5s / YOLOv8n INT8（需固件升级）**
- 目标：模型 Zoo ≥ 1.5 → NPU Runtime ≥ 1.6
- 推理速度：预期 15-30 FPS（640×640 INT8）
- mAP@0.5：≥ 0.45（COCO person/dog/cat）
- 优势：更快、更准、社区生态好
- 路线：升级 RK3566 Android 固件 → 更新 NPU 驱动到 0.6+ → Runtime 1.6+

| 指标 | 阶段一 (SSD v2) | 阶段二 (YOLOv5s) | 最终目标 |
|------|-----------------|-------------------|----------|
| 推理 FPS | 6-7 | 15-20 | ≥15 |
| 端到端延迟 | ~200ms | ~100ms | ≤150ms |
| 人物召回率 | ~70% | ~85% | ≥90% |
| 宠物召回率 | ~60% | ~80% | ≥85% |
| 误检率 (FP) | < 5% | < 3% | < 2% |

#### 3.2.2 多目标跟踪 (MOT)

复用已有的 `SimpleTracker`（IoU-based SORT 简化版）：

```
tracker = SimpleTracker(max_age=30, min_hits=3, iou_threshold=0.3)

每帧流程:
  1. 获取检测框列表 detections[{bbox, class_id, confidence}]
  2. tracker.update(detections) → tracks[{track_id, bbox, class_id, age, hits}]
  3. 选择跟踪目标:
     - 优先级: 已注册的家人/宠物 > 高置信度人 > 高置信度宠物
     - 选取视野中央最近的目标（避免边缘目标）
     - 目标切换需连续 5 帧确认，防止抖动
```

#### 3.2.3 身份重识别 (ReID)

家庭场景需要对特定人员/宠物建立身份：

```
方案: 轻量级 ReID embedding（MobileNetV3 backbone, 128-d 特征向量）
  - 注册: 用户通过 Web 界面框选目标，采集 10-20 张不同角度截图
  - 入库: 提取 embedding，存入本地向量库（numpy/faiss）
  - 匹配: 每帧对跟踪目标提取 embedding，cosine_similarity > 0.7 判定为已注册目标
  - 成本: embedding 提取可每 5-10 帧做一次（非每帧），使用 CPU 计算
```

#### 3.2.4 行为机 (BehaviorMachine)

已有 12 状态 FSM，自动跟踪场景下的核心状态转换：

```
                 ┌─────────┐
       启动 ───→ │  IDLE   │ ←─── 目标长时间丢失
                 └────┬────┘
                      │ 检测到目标
                      ▼
                 ┌─────────┐
                 │ SEARCH  │ 原地旋转 ±60°，搜索视野
                 └────┬────┘
                      │ 锁定目标
                      ▼
                 ┌─────────┐
          ┌────→ │  TRACK  │ 纯视觉跟踪，不移动
          │      └────┬────┘
          │           │ 目标距离 > 安全距离
          │           ▼
          │      ┌─────────┐
          └───── │ FOLLOW  │ PID 驱动底盘跟随
   目标重新出现   └────┬────┘
          ↑            │ 短暂遮挡(≤2s)
          │            ▼
          │      ┌─────────┐
          └───── │  LOST   │ 等待重识别，3s超时→SEARCH
                 └────┬────┘
                      │ 碰撞/急停指令
                      ▼
                 ┌──────────────┐
                 │ EMERGENCY_STOP│ 电机断电，需手动解除
                 └──────────────┘
```

---

### 3.3 运动控制模块

#### 3.3.1 PID 控制器设计

```python
class TrackingPID:
    """
    双通道 PID:
      - angular_pid: 根据目标在画面中的水平偏移 (cx_error) 控制角速度
      - linear_pid:  根据目标距离估计 (depth_est) 控制线速度
    """

    def __init__(self):
        # 角速度 PID (控制转弯)
        self.angular = PID(Kp=0.8, Ki=0.05, Kd=0.2, output_limit=(-500, 500))

        # 线速度 PID (控制前进/后退)
        self.linear = PID(Kp=1.0, Ki=0.1, Kd=0.3, output_limit=(-400, 600))

    def compute(self, target_cx, frame_center_x, depth_est, target_depth=1.5):
        # cx_error: 目标距画面中心的水平偏移（归一化到 [-1, 1]）
        cx_error = (target_cx - frame_center_x) / (frame_center_x)

        # depth_error: 目标距离期望距离的偏差
        depth_error = target_depth - depth_est

        angular_speed = self.angular.update(cx_error)
        linear_speed = self.linear.update(depth_error)

        # 差速分解
        left  = linear_speed - angular_speed
        right = linear_speed + angular_speed

        return clamp(left, -1000, 1000), clamp(right, -1000, 1000)
```

**距离估计策略**：
- **单目方案**: 利用目标检测框高度反推距离 `depth ≈ focal_length × real_height / bbox_height`
  - 人: 假设身高 1.7m，框高 → 距离
  - 宠物: 猫 0.25m / 狗 0.5m（类别预设）
- **未来升级**: 加装超声波/ToF 传感器做近距离精确测距

#### 3.3.2 运动控制策略

| 场景 | 线速度 | 角速度策略 | 备注 |
|------|--------|------------|------|
| 目标<0.5m | 0（停止） | 仅转弯保持朝向 | 安全距离，不前进 |
| 目标 0.5-1.5m | 慢速 100-300 | PID 微调 | 室内跟随即用 |
| 目标 1.5-3m | 中速 300-500 | PID 追踪 | 开间/走廊 |
| 目标 >3m | 快速 500-600 | 大角度转弯 | 空旷区域 |
| 目标丢失 <2s | 0 | 0 | 等待重识别 |
| 目标丢失 >3s | 0 | ±250 旋转搜索 | 原地转头找目标 |
| 急停触发 | 0 | 0 | 需手动解除 |

#### 3.3.3 下位机协议

使用已验证的 **M10 V2 二进制帧协议**：

```
帧格式: AA 55 [CMD] [SEQ] [PAYLOAD...] [CRC16-H] [CRC16-L]

SET_MOTOR: AA 55 03 [SEQ] [LEFT_H] [LEFT_L] [RIGHT_H] [RIGHT_L] [DUR_H] [DUR_L] [CRC16]
  - LEFT/RIGHT: int16, -1000..1000（PWM 占空比千分比）
  - DURATION: uint16 ms, 0=持续直到下一条指令
  - 300ms 通信看门狗自动停车

STOP: AA 55 04 [SEQ] [CRC16]          — 常规停车
EMERGENCY_STOP: AA 55 05 [SEQ] [CRC16] — 急停锁存
```

**指令发送频率**：每 100ms 发送一次 SET_MOTOR（10Hz），duration 设 200ms（允许丢 1 帧不断联）。

---

### 3.4 模块间通信协调机制

#### 3.4.1 进程架构

```
+----------------+     +------------------+     +-----------------+
| CameraService  |     | VisionEngine     |     | MotorController |
| (Java/NDK)     |     | (C++ NDK)        |     | (Java JNI)      |
|                |     |                  |     |                 |
| Camera2 API    | ──→ | Shm RingBuffer   | ──→ | M10 V2 Encoder  |
| MediaCodec     |     | NPU RKNN 推理    |     | Serial Bridge   |
| RTSP Server    |     | BehaviorMachine  |     | PID Controller  |
+----------------+     +------------------+     +-----------------+
         |                      |                        |
         +──────── [Unix Domain Socket / ZMQ PUB-SUB] ───+
                             |
                    +------------------+
                    | WebServer        |
                    | (Java/Netty)     |
                    | REST + WebSocket |
                    | :8080/:8081      |
                    +------------------+
```

#### 3.4.2 数据通道

| 通道 | 方向 | 数据 | 方式 | 频率 |
|------|------|------|------|------|
| 视频帧 | Camera → Vision | YUV/NV21, 640×640 | Shared Memory RingBuffer (8槽) | 15-30 Hz |
| 检测结果 | Vision → Motor | track_id, bbox, cx_error, depth | inproc ZMQ PUSH/PULL | 每帧 |
| 运动指令 | Motor → ESP32 | M10 V2 二进制帧 | USB Serial (FT232R) | 10 Hz |
| 遥测信息 | ESP32 → Motor | 电池、里程、障碍物 | UART RX Callback | 5 Hz |
| 监控帧 | Camera → WebServer | H.264 NAL units | RTSP / WebRTC | 15-30 fps |
| 状态上报 | Vision/Motor → Web | JSON (tracking state, speed) | WebSocket | 10 Hz |
| 控制指令 | Web → Vision/Motor | action (follow/stop/search) | REST POST | 按需 |

#### 3.4.3 同步与延迟管控

```
端到端延迟链路（目标）：

  相机曝光 + 读出:       ~15ms  (30fps 下 1/30s 的一半)
  Camera2 buffer 回调:   ~5ms
  NPU 推理 (YOLOv5s):    ~50ms (20fps)
  NMS + Tracker:         ~2ms
  BehaviorMachine:       ~1ms
  PID 解算:              ~1ms
  Serial 发送 (115200):  ~3ms  (SET_MOTOR ~16 bytes)
  ESP32 处理 + PWM:      ~5ms
  ─────────────────────────────────
  总计:                  ~82ms

  设计目标: ≤150ms（含 2 帧缓冲余量）
```

---

## 4. 精度与实时性指标

### 4.1 检测精度

| 指标 | 阶段一 (SSD v2) | 阶段二 (YOLOv5s) | 测试方法 |
|------|-----------------|-------------------|----------|
| mAP@0.5 (person) | ≥ 0.60 | ≥ 0.80 | COCO val2017 |
| mAP@0.5 (dog+cat) | ≥ 0.50 | ≥ 0.75 | 自建宠物数据集 |
| 召回率 Recall | ≥ 0.70 | ≥ 0.85 | 室内多场景 |
| 精确率 Precision | ≥ 0.80 | ≥ 0.90 | 误检率控制 |
| 跟踪 ID Switch | < 5% | < 2% | MOTA 评估 |
| 身份识别准确率 | — | ≥ 0.85 (Top-1) | 注册家人/宠物 |

### 4.2 实时性指标

| 指标 | 目标 | 当前 (SSD v2) | 最终 (YOLOv5s) |
|------|------|---------------|----------------|
| 检测帧率 | ≥15 fps | 6-7 fps | 15-20 fps |
| 检测延迟 (单帧) | ≤60ms | ~147ms | ~50ms |
| 端到端延迟 (采集→指令) | ≤150ms | ~200ms | ~80-100ms |
| 跟踪响应延迟 | ≤200ms | ~250ms | ~120ms |
| 视频推流延迟 (RTSP) | ≤300ms | — | ≤200ms |
| 控制指令周期 | 100ms (10Hz) | — | 100ms |

### 4.3 运动控制指标

| 指标 | 目标 |
|------|------|
| 稳态跟踪误差（方向） | ≤ ±5° 水平偏角 |
| 稳态跟踪误差（距离） | ≤ ±0.3m |
| 最大跟随速度 | 0.8 m/s |
| 最小安全距离 | 0.5m（自动停止） |
| 急停响应时间 | ≤ 100ms（从指令到轮子停止） |

---

## 5. 适用场景

### 5.1 室内（主要场景）

| 场景 | 描述 | 关键约束 |
|------|------|----------|
| 家庭客厅/走廊 | 跟随老人或小孩，辅助看护 | 光照充足、地面平整、窄通道 |
| 宠物互动 | 自动跟随猫/狗，保持安全距离 | 目标尺寸小、运动快、可能突然变向 |
| 办公/会议室 | 跟随演讲者移动拍摄 | 多人场景需锁定特定目标 |

**室内优势**：GPS 不可用场景下纯视觉方案最佳；地面平整 → 单目测距可用；Wi-Fi 覆盖 → 远程监控便利。

**室内挑战**：光照变化、玻璃/镜面反射、狭窄空间避障。

### 5.2 室外（扩展场景）

| 场景 | 描述 | 关键约束 |
|------|------|----------|
| 庭院/花园 | 跟随宠物在围栏内活动 | 地面不平、强光/阴影 |
| 小区人行道 | 陪同散步 | 行人干扰、需遵守交通规则 |

**室外限制**：
- 当前 M10 底盘为室内设计，无悬挂、无防水
- 单目视觉在强光下饱和、阴影中丢失目标
- 室外风/震动影响视觉稳定
- **建议**：将室外作为中长期目标，优先打通室内闭环

---

## 6. 可扩展性与稳定性

### 6.1 可扩展性设计

| 维度 | 设计决策 | 扩展路径 |
|------|----------|----------|
| **模型升级** | 模型加载器抽象为 `ModelEngine` 接口 | 热切换 YOLO/RT-DETR/MobileNet 系列 |
| **多传感器融合** | 传感器数据统一 `SensorFrame` 结构 | 加速计、陀螺仪、超声波、ToF 即插即用 |
| **多摄像头** | FrameRouter 按 source_id 路由 | 增加广角/深度/红外摄像头 |
| **SLAM 导航** | BehaviorMachine 预留 NAVIGATE 状态 | ORB-SLAM3 / VINS-Mono 集成点 |
| **云边协同** | 本地推理为主，云端可选增强 | 云端大模型做复杂场景理解，本地做低延迟控制 |
| **OTA 升级** | APK + 模型文件分离 | 模型远程下发，无需重装 App |

### 6.2 稳定性保障

```
分层保护策略:

[硬件层]
  - 独立急停物理按钮 → 直接切断 TB6612 STBY
  - 电池低压保护 → BMS 回传 → BehaviorMachine 自动回充
  - ESP32 看门狗 → 300ms 无指令自动停车

[通信层]
  - M10 V2 CRC16-CCITT 每帧校验
  - ESP32 StreamDecoder 容错：半包/粘包/噪声/CRC 错误恢复
  - 串口心跳 PING/PONG 1Hz，3 次超时触发 MOTOR_FAULT

[软件层]
  - 每个模块独立进程，崩溃不影响其他模块
  - VisionEngine 异常自动重启，恢复时间 < 2s
  - 帧超时监控：>500ms 无新帧 → 急停
  - 推理异常降级：NPU 故障 → 自动切到 CPU NCNN 备选推理（低帧率）

[行为层]
  - 速度上限硬编码: max_linear=600, max_angular=500
  - 急停后需手动解除（APP 确认）
  - 碰撞检测：加速度突变 > 3σ → 立即停车 + 后退 20cm
```

### 6.3 降级策略

| 故障 | 检测方式 | 降级行为 |
|------|----------|----------|
| 摄像头断连 | Camera2 onError | 停车 → Web 告警 → 自动重连 (5s 间隔) |
| NPU 推理超时 | 帧队列积压 > 5 帧 | 切到 CPU 推理 (NCNN, 降低分辨率) |
| ESP32 通信失败 | 3 次心跳超时 | 急停锁存 → 串口重连 |
| Wi-Fi 断开 | ConnectivityManager | 本地自主运行，缓存事件 |
| 电池 < 15% | 遥测阈值 | 停止跟踪 → 表情改 LOW_BATTERY → Web 告警 |

---

## 7. 实施路线图

```
Phase 1: 闭环打通 (2-3 周)
  ├── 1.1 CameraService NDK 化: Camera2 → NV21 帧 → Shm RingBuffer
  ├── 1.2 VisionEngine 接入: SSD v2 推理 + SimpleTracker + BehaviorMachine
  ├── 1.3 MotorController 串联: PID → M10 V2 → ESP32
  ├── 1.4 端到端验证: 室内固定目标跟随测试
  └── 1.5 Web 状态面板: WebSocket 实时状态推送

Phase 2: 性能提升 (2-3 周)
  ├── 2.1 NPU 固件升级: Runtime 0.4.2 → 1.6+, 部署 YOLOv5s
  ├── 2.2 PID 参数整定: 实机标定 angular/linear 三参数
  ├── 2.3 RTSP 推流集成: MediaCodec + rtsp-server 模块
  ├── 2.4 安全链路完善: 急停物理回路 + 碰撞检测
  └── 2.5 多目标优先级跟踪实测

Phase 3: 体验增强 (2-4 周)
  ├── 3.1 ReID 身份识别: MobileNetV3 embedding + 向量匹配
  ├── 3.2 WebRTC 低延迟推流（手机端远程操控）
  ├── 3.3 表情联动: BehaviorMachine 状态映射到 m10-face-android
  ├── 3.4 语音交互: 目标丢失时 TTS 播报 "XX 去哪了？"
  └── 3.5 室内 7×24 稳定性测试 + 异常场景覆盖

Phase 4: 扩展能力 (中长期)
  ├── 4.1 超声波/ToF 近距离测距融合
  ├── 4.2 室外庭院跟随（光照适应 + 地形应对）
  ├── 4.3 多摄像头广角 + 深度
  └── 4.4 OTA 升级体系
```

---

## 8. 关键风险与对策

| 风险 | 影响 | 概率 | 对策 |
|------|------|------|------|
| NPU Runtime 升级阻塞 | YOLOv5s 无法部署，FPS 上不去 | 中 | 备选：NCNN CPU 推理 + 降低分辨率到 416×416 |
| 单目测距误差大 | 跟随时距控制不准 | 高 | 加装超声波传感器（<2m 近距离），视觉框高做粗估计 |
| 室内光线不足 | 检测召回率暴跌 | 中 | 红外补光灯 + 低光照数据增强训练 |
| ESP32 串口丢帧 | 运动控制卡顿 | 低 | V2 协议已内建 CRC + 重传，100ms 周期可容忍 1 帧丢失 |
| 多人/多宠物场景 | 跟踪目标跳变 | 中 | ReID 身份锁定 + 5 帧确认切换策略 |
| 窄通道倒车困难 | 跟丢后无法转身 | 中 | SearchController 原地旋转已实现，增加后退避障逻辑 |

---

## 9. 附录

### A. 关键文件索引

| 文件 | 用途 |
|------|------|
| `m10-vision/native/common/m10_core.hpp` | SimpleTracker, BehaviorMachine, NMS 完整实现 |
| `m10-hardware-test/esp32/m10_motor_controller/m10_motor_controller.ino` | ESP32 V2 固件 |
| `m10-hardware-test/esp32/m10_motor_controller/m10_protocol_core.h` | 协议栈（帧编解码、CRC16、StreamDecoder） |
| `m10-uvc-streaming-plan.md` | UVC 推流完整 Java 代码 |
| `m10-vision/docs/final_summary.md` | 当前视觉验收状态 |
| `m10-hardware-test/docs/live_motor_debug_2026-08-05.md` | 电机实机连调记录 |

### B. 参考方案

- **SORT (Simple Online and Realtime Tracking)**: Bewley et al., 2016 — IoU 匹配基础算法
- **Deep SORT**: Wojke et al., 2017 — 加入外观特征做 ReID
- **RKNN Model Zoo**: https://github.com/airockchip/rknn_model_zoo — 官方模型部署参考
- **MediaPipe Objectron/Box Tracking**: Google — 轻量级跟踪备选方案

---

> **文档状态**: v1.0 Draft  
> **编制日期**: 2026-08-06  
> **适用范围**: M10 项目自动跟踪子系统设计  
