# 代码导读与模块实现

本文按公开源码解释实际行为。方案中的目标架构不代表所有模块已经互通。建议先读 [总览](technical-summary.md)，再按需要进入具体工程。

## 一、Linux 主控：设备发现、服务组织与控制台

入口是 [main.py](../m10-robot-core/main.py)：加载 YAML，构造 `RobotCore`，执行初始化；`--check` 输出设备检查后退出，否则启动 FastAPI。运行 `--check` 仍会进行真实外设探测，不能把它当作完全不访问设备的纯模拟。

| 文件 | 具体职责 | 阅读时关注 |
| --- | --- | --- |
| [robot_core.py](../m10-robot-core/services/robot_core.py) | 组织设备发现、服务实例和汇总状态 | 生命周期与状态刷新入口 |
| [hardware_discovery.py](../m10-robot-core/services/hardware_discovery.py) | 查找串口、相机、显示与音频设备 | 缺失和不可用状态如何返回 |
| [state_machine.py](../m10-robot-core/services/state_machine.py) | 记录运行状态、故障、电池与障碍信息 | 哪些信息会阻止运动 |
| [command_dispatcher.py](../m10-robot-core/services/command_dispatcher.py) | 检查运动条件后转交串口；分发截图、表情、音频操作 | 失败后尝试发送停止 |
| [esp32_bridge.py](../m10-robot-core/services/esp32_bridge.py) | 查找并打开串口，发送文本并收集响应 | 当前不是 V2 编解码器 |
| [web_server.py](../m10-robot-core/web/web_server.py) | 状态查询和人工控制 HTTP 接口 | 默认端口 8000 |
| [config.yaml](../m10-robot-core/config.yaml) | 外设候选路径、串口参数、服务地址 | 候选设备存在不等于型号已确认 |

`ESP32Bridge.connect()` 以成功打开串口为连接依据，没有完成 V2 能力握手。`send_command()` 写入后收集文本，即使最终没有响应行也可能返回 `ok: true`。因此该结果不能作为正式固件 ACK 或轮子动作证据。

状态机目前会阻止已知故障、串口未连接、已知极低电量和已知近距离障碍；电池与障碍处于 `unknown` 时没有自动加入阻塞项。后续若采用“观测未知即禁止自动移动”，需要在实际授权逻辑中实现，不能仅修改说明。

## 二、视觉核心：算法组件与演示程序

核心在 [m10_core.hpp](../m10-vision/native/common/m10_core.hpp) 和 [m10_core.cpp](../m10-vision/native/common/m10_core.cpp)。它们与模型推理、摄像头后端解耦，便于在没有 RK3566 的主机上验证。

| 组件 | 当前实现 | 边界 |
| --- | --- | --- |
| Letterbox / 框还原 | 等比缩放、填充、反变换和边界裁剪 | 调用方仍需提供正确的原图与模型尺寸 |
| INT8 反量化 | `(q - zero_point) * scale` | 量化参数来自对应张量，不能跨模型套用 |
| NMS | 按分数排序，同类别框重叠过大时抑制 | 不负责跨帧身份判断 |
| `SimpleTracker` | 同类别、最大 IoU 贪心关联，生成 ID | 无 Kalman 预测、全局分配和 ReID |
| `BehaviorMachine` | 根据健康标志、路径、分数、位置和面积返回离散动作 | 有旧轨迹与状态授权缺口，见问题清单 |
| `SearchController` | 左右交替的有限搜索步骤 | 不是地图导航，也不保证完整搜索覆盖 |
| `GestureDebouncer` | 用腕部 / 肩部关键点位置做规则分类，持续确认与冷却 | 没有在这里运行人体姿态模型 |
| `identity_match` | 比较传入特征的余弦相似度 | 没有在这里提取人脸特征或建立身份库 |
| `conservative_traversability` | 根据传入地面比例和障碍标志做保守判断 | 没有在这里计算语义分割、深度或障碍距离 |

[native/app/main.cpp](../m10-vision/native/app/main.cpp) 输入的是手写检测框，并调用 Mock 电机。它是算法连通演示，不是读取相机、执行模型、控制真实电机的生产主循环。[sim_tracker.py](../m10-vision/sim_tracker.py) 是另一个主机摄像头实验；其 Python 跟踪实现和 C++ 核心也需要保持一致。

`configs/default.yaml` 描述了预期参数，但上述 C++ 演示入口没有加载它。配置写了鉴权、超时或心跳，不表示每个执行路径都已执行这些规则。

## 三、ESP32 固件：执行命令与限制运动期限

正式候选目录为 [m10_motor_controller](../m10-hardware-test/esp32/m10_motor_controller/)。头文件完成帧编解码与流式解析，`.ino` 负责会话、指令处理、PWM 输出、看门狗和遥测。

处理路径是：串口字节 → 帧头 / 长度 / CRC 校验 → 版本与消息类型判断 → 会话和急停检查 → 左右目标限幅 → GPIO / PWM → ACK。独立循环检查通信超时和运动到期。

当前控制是开环。`-1000..1000` 是归一化驱动目标，并非 rpm、mm/s 或实测轮速。左轮反向通过 `LEFT_INVERTED` 修正，使上层使用统一符号；其他接线不能不经验证照搬。

详细帧结构、重复序号和遥测占位值见 [接口说明](interfaces.md)。原有 [固件说明](../m10-hardware-test/docs/M10_MOTOR_FIRMWARE.md) 含历史镜像与烧录流程，其中预编译镜像不随本仓库发布。

## 四、表情：两个独立实现

| 路线 | 播放与状态 | 已有控制入口 | 适用场景 |
| --- | --- | --- | --- |
| [Web](../m10-face-ui/app.py) | 浏览器视频、服务端状态、WebSocket 广播、限时恢复 | HTTP、WebSocket、可选服务轮询 | Linux / 开发主机上的独立界面实验 |
| [Android](../m10-face-android/README.md) | MediaPlayer、双 TextureView、10 个内置 MP4 | 设备 HTTP 服务，端口 8765 | 当前 Android RK3566 全屏表情 |

两个服务都采用 1 到 10 的状态编号，但并非同一个进程，也没有自动同步。相同机器上同时监听同一地址和 8765 端口会冲突。表情变成 `listening` 只说明界面切换，不能据此判断 ASR 已启动。

## 五、语音：目前停留在什么层次

[audio_io.py](../m10-robot-core/services/voice/audio_io.py) 包含设备枚举、采集回调、预唤醒环形缓存、PCM 播放和 WAV 保存。默认配置为 16 kHz、单声道、30 ms 音频块、2 秒预缓存；这些默认值可以通过传入配置改变。

尚待集成的完整流程是：音频采集 → VAD / 唤醒 → ASR → 对话 / 工具决策 → TTS → 播放。还需处理播放参考信号的回声消除、用户插话取消、旧 TTS 清理以及与电机任务的优先级。当前 `play_pcm()` 使用等待播放完成的路径，不能把它描述为已支持流式 TTS 打断。

## 六、修改入口

| 想推进的工作 | 先读哪里 | 完成后补什么证据 |
| --- | --- | --- |
| 固定同一个跟踪对象 | Tracker、仿真 `_select_target`、BehaviorMachine | 多目标录像、ID 切换与错误重捕获统计 |
| 接真实底盘 | 三种协议实现与正式固件 | 字节级样例、ACK、断线停车与轮向视频 |
| 降低感知延迟 | Android CameraInference、HTTP 单帧检测 | 分阶段时间戳和 p50 / p95 延迟 |
| 增加身份确认 | 特征比较入口、实际特征提取模块 | 阈值来源、误识率和隐私处理说明 |
| 接多轮语音 | AudioIO、表情服务、指令仲裁设计 | 首包时延、插话取消、网络断连实验 |
| 开始 RL | 执行器测量、仿真拓扑、训练配置 | 训练种子、模型哈希、基线比较和部署契约 |

开发顺序与验收要求见 [问题清单](problem-log.md)，运行命令见 [复现指南](reproduction.md)。
