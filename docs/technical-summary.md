# M10 技术方案总结

M10 的当前目标是验证一条可重复的机器人链路：外设采集、目标检测与关联、状态决策、运动执行、表情与语音联动。

## 技术选择

| 层级 | 已有选择 | 原因与边界 |
| --- | --- | --- |
| 主控 | RK3566，Android 11 实机与 Linux 工程并行 | 前者已有外设记录，后者便于 Python 服务与硬件接口开发，尚未统一 |
| 下位机 | ESP32-S3，Arduino C++ | 将运动期限、通信看门狗与急停放在独立控制器 |
| 电机 | TB6612、两驱差速、开环 PWM | 适合快速验证，编码器 PID 尚未完成 |
| 视觉 | Camera2 / UVC、TFLite、RKNN、C++ | 模型与固件兼容性优先于盲目更换模型 |
| 跟踪 | 同类 IoU 贪心关联、Track ID、丢失计数 | 轻量基线，遮挡、交叉和固定目标选择仍需改进 |
| 服务 | Python、FastAPI、HTTP / WebSocket、串口 | 将设备层、状态机和 Web API 分开 |
| 语音 | 流式音频 I/O 与云端对话方案 | AEC、打断与完整多轮对话还需要联合验证 |
| RL | MuJoCo / mjlab、PPO、ONNX / MNN 参考路线 | 训练与部署均为后续工作，不包含 M10 策略权重 |

## 目前最重要的问题

1. Android、Linux 与各模块的电机协议尚未收敛。
2. 单次 Camera2 打开与关闭使采集成为延迟大头。
3. 当前 RKNN Runtime / 驱动限制了可运行的模型版本。
4. 旧跟踪框的保留与动作授权没有完全隔离。
5. 单模块成功不能替代视觉、底盘和语音的整机稳定性验证。

## 后续顺序

先固定系统、接线和协议，再完成连续跟踪与停车，随后接入语音闭环。执行器替换和强化学习必须建立在可测量的反馈链路上。

相关材料：[跟踪](tracking.md)、[执行器](hardware-and-actuators.md)、[国产替代](domestic-options.md)、[RL](reinforcement-learning.md)、[验证记录](validation.md)、[PPT](presentations/M10_technical_overview.pptx)。
