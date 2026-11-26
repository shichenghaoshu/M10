# Dreamupers 开源小车分析

分析版本：[c6d6b428](https://github.com/Dreamupers/rk3566-ipc-car-public/tree/c6d6b428322cf0311b0059f7d5bdd287b4bf65a2)。

## 已有链路

| 层级 | 实现 |
| --- | --- |
| 平台 | Radxa ZERO 3W / RK3566 + Linux，README 推荐 5.10 内核 |
| 控制 | Flask 9090 + WebSocket 8080，JSON 动作与 HTTP 心跳 |
| 电机 | gpiod + periphery PWM 直接控制 TB6612，开环 |
| 图传 | V4L2 + FFmpeg h264_rkmpp，RTSP 送入 MediaMTX |
| 预览 | HLS 8888 + hls.js，默认 WebRTC 关闭 |

## 复用边界

可复用遥控页面、图传组织方式、状态显示和电流计接口。公开树没有目标检测、跨帧关联或身份锁定模块，README 明确语音代码未实现。

WS 断连会停车，HTTP 客户端心跳默认 5 秒。因此不能写成完全没有断线保护，但它也不能替代独立 MCU 的每条动作期限。Linux 进程停止调度时，单靠该进程本身不能提供独立的停车兜底。

前端 IP、运行路径和设备节点固定，当前代码未见控制鉴权。同为 RK3566 仍须适配具体板卡、相机和硬件编码驱动。

## M10 的取舍

保留图传与预览，本机最新帧进入感知；以 M10 V2 / ESP32 替换 GPIO 直驱；统一手动 / AI 指令仲裁；把部署地址、设备路径和权限配置化。该迁移尚未完成。

上游于 2026-11-15 新增 MIT。公开文件树未含其完整原理图、PCB 或 BSP，本仓库不将这些未公开资料视为已获得的开源资产。
