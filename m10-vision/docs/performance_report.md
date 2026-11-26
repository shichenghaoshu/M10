# 性能报告

设备：RK3566 Android 11，RKNPU driver 0.4.2，RKNN Runtime/API 1.0.0，NPU devfreq 900 MHz。

## 已完成实测

- UVC：1280×720 MJPEG，1800 帧，约 29.9 FPS，连续约 60 秒，无取流失败。
- SSD Inception v2 INT8：官方 300×300 模型，真实 RGB 图片输入；20 次平均 145.566 ms，p50 145.461 ms，p95 148.271 ms，约 6.870 FPS。
- 类别结果：road 图 person 0.9766；cat 图 cat 0.9885；dog 图 dog 0.9199。

## 运行中/未完成

- 4000 次 NPU 连续运行完成，退出码 0：平均 146.859 ms，p50 146.670 ms，p95 148.297 ms，6.809 FPS；最终温度 69.4°C，最高观察约 72.2°C，无 NPU 错误或崩溃。
- 真实 UVC 单帧端到端烟雾链路成功：抓取 43,698 字节 MJPEG，转换 RGB 后连续 3 次 NPU 平均 146.982 ms；当前桌面画面检出 keyboard 0.6398。
- 端到端 Camera → decode/resize → NPU → tracker → overlay 尚未完成，因此不能报告端到端延迟、跟踪 FPS 或叠框 FPS。
- Pose/face/segmentation 模型不兼容当前 Runtime，未报告虚假 FPS。
