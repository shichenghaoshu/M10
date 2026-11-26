# M10 Vision 环境报告

生成时间：2026-08-05（Asia/Shanghai）。本报告来自真实命令，不含推测结果。

## 主机

- macOS 15.6.1，Darwin 24.6.0，Apple Silicon arm64。
- Python 3.14.0；Git 2.39.5；ADB 1.0.41 / 37.0.1。
- 初始缺少 CMake；已安装 CMake 4.4.2、Ninja 1.13.2 和 Android NDK r29。Docker CLI 存在，但 Docker daemon 未运行。
- 工作区根目录是尚无提交的 Git 仓库；已有多个独立工程，故新建 `m10-vision/`，不覆盖旧代码。

## RK3566

- ADB 序列号：`DEVICE_IDENTIFIER`，USB 连接正常。
- 系统：Android 11 / SDK 30 / userdebug；型号 `rk3566_tspi`。
- ABI：`arm64-v8a`；内核 `4.19.193`；设备树含 `rockchip,rk3566`。
- `adb root` 成功，root ADB 可用；`/data/local/tmp` 和 `/sdcard` 可写。
- 未验证 SSH；可用部署方式为 ADB push/exec 与局域网。

## NPU 与 RKNN

- NPU 设备树节点 `fde40000.npu` 状态 `okay`，绑定驱动 `RKNPU`，devfreq 当前 900 MHz。
- 内核模块版本：`0.4.2`。
- Runtime：`/vendor/lib64/librknnrt.so`，字符串版本 `1.0.0 (454a7218@2021-04-30T17:08:17)`。
- `/dev/rknpu*` 不存在；此版本通过已绑定的平台驱动/DRM 路径工作，必须用真实模型初始化进一步确认。
- 官方当前 model zoo >=1.5 与本机 1.0.0 不匹配。固定使用官方 `airockchip/rknpu2` 提交 `1346f96` 的 1.0.0 资产做初始 NPU 验证；不得替换板端 Runtime。

## 摄像头

- 类型：USB UVC，VID:PID `32e6:9251`，序列号 `202407231501043`。
- 视频节点：`/dev/video9`；`/dev/video10` 是 metadata capture。
- Android External Camera HAL：Camera ID `109`，HAL 3.4，Camera2 hardware level `EXTERNAL`，方向 90°。
- 格式：MJPEG 1920x1080/1280x720/800x600/640x480 @ 30 FPS；YUYV 640x480 @ 30 FPS、1280x720 @ 10 FPS。
- 单帧验证：1280x720 MJPEG，41,312 字节，SHA256 `812eab82919844c5ec958cadd286c5ff899c3f1027a22348e9d060d33e1cdcea`，成功解码且非黑帧。
- 连续验证：`v4l2-ctl` mmap 读取 1800 帧，约 29.9 FPS，约 60 秒，无取流失败。
- 系统 Camera2 App 存在缺陷：识别 ID 109 后内部 `cameraId=null`，在 `CaptureModule.openCameraAndStartPreview` 抛 NPE。底层 UVC 与 HAL 正常，项目必须使用独立 Camera2 或 V4L2 采集器。
