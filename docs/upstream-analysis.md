# Dreamupers 开源小车分析

2026-11-27 更新：上游的 11 个原版文本文件已经固定保存到 `third_party/dreamupers/`，由新 `m10_runtime/` 复用。下面的历史迁移分析与新运行器集成状态分开阅读；启动方法与已接入功能见 [一键复刻指南](one-click.md)。

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

## 按源码拆解

| 上游文件 | 实际职责 | 迁移时需要改什么 |
| --- | --- | --- |
| [ws_main.py](https://github.com/Dreamupers/rk3566-ipc-car-public/blob/c6d6b428322cf0311b0059f7d5bdd287b4bf65a2/ws_main.py) | Flask 路由、WebSocket 动作、心跳、推流进程管理 | 拆开遥控、设备接口和媒体生命周期，配置路径与地址 |
| [motor.py](https://github.com/Dreamupers/rk3566-ipc-car-public/blob/c6d6b428322cf0311b0059f7d5bdd287b4bf65a2/motor.py) | gpiod 输出方向与 STBY，periphery 设置 PWM | 换成 ESP32 V2 适配器，不照搬 Radxa 引脚 |
| [vc.py](https://github.com/Dreamupers/rk3566-ipc-car-public/blob/c6d6b428322cf0311b0059f7d5bdd287b4bf65a2/vc.py) | 电压 / 电流相关外设访问 | 核对传感器型号、标定、设备总线和单位 |
| [mediamtx.yml](https://github.com/Dreamupers/rk3566-ipc-car-public/blob/c6d6b428322cf0311b0059f7d5bdd287b4bf65a2/rtsp/mediamtx.yml) | 媒体发布和预览协议 | 核对端口、发布权限、鉴权和缓存 |
| [README](https://github.com/Dreamupers/rk3566-ipc-car-public/blob/c6d6b428322cf0311b0059f7d5bdd287b4bf65a2/README.md) | 板卡、内核与 ffmpeg-rockchip 环境 | RK3566 相同不代表 BSP、相机和编码路径相同 |

WebSocket 处理器接受 JSON 的 `action`，调用 forward / backward / left / right / stop。它的 `status: ok` 表示处理函数完成，不包含编码器轮速、物理位移或 MCU ACK。未见控制请求的身份校验；MediaMTX 自带的鉴权配置不能自动保护另一个控制端口。

## 心跳保护的实际语义

源码默认心跳超时为 5 秒，后台约每 0.5 秒检查一次；仅在没有活跃客户端、服务处于 active 且过了启动宽限期时停止电机和流。WebSocket 断连另有停车路径。

因此它既不是“完全无保护”，也不是严格的“每个客户端一超时立即停车”。多个客户端同时在线时，需要另行设计谁拥有控制权、旁观客户端是否能维持活动状态，以及输入互相覆盖如何处理。

M10 计划把短动作期限和通信看门狗放在 ESP32，但还必须完成统一适配。300 ms 与 5 秒的差别是不同层次的时序设计，不能仅凭数字宣称整机可靠性已经提升。

## 为什么 HLS 预览不作为跟踪输入

编码、网络、分片和浏览器缓冲会使预览滞后；具体延迟需实测，不能仅根据协议名称给出固定毫秒值。机器人动作应消费本机最新帧；远端预览用于观察和调试。两者可共享采集来源，但不应让控制等待浏览器播放。

如果需要更低延迟遥操作，可以另做 WebRTC 等路线的评估；这不是当前默认配置已经实现的能力，且仍不能替代本机动作期限。

## 与 M10、Beni 的分工比较

| 维度 | Dreamupers 小车 | 当前 M10 快照 | OpenBeni 公开运动栈 |
| --- | --- | --- | --- |
| 核心价值 | RK3566 图传与网页遥控 | 感知、执行、界面与语音的验证模块 | 轮足运动仿真、训练和策略导出 |
| 运动接口 | Linux GPIO / PWM 直驱 | ESP32 V2 候选，适配尚未收敛 | 关节位置 / 轮速策略动作 |
| 视觉目标锁定 | 本次公开树未见 | 轻量基线，固定目标等待补齐 | 运动配置不等于视觉身份跟随 |
| 最值得参考 | 媒体进程与遥控组织 | 模块边界与可测试的核心 | 执行器建模、域随机化和部署契约 |

当前新运行器已提供媒体进程管理、可配置后端、动作租期与控制权、V2 适配及对应主机测试，并复用上游原版驱动与页面。原版 PNG 未复制，硬件路线尚待实机验收；原作者未公开的硬件设计不属于本次开源内容。
