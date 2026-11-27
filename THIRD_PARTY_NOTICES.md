# 第三方来源与许可

根目录 MIT 许可适用于本项目原创部分，不改变第三方文件已有的许可。

| 来源 | 仓库中的使用方式 | 许可 / 说明 |
| --- | --- | --- |
| [Rockchip RKNPU2](https://github.com/airockchip/rknpu2/tree/1346f96) | `m10-vision/third_party/rknpu2-v1.0.0/` 中的头文件与 SSD 后处理代码 | Apache-2.0，保留该目录原始 LICENSE |
| [Gradle Wrapper](https://github.com/gradle/gradle) | `m10-face-android/gradlew*` 与 wrapper JAR | 原文件版权与 Apache-2.0 声明保留 |
| TensorFlow Lite、FastAPI、OpenCV、pyserial 等 | 运行依赖，由使用者安装 | 各依赖保持自身许可，不在根目录 MIT 下重新授权 |
| [Dreamupers/rk3566-ipc-car-public](https://github.com/Dreamupers/rk3566-ipc-car-public/tree/c6d6b428322cf0311b0059f7d5bdd287b4bf65a2) | `third_party/dreamupers/` 保存原版 11 个文本文件，运行器复用驱动、网页和媒体配置 | MIT，Copyright (c) 2026 Xi Zhang；原 LICENSE 与 rtsp/LICENSE 保留，PNG 不在快照中 |
| [MediaMTX](https://github.com/bluenviron/mediamtx) | Linux 图传首次按固定版本与 SHA-256 下载二进制，源码 / 二进制不纳入原创部分 | MIT；下载归档中的 LICENSE 保留在本机组件目录 |
| [hls.js](https://github.com/video-dev/hls.js/tree/v1.6.13)、[Tailwind CSS](https://tailwindcss.com/) | 浏览器 HLS 播放和 Dreamupers 原版样式的 CDN 依赖 | 保持各自 Apache-2.0 / MIT 许可；不作为本项目原创源码 |
| [Mondo-Robotics/open-beni](https://github.com/Mondo-Robotics/open-beni/tree/4545b86a131d05519050df11a424368ef9f06b4f) | 公开仿真、执行器与强化学习方案分析，未复制权重 | 上游 MIT；商业视觉跟随与公开运动策略分别对待 |
| [Hiwonder WonderDuck](https://github.com/Hiwonder/wonderduck)、[陆吾 XGO](https://www.xgorobot.com/) | 官方参数、平台选型与文档链接 | 不宣称获得其未公开硬件、商业固件或商标授权 |

模型二进制通过上游下载步骤获取，使用者应保留原始模型来源与许可。仓库没有包含开发机环境、系统镜像、设备私钥、厂家资料压缩包或无关项目源码。
