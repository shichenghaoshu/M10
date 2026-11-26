# 架构

正式数据流：Camera2/UVC 最新帧队列 → letterbox/RGA(OpenCV fallback) → RKNN detector → NMS → tracker → identity/pose/segmentation 调度 → BehaviorMachine → MotorDriver。紧急停止独立于推理队列。所有队列必须有界并丢弃过期帧。

模型调度：检测每 2 帧；Pose 仅锁定主人时每 5 帧；人脸仅新 person/周期复核；分割每 3–5 帧。当前已实现可单测的核心决策层，实时 Android Service 和多模型 RKNN 调度尚未完成。

