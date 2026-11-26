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
