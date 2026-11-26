# HTTP、WebSocket 与电机协议

本页描述公开快照里的实际接口。除特别注明为“建议”的部分，其余均对应已有源码。各模块的接口相似不代表已经连接。

## 一、服务与端口

| 服务 | 默认端口 | 入口 | 当前边界 |
| --- | --- | --- | --- |
| Linux 主控 | 8000 | `m10-robot-core/main.py` | 设备状态与旧文本串口控制 |
| Web 表情 | 8765 | `m10-face-ui/app.py` | 表情 HTTP / WebSocket，不控制底盘 |
| Android 表情 / 单帧检测 | 8765 | `HttpControlServer.java` | 表情与一次性检测 / 决策 |
| 视觉主机联调 | 8080 | `m10-vision/web/server.py` | 独立开发服务，不能当作 Android 常驻推理服务 |

Web 与 Android 表情通常运行在不同设备或不同实验路线；不要在同一监听地址同时启动两个 8765 服务。

## 二、Linux 主控 HTTP

源码：[web_server.py](../m10-robot-core/web/web_server.py)、[command_dispatcher.py](../m10-robot-core/services/command_dispatcher.py)。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/status` | 整体状态 |
| GET | `/api/hardware` | 外设状态 |
| GET | `/api/esp32/status` | 串口桥状态 |
| POST | `/api/control/forward`、`backward`、`left`、`right` | 各路径分别发送对应文本运动命令 |
| POST | `/api/control/stop` | 尝试发送文本停止 |
| POST | `/api/control/status` | 请求下位机状态 |
| POST | `/api/video/snapshot` | 拍照 |
| POST | `/api/display/face/{face_name}` | Linux 显示服务切换表情 |
| POST | `/api/audio/test` | 音频自检 |
| POST | `/api/server/heartbeat` | 向配置的远端服务发送心跳，不是 V2 电机心跳 |

只读查询示例：

```bash
curl http://127.0.0.1:8000/api/status
curl http://127.0.0.1:8000/api/hardware
```

当前这些路由没有实现统一控制鉴权。配置中的 `server.token` 用于远端服务，不会自动保护本机 HTTP。接入共享网络前，应实现访问控制或限制监听范围；这也是现有实现的具体缺口。

## 三、表情接口

Web 与 Android 都支持 `GET /health`、`GET /api/v1/states`、`GET /api/v1/state`，以及 `POST|PUT /api/v1/state`；保留 `POST /api/state` 别名。

请求示例：

```json
{"state":"listening","duration_ms":5000,"transition_ms":120}
```

`duration_ms` 表示临时状态的持续时间；`0` 表示不设置定时恢复。`transition_ms` 是表情过渡参数，不是电机动作期限。

| ID | key | 视频 |
| --- | --- | --- |
| 1 | `idle_blink` | `1.mp4` |
| 2 | `idle_breathe` | `2.mp4` |
| 3 | `happy` | `3.mp4` |
| 4 | `excited` | `4.mp4` |
| 5 | `playful` | `5.mp4` |
| 6 | `sleep` | `6.mp4` |
| 7 | `curious` | `7.mp4` |
| 8 | `listening` | `8.mp4` |
| 9 | `thinking` | `9.mp4` |
| 10 | `low_battery` | `10.mp4` |

Web 的状态写入在配置 `M10_FACE_API_TOKEN` 时要求 `Authorization: Bearer ...`。`/ws` 建连后可接收状态；写入时校验查询参数 `token`，未授权连接只能读取。Android 当前 HTTP 实现没有等价的 Token 校验，响应头中出现 `Authorization` 字样不代表实现了鉴权。

## 四、Android 单帧检测与跟随建议

源码：[HttpControlServer.java](../m10-face-android/app/src/main/java/com/m10/faceui/HttpControlServer.java)。

| 方法与路径 | 输入 | 输出 / 行为 |
| --- | --- | --- |
| GET `/api/v1/detect/status` | 无 | `ready`、`model_loaded`、`camera_ok` |
| POST `/api/v1/detect` | `mode` 默认 `person`，`min_confidence` 默认 0.4 | 一次采集与检测，返回检测列表及 `capture_ms`、`inference_ms`、`total_ms` |
| POST `/api/v1/follow` | 当前不读取调参请求体 | 一次人员检测与离散动作建议，返回 `motor_command` |

```bash
curl -X POST http://127.0.0.1:8765/api/v1/detect \
  -H 'Content-Type: application/json' \
  -d '{"mode":"person","min_confidence":0.4}'
```

模型未就绪返回 503，采集失败返回错误。`camera_ok` 当前仅检查相机对象非空，不是实时帧到达保证。`follow` 的 `motor_command` 只是 JSON 字段，该处理函数没有完成串口发送，也没有维护跨请求 Track ID。客户端反复调用它仍不等于固定身份的连续跟踪。

## 五、三种电机协议为什么不能混用

| 使用位置 | 线上的内容 | 当前状态 |
| --- | --- | --- |
| Linux `ESP32Bridge` | `forward\n`、`stop\n` 等纯文本 | 早期接线接口 |
| 视觉 C++ | `M10,seq,motion,left,right,duration,CRC\n` | 文本 CRC 与 `ACK,seq,` 匹配，速度限幅为 ±100 |
| ESP32 正式候选 | 帧头 `AA 55` 的 V2 二进制 | 左右驱动目标为 ±1000，uint16 序号 |

适配不能仅替换串口路径。还要转换量纲和范围、实现握手与二进制 ACK、处理断线恢复，并把每个动作转换为明确的左右轮目标。视觉演示程序对所有非 STOP 动作传入相同的左右正值，不能直接拿它的轮值作为真实转向执行。

## 六、M10 Protocol V2 字节结构

以 [m10_protocol_core.h](../m10-hardware-test/esp32/m10_motor_controller/m10_protocol_core.h) 与 [.ino](../m10-hardware-test/esp32/m10_motor_controller/m10_motor_controller.ino) 为准。所有 16 位字段采用小端。

| 偏移 | 字节数 | 字段 |
| --- | --- | --- |
| 0 | 2 | 固定帧头 `AA 55` |
| 2 | 1 | version，当前为 2 |
| 3 | 1 | type |
| 4 | 2 | sequence |
| 6 | 2 | payloadLength，最大 256 |
| 8 | N | payload |
| 8+N | 2 | CRC16 |

总长度为 `10 + N`。CRC 使用 CCITT-FALSE：初值 `0xFFFF`，多项式 `0x1021`；覆盖 version 到 payload，即从偏移 2 开始的 `6+N` 字节。帧头和 CRC 本身不参与计算。

| type | 消息 | 固件处理 |
| --- | --- | --- |
| `0x01` / `0x02` | HELLO / HELLO_ACK | HELLO 会先停车、建立会话，回传两个能力字节 |
| `0x03` / `0x04` | HEARTBEAT / ACK | 已建立会话后刷新通信时刻；ACK payload 为被确认的 uint16 序号 |
| `0x10` | SET_MOTOR | payload 必须恰好 7 字节，受会话和急停锁存限制 |
| `0x11` | STOP | 停车；建立会话后确认 |
| `0x12` | EMERGENCY_STOP | 停车并锁存急停 |
| `0x13` | CLEAR_EMERGENCY_STOP | 会话有效时清除锁存，仍先停车 |
| `0x20` | TELEMETRY | 固件约每 200 ms 发送 |
| `0x22` | FAULT | 例如急停锁存时拒绝 SET_MOTOR |
| `0x40` / `0x41` | PING / PONG | 会话有效时回传 PING payload；不会刷新运动看门狗 |

头文件还枚举了配置与控制模式等消息，但 `.ino` 没有对应实现，不应因为存在枚举就宣称支持。

### SET_MOTOR payload

| payload 偏移 | 类型 | 含义 |
| --- | --- | --- |
| 0 | int16 | 左轮目标，限幅 ±1000 |
| 2 | int16 | 右轮目标，限幅 ±1000 |
| 4 | uint16 | durationMs |
| 6 | uint8 | 当前实现不读取，适配器应置 0，保留语义待统一 |

非零 duration 到期会停车；`durationMs=0` 表示不设置动作到期时刻，此时持续 HEARTBEAT 可以让最后的驱动目标继续保持。接入自动控制时建议每条运动命令都设置非零、受上限约束的期限，这一上限还需在固件和适配器中落实。

### 看门狗、重复指令与遥测

- 运动中若有效控制通信间隔严格大于 300 ms，循环执行停车。实际物理停车时延还包含循环调度与机械响应，不等于精确的 300 ms。
- 当前只记住**最近一次**执行命令的 type 与 sequence；紧接的重复命令只重发 ACK，不重新执行，也不刷新期限。这不是完整的滑动窗口去重，也不是跨会话重放防护。
- 遥测 payload 为 10 字节：左右**目标值**、电池占位 `0xFFFF`、角度占位 `0`、障碍占位 `0xFFFF`。没有编码器实测轮速，角度的 `0` 也不能当成实测水平。
- `STBY_PIN=-1` 时 `setStandby()` 不会操作 GPIO，当前靠 PWM / 方向脚置零停车；不能宣称软件已拉低现场外接的 STBY。

## 七、统一适配器的建议契约

以下为待实现设计：`connect → HELLO_ACK → active`；只有新鲜目标与有效控制模式可以生成非零目标。适配器统一序号、非零动作期限、ACK 超时、显式急停与重新握手；心跳周期应明显小于 300 ms 并保留调度余量。现有视觉 YAML 的 500 ms 心跳不能直接用于此固件。

建议对外暴露 `set_wheel_targets(left, right, duration_ms)`、`stop()`、`emergency_stop()`、`clear_emergency_stop()`、`get_link_status()`；这些函数名是设计建议，当前仓库没有统一实现。
