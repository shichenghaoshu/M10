# 从零复现与验收步骤

先选择纯主机测试、独立表情、设备探测、模型验证或真实底盘。它们不是一个命令即可全部完成的整机安装包。

## 1. 纯主机逻辑

需要 Python 3.9+、C++17 编译器、CMake 3.16+ 与 Ninja。macOS / Linux 有过主机验证，本次未验证 Windows 原生路径。

```bash
git clone https://github.com/shichenghaoshu/M10.git
cd M10
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r m10-robot-core/requirements.txt \
  -r m10-face-ui/requirements-dev.txt
# FastAPI TestClient 的干净环境依赖。
python -m pip install httpx
bash scripts/check.sh
```

检查不会发送真实电机运动指令，包括发布扫描、27 项 Python 测试、两项固件 C++ 测试程序与视觉 CTest。一个 C++ 程序内部含多个断言，不能把 CTest 程序数当作断言数。

初次公开版本的 [CI](https://github.com/shichenghaoshu/M10/actions/runs/45834323263) 已通过。依赖尚未完整锁定，复现异常时保存 Python 版本、`pip freeze` 与错误信息。

## 2. 视觉核心

```bash
cmake -S m10-vision -B /tmp/m10-vision-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/m10-vision-build
ctest --test-dir /tmp/m10-vision-build --output-on-failure
/tmp/m10-vision-build/m10_sim
```

演示使用手写框和 Mock 电机，不需要相机、RKNN 模型或真实串口。Python 摄像头实验另外需要 OpenCV / 检测依赖、摄像头权限和兼容权重；YOLO 权重不在仓库内。

## 3. Web 表情

在仓库根目录、激活虚拟环境后执行：

```bash
export M10_FACE_VIDEO_DIR="$(pwd)/video"
cd m10-face-ui
uvicorn app:app --host 127.0.0.1 --port 8765
```

另一终端测试：

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/api/v1/states
curl -X POST http://127.0.0.1:8765/api/v1/state \
  -H 'Content-Type: application/json' \
  -d '{"state":"thinking","duration_ms":3000}'
```

浏览器打开 `http://127.0.0.1:8765`，验证切换和超时恢复。配置 `M10_FACE_API_TOKEN` 后写入需携带 Bearer Token。若接口正常但画面不播放，检查 MP4 路径、浏览器媒体错误和自动播放设置。

## 4. Linux 主控

```bash
cd m10-robot-core
python main.py --check
python main.py --host 127.0.0.1 --port 8000
```

这些命令会探测真实设备并尝试打开候选串口。没有外设时 `unavailable` / `error` 是正常结果；返回 0 或启动摘要完成不代表全部硬件通过。先核对实际设备型号与路径，再调整 `config.yaml`。历史 Camera ID 109、`/dev/video9` 等不是通用硬件参数。

## 5. Android 表情与单次检测

历史工程使用 JDK 8、Gradle 4.10.3、AGP 3.1.2 与 TFLite 1.15.0。先准备 Android SDK、对应构建组件和 PATH 中的 `adb`。

```bash
cd m10-face-android
export JAVA_HOME=/path/to/jdk8
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.m10.faceui/.MainActivity
adb forward tcp:8765 tcp:8765
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/api/v1/detect/status
```

表情无需检测模型即可验证；检测需要额外准备兼容模型、权限和相机。`detection_not_ready` 时先核对这些条件。本次文档扩展没有重新构建 APK。

## 6. RKNN 兼容验证

先核对驱动、Runtime、转换版本、输入尺寸、数据格式、量化参数和后处理。现有兼容路线使用 SSD Inception v2，不能据此认定最新 YOLO 已在该 NPU 运行。

```bash
cd m10-vision
bash scripts/prepare_models.sh
```

脚本从固定提交取资源，并生成下载结果的 SHA-256 记录；生成校验值本身不等于使用独立已知值完成验证。再按 [模型说明](../m10-vision/models/README.md) 和 [部署说明](../m10-vision/docs/deployment.md) 构建 probe。先核对单图结果，再做多轮计时，最后接连续采集。

## 7. 真实底盘

先读 [固件与接线](../m10-hardware-test/docs/M10_MOTOR_FIRMWARE.md) 和 [接口](interfaces.md)。仓库未包含历史合并镜像，脚本里的旧镜像哈希不能直接用于刚编译的新镜像。

按顺序验收：逻辑供电与接线 → 无电机驱动的握手 / CRC / ACK → 架空急停与超时 → 低速短脉冲与轮向 → 地面低速 → 相机异常和目标丢失。保存命令、响应与真实动作。

Linux 文本桥与视觉 CRC 文本后端均不能直接对接 V2 正式固件；统一适配器完成前，HTTP 返回动作字符串不等于底盘闭环已建立。
