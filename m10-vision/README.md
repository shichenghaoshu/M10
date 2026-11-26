# M10 Vision

这是与现有 M10/轮趣代码隔离的 RK3566 Android 视觉工程。安全原则：默认 Mock 电机、未知路径不前进、摄像头/NPU/通信失败立即 STOP、不得把人脸或完整视频上传云端。

## 当前真实状态

- RK3566 Android 11 已通过 ADB root 验证。
- USB UVC `/dev/video9` 已抓取真实 1280×720 帧，并完成 60 秒/1800 帧/约 29.9 FPS 测试。
- NPU 驱动 0.4.2、Runtime 1.0.0；官方同版 SSD 模型与 probe 已准备，待 Android NDK 构建后运行。
- 当前系统 Camera App 对 External ID 109 有空指针缺陷，不代表 UVC 失败。
- C++ 核心包含映射、NMS、反量化、跟踪、状态机、Mock 电机、CRC、手势去抖、身份阈值和保守可通行判断。

## 命令

```bash
./scripts/inspect_host.sh
./scripts/inspect_device.sh
./scripts/camera_test.sh 60
./scripts/prepare_models.sh
./scripts/build_host.sh
ANDROID_NDK_PATH=/path/to/ndk ./scripts/build_android.sh
./scripts/deploy.sh && ./scripts/run_npu_probe.sh
./scripts/camera_npu_smoke.sh
./scripts/run.sh
./scripts/stop.sh
```

网页默认 `http://<本机局域网IP>:8080/`；配对 token 仅在启动终端显示，并以 0600 权限保存在被 Git 忽略的 `data/access-token`，不会写入日志。真实部署前应把 Web 服务移到 RK3566 前台 Service，当前主机服务只用于受保护 API/状态机联调。
