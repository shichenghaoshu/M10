# 当前执行摘要

系统类型：Android 11 userdebug / arm64-v8a  
RK3566 连接方式：USB ADB（root 可用）；局域网 Web  
摄像头类型：USB UVC 32e6:9251，Camera ID 109，`/dev/video9`  
NPU 驱动版本：0.4.2  
RKNN Runtime 版本：1.0.0  
使用的模型：官方 SSD Inception v2；YOLOv8n 因固件版本不兼容未冒险部署  
模型量化方式：INT8 affine  
检测 FPS：短测 6.870；4000 次稳定性 6.809  
端到端延迟：完整实时循环未完成；单帧 UVC→RGB 后纯 NPU 约 147 ms  
Pose FPS：未运行（模型版本阻塞）  
分割 FPS：未运行（模型版本阻塞）  
主人识别结果：阈值/本地数据接口已实现，RKNN 人脸模型未部署  
手机访问地址：`http://192.0.2.10:8080/`（当前主机联调服务）  
启动命令：`./scripts/run.sh`  
停止命令：`./scripts/stop.sh`  
紧急停止方法：网页“紧急停止”或 `POST /api/action/emergency_stop`  
电机后端：Mock（真实 ESP32 协议未确认，保持安全禁用）  
已完成验收项：环境/NPU/摄像头识别、60 秒取流、NPU 单图检测 person/cat/dog、4000 次 NPU 稳定性、核心算法单测、Mock/串口安全接口、token Web API  
未完成验收项：常驻 Camera2 实时叠框与跟踪、YOLOv8、主人模型、Pose、语义分割、板端手机预览、真实 ESP32、30 分钟全系统联合稳定性  
实际阻塞问题：当前固件 Runtime 1.0.0/driver 0.4.2 与官方当前 Model Zoo >=1.5 不兼容；升级内核/固件属于有刷机风险的外部边界。  

