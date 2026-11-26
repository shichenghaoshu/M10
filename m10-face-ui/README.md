# M10 Face UI

独立于底盘与主控制程序的全屏表情播放器。它只负责三件事：接收服务器状态、把状态映射到 10 个视频、稳定地在屏幕上循环播放。

## 架构边界

```text
云端/局域网服务器 ── HTTP 推送或轮询 ──> M10 Face UI :8765 ──> 全屏浏览器
                                              │
                                              └── video/1.mp4 ... 10.mp4

底盘控制 / ESP32 / 摄像头 / 语音服务：不依赖、不导入、故障互不影响
```

正常显示页没有按钮或文字，只有黑底表情视频。调试时按 `D` 或 `` ` `` 打开状态面板；数字键 `1–9`、`0` 可切换 10 个表情，`F` 进入全屏。

## 快速运行

工程默认读取同级上层的 `video/`，因此在当前资料目录可直接启动：

```bash
cd m10-face-ui
chmod +x scripts/*.sh
./scripts/start.sh
```

访问：

```text
http://127.0.0.1:8765
```

调试面板：

```text
http://127.0.0.1:8765/?debug=1
```

运行测试：

```bash
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/pytest -q
```

## 服务器参数协议

### 方式 A：服务器主动推送（推荐）

```bash
curl -X POST http://<M10-IP>:8765/api/v1/state \
  -H 'Content-Type: application/json' \
  -d '{"state": 4}'
```

也可以使用状态名，并在指定时间后自动回到默认待机：

```bash
curl -X POST http://<M10-IP>:8765/api/v1/state \
  -H 'Content-Type: application/json' \
  -d '{"state":"listening","duration_ms":5000,"transition_ms":120}'
```

设置 `M10_FACE_API_TOKEN` 后，写接口需要请求头：

```text
Authorization: Bearer <token>
```

此时若要使用浏览器调试按钮，可打开 `/?debug=1&token=<token>`；普通全屏显示只订阅状态，不需要把 token 放进 URL。

### 方式 B：M10 主动轮询服务器

复制 `.env.example` 为 `.env`，设置：

```dotenv
M10_FACE_SERVER_URL=https://server.example.com/api/device/m10-001/face
M10_FACE_SERVER_TOKEN=your-token
M10_FACE_POLL_INTERVAL=1.0
M10_FACE_SERVER_TIMEOUT=15.0
```

服务端响应以下任一种形状均可：

```json
{"state": 3}
{"expression": "happy", "duration_ms": 3000}
{"data": {"mode": "thinking"}}
{"command": {"video": "10.mp4"}}
```

服务器持续不可达超过 `M10_FACE_SERVER_TIMEOUT` 时，播放器回到 1 号默认待机；页面与控制程序都不会退出。

### 状态表

| ID | key | 视频 | 含义 |
|---:|---|---|---|
| 1 | `idle_blink` | `1.mp4` | 默认待机·灵动眨眼 |
| 2 | `idle_breathe` | `2.mp4` | 极简待机·呼吸灯效果 |
| 3 | `happy` | `3.mp4` | 猫咪开心·撒娇表情 |
| 4 | `excited` | `4.mp4` | 超级兴奋·星星眼 |
| 5 | `playful` | `5.mp4` | 调皮眨眼·互动回应 |
| 6 | `sleep` | `6.mp4` | 睡眠模式·安静打呼 |
| 7 | `curious` | `7.mp4` | 好奇疑惑·探索状态 |
| 8 | `listening` | `8.mp4` | 聆听模式·声波响应 |
| 9 | `thinking` | `9.mp4` | 思考模式·三点循环 |
| 10 | `low_battery` | `10.mp4` | 低电量·委屈求充电 |

查看完整状态和当前状态：

```text
GET /api/v1/states
GET /api/v1/state
GET /health
```

显示页通过 `WS /ws` 实时收取切换事件。WebSocket 控制端也可以发送 `{"state": 5}`；配置 API token 时使用 `/ws?token=<token>`。

## RK3566 部署

推荐部署到 `/opt/m10-face-ui`，把 10 个视频放入 `/opt/m10-face-ui/video`，并将 `.env.example` 复制为 `.env`。后端 systemd 模板位于 `deploy/m10-face-ui.service`；桌面自动全屏模板位于 `deploy/m10-face-kiosk.desktop`。

```bash
sudo chown -R m10:m10 /opt/m10-face-ui
sudo -u m10 python3 -m venv /opt/m10-face-ui/.venv
sudo -u m10 /opt/m10-face-ui/.venv/bin/pip install -r /opt/m10-face-ui/requirements.txt

sudo cp deploy/m10-face-ui.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now m10-face-ui

mkdir -p ~/.config/autostart
cp deploy/m10-face-kiosk.desktop ~/.config/autostart/
```

模板默认以 Linux 用户 `m10` 运行；若设备用户名不同，只需修改 service 的 `User=`。播放器与主控制程序使用不同目录、进程和端口，可分别重启、升级和回滚。
