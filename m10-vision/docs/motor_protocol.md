# M10 ESP32-S3 电机协议

默认只启用 Mock；在真实协议和轮子架空验证前不发送运动命令。

命令：`M10,<seq>,<command>,<left>,<right>,<duration_ms>,<CRC16-CCITT>\n`。
响应：`ACK,<seq>,<status>,<battery>,<CRC16-CCITT>\n`。

要求：序列号去重、300 ms ACK 超时、500 ms 心跳、动作最长 500 ms、断联/上电/解析错误自动停车。紧急停止不进入普通动作队列。当前 ESP32 固件协议尚未在本工程中确认，真实后端保持禁用。

