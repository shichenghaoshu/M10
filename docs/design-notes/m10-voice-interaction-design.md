> 历史设计 / 调试笔记，不代表所有方案已实现。当前状态以仓库根 README 和 docs/validation.md 为准，文中设备地址与标识已替换。

# M10 × RK3566 实时语音交互设计方案

> 目标：让 M10 机器人（RK3566 Ubuntu 端）具备"听得见、听得懂、会回答、可打断"的实时语音交互能力，并与现有 m10-robot-core（表情屏、ESP32 底盘、状态机）联动。
> 日期：2026-08-07 · 状态：设计草案 v1

---

## 1. 现状盘点

已有基础（m10-robot-core）：

- RK3566 Ubuntu 运行 Python 服务，FastAPI Web 控制台（:8000）
- `audio_service.py` 已能通过 `arecord -l` / `aplay -l` 检测声卡，并做 3 秒录放测试
- `display_service.py` 可输出表情（idle / happy / error），480×320 表情屏
- `state_machine.py` + `command_dispatcher.py` 已有机器人状态与指令分发框架
- ESP32 通过串口桥接（底盘/电机控制）

缺口：

- 无持续音频流采集（现在只是整段录放）
- 无唤醒词 / VAD / ASR / LLM / TTS 任一环节
- 无回声消除（AEC）——同机麦克风和扬声器，这是最大的硬件级风险

---

## 2. 总体架构

```
麦克风 ──▶ [1] 采集线程 (ALSA/sounddevice, 16kHz 单声道)
              │
              ▼
        [2] AEC + 降噪        ←── 扬声器参考信号（回采/软参考）
              │
              ▼
        [3] 唤醒词引擎 (常驻, 低功耗)  ── 未唤醒则丢弃
              │ 唤醒后
              ▼
        [4] VAD 端点检测 (流式) ── 判断"说完了"
              │
              ▼
        [5] 流式 ASR ──▶ 文本
              │
              ▼
        [6] 意图路由 ──┬─▶ 本地指令 ("前进/停下/转圈") ─▶ command_dispatcher ─▶ ESP32
                       └─▶ LLM 对话 (云端 API / 本地小模型)
                                  │
                                  ▼
                        [7] 流式 TTS ──▶ 扬声器播放 (可被 barge-in 打断)

联动：每个阶段向 state_machine 上报状态 → display_service 切换表情
      listening(听) / thinking(想) / speaking(说，嘴部动画)
```

**核心原则：全链路流式。** 不等整句识别完再送 LLM，不等整段 TTS 合成完再播放。这是"实时感"的来源。

---

## 3. 硬件层：先解决 AEC，否则后面全是空中楼阁

M10 是"喇叭和麦克风在同一个身体上"的设备。没有 AEC，机器人说话时麦克风听到的全是自己的声音，ASR 会自激、打断失效。

| 方案 | 说明 | 建议 |
|---|---|---|
| USB 麦克风阵列（ReSpeaker 2/4-Mic） | 自带硬件或配套 AEC 算法，即插即用 | **首选原型方案**，`arecord -l` 直接可见，和现有检测代码兼容 |
| 板载 I2S 麦 + 软 AEC | WebRTC AEC / SpeexDSP，需要扬声器回采参考信号 | 量产方向，调试周期长 |
| 静音法（说话时关采集） | 播放 TTS 时 mute 麦克风 | 兜底方案，但失去 barge-in 能力，不推荐作为终态 |

RK3566 的 CPU（4×A55）跑 WebRTC AEC 单通道实时毫无压力，瓶颈不在算力而在参考信号的对齐。

---

## 4. 软件栈选型（关键决策）

### 4.1 推荐：sherpa-onnx 一把梭（本地路线）

sherpa-onnx（k2-fsa 出品，Next-gen Kaldi）对 RK3566 这类 ARM A55 板子是当前最省心的选择：一个框架覆盖 VAD + 唤醒 + ASR + TTS，有官方 Python API，CPU 推理优化好，无需联网。

| 环节 | 推荐组件 | 备注 |
|---|---|---|
| 唤醒词 | openWakeWord 或 sherpa-onnx KWS | 常驻线程，CPU 占用 <10% |
| VAD | silero-vad (sherpa-onnx 内置) | 30ms 帧，判停 ~500ms 静音 |
| ASR | sherpa-onnx streaming Zipformer (中文 bilingual 模型) | 流式，边说边出字；模型 ~100MB，RK3566 上 RTF ≈ 0.3–0.5 |
| LLM | 云端 API（流式 SSE） | 本地跑可用模型不现实，对话质量优先走云端 |
| TTS | sherpa-onnx VITS（如 vits-zh-aishell3） | 本地合成，首音 ~300ms；追求音色可换云端流式 TTS |

### 4.2 备选：全云端管线

麦克风 → WebSocket 流式送云端 ASR → LLM → 云端 TTS 流式回传播放。

- 优点：识别率和音色最好，开发量小
- 缺点：断网即哑、持续流量费、隐私、延迟受网络影响（通常 1.5–3s）
- **结论：离线可用是机器人的底线，建议"本地 ASR/TTS 为主 + 云端 LLM"，云端 ASR/TTS 作为可选降级/升级开关**

### 4.3 不建议

- 在 RK3566 上本地跑 LLM：1–2B 模型在 A55 上速度不可用于实时对话，NPU 0.8 TOPS 且 RKNN 对 LLM 支持折腾成本极高
- 自己训 ASR：直接拿 sherpa-onnx 预训练模型

---

## 5. 实时性设计

### 延迟预算（目标：端到端 ≤ 1.5s）

| 阶段 | 预算 |
|---|---|
| VAD 判停（说完话到确认） | 400–600 ms |
| ASR 尾包补齐 | ~200 ms（流式下已大部分完成） |
| LLM 首 token（云端） | 300–600 ms |
| TTS 首音 + 起播 | 200–400 ms |

### Barge-in（打断）

机器人播放 TTS 时唤醒/VAD 线程保持运行（依赖 AEC 生效）。检测到有效人声能量超过阈值 → 立即停播、清空播放缓冲、回到 listening。没有这个，交互会像对讲机而不是对话。

### 线程模型

```
CaptureThread ──(queue)──▶ KwsVadThread ──(utterance)──▶ AsrThread ──(text)──▶ DialogThread ──(audio chunks)──▶ PlaybackThread
```

全部用 `queue.Queue` 解耦，环形缓冲保留最近 2 秒音频做预唤醒补偿。与现有 `audio_service.py` 的关系：把录放子进程换成 `sounddevice`/`pyaudio` 常驻流，`arecord -l` 检测逻辑保留做启动自检（延续 No Mock 原则）。

---

## 6. 与 m10-robot-core 的集成

新增 `services/voice_service.py`，作为独立服务挂进 `robot_core.py` 生命周期：

```
services/
  voice/
    voice_service.py      # 总管：启动/停止/状态上报
    audio_io.py           # 采集流 + 播放流（sounddevice）
    kws.py                # 唤醒词
    vad_asr.py            # sherpa-onnx 流式识别
    dialog.py             # 意图路由 + LLM 客户端
    tts.py                # sherpa-onnx VITS
    barge_in.py           # 打断控制
```

- **表情联动**：voice 状态 → `state_machine` → `display_service`：唤醒=开心、听=专注、想=思考、说=张嘴动画、错误=error
- **本地指令直通**：ASR 文本先过正则/关键词匹配（"前进/后退/停下/转个圈"），命中直接走 `command_dispatcher` → ESP32，**不过 LLM，延迟 <100ms**
- **API 面**：`POST /api/voice/start`、`POST /api/voice/stop`、`GET /api/voice/status`、`WS /api/voice/events`（推送 ASR 中间结果到 Web 控制台显示字幕）
- **config.yaml 新增 `voice:` 段**：模型路径、唤醒词文件、LLM endpoint、音量、barge-in 开关
- **No Mock 原则**：模型文件缺失 → `voice_model_not_found`；LLM 不可达 → 本地指令仍可用，对话回复诚实降级

---

## 7. 分阶段实施路线

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| P0 音频底座 | 换 sounddevice 常驻流；确认麦克风阵列 + AEC 生效 | 机器人播音乐时采集流里人声可分离 |
| P1 离线指令 | 唤醒词 + VAD + 本地 ASR + 本地指令控制底盘 | "小十小十，前进" → ESP32 执行，全程离线 |
| P2 云端对话 | 接入 LLM 流式 API + 本地 TTS | 连续 3 轮对话，端到端 ≤1.5s |
| P3 体验打磨 | barge-in、表情联动、Web 控制台字幕、音量/音色配置 | 说话可打断；表情与状态同步 |

---

## 8. 风险清单

1. **AEC 不达标** → 自激/误唤醒。缓解：P0 阶段先做专项验证，不行就降级为"播放时 mute"
2. **模型体积与内存**：ASR+TTS 模型约 300MB，注意板子 RAM；模型放 ext4 数据分区，加载用 mmap
3. **网络依赖**：LLM 断网 → 需有诚实的本地兜底话术（"我现在没联网，但我还可以听指令"）
4. **CPU 争抢**：ASR 线程与视觉（m10-vision RKNN 推理）同时跑时要绑核隔离（taskset），避免互相拖慢
5. **唤醒误触**：安静环境误唤醒率需实测，必要时双级确认（唤醒词 + 短时人声确认）

---

## 9. 第一步建议

本周可做的最小验证：插一个 ReSpeaker USB 阵列到 RK3566，`pip install sherpa-onnx sounddevice`，跑官方 streaming ASR demo。如果识别延迟和准确率达标，整个方案的本地底座就成立了，后面都是工程集成。
