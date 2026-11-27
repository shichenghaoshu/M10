# 本次开源整理的主机验证

日期：2026-11-26。环境：macOS / AppleClang 17 / Python 3.9。

执行命令：

```bash
bash scripts/check.sh
```

| 检查 | 结果 |
| --- | --- |
| 发布源码扫描 | 通过，未发现扫描规则覆盖的私钥、真实 Token 或原作者主机路径 |
| Linux 主控 pytest | 13 passed |
| Web 表情 pytest | 13 passed |
| 串口主机脚本 pytest | 1 passed |
| 电机控制核心 C++ 程序 | 编译与执行通过 |
| M10 V2 协议 C++ 程序 | 编译与执行通过 |
| 视觉核心 CMake / CTest | 1/1 passed |

主控测试出现 urllib3 与本机 LibreSSL 版本的兼容性警告，未导致本次测试失败。建议部署时使用带受支持 OpenSSL 的 Python 环境。

本次没有连接真实底盘，没有刷写 ESP32，没有重新构建 Android APK，也没有运行摄像头、NPU、语音或 RL 实机测试。上表不能替代这些验收。

## 2026-11-27 一键运行器

在上述原有测试之外，新增 33 项 pytest 通过，总计 60 项 Python 用例。覆盖 V2 帧 / CRC / 分片 / ACK / 通信失败、动作期限、控制权、断连与急停、鉴权、表情服务、注入 GPIO 的原版驱动、媒体命令和下载校验。

本机通过 `m10.sh --no-install doctor`、真实 HTTP 服务与浏览器验证：控制台、Dreamupers 页面、模拟遥控、急停 / 解除和本地 MP4 表情切换。浏览器确认表情视频具有有效尺寸并处于播放状态。JavaScript 语法、Python 语法、修改文档的相对链接和发布扫描通过。

CI 另在干净虚拟环境执行首次安装，并下载固定版本 MediaMTX，验证生成配置能启动真实进程并响应 RTSP。对应提交的结果以 [Actions](https://github.com/shichenghaoshu/M10/actions) 为准。

没有新增真实底盘、INA226、V4L2 摄像头或硬件编码实测，也没有验证连续视觉跟随和 RL。本机测试没有执行实体非零运动。
