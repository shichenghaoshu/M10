# M10 Face UI for RK3566 Android

这是面向当前 `rk3566_tspi`（Android 11、横屏 800×480）的独立全屏表情 APK。包名为 `com.m10.faceui`，不导入也不修改原控制程序。

## 功能

- 10 个 MP4 全部内置，离线可播
- 原生 `MediaPlayer` 硬件解码
- 双 `TextureView` 淡入淡出切换
- 固定横屏沉浸模式、隐藏状态栏/导航栏、屏幕常亮
- 视频按原比例居中，黑色背景不会裁掉眼睛
- 本机监听 `0.0.0.0:8765`
- 支持临时表情结束后自动恢复 1 号待机
- 收到开机广播时尝试自动进入表情界面

## 构建和安装

```bash
export JAVA_HOME=/path/to/jdk8
./gradlew assembleDebug

../platform-tools-mac/platform-tools/adb install -r app/build/outputs/apk/debug/app-debug.apk
../platform-tools-mac/platform-tools/adb shell am start -n com.m10.faceui/.MainActivity
```

## 服务器控制

设备接入 Wi-Fi 后，服务器可直接访问：

```bash
curl -X POST http://<RK3566-IP>:8765/api/v1/state \
  -H 'Content-Type: application/json' \
  -d '{"state":"excited"}'
```

临时显示 5 秒后回待机：

```bash
curl -X POST http://<RK3566-IP>:8765/api/v1/state \
  -H 'Content-Type: application/json' \
  -d '{"state":"listening","duration_ms":5000,"transition_ms":120}'
```

USB 调试阶段可使用 ADB 转发：

```bash
../platform-tools-mac/platform-tools/adb forward tcp:8765 tcp:8765
curl http://127.0.0.1:8765/health
```

接口：

- `GET /health`
- `GET /api/v1/state`
- `GET /api/v1/states`
- `POST|PUT /api/v1/state`

状态参数接受 `1` 到 `10`，或 `idle_blink`、`happy`、`excited`、`playful`、`sleep`、`curious`、`listening`、`thinking`、`low_battery`。
