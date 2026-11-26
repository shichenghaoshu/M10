> 历史设计 / 调试笔记，不代表所有方案已实现。当前状态以仓库根 README 和 docs/validation.md 为准，文中设备地址与标识已替换。

# M10 — RK3566 泰山派 Android MIPI CSI 摄像头集成方案

## 1. 目标

将 MIPI CSI 摄像头模组接入立创·泰山派（RK3566），在 Android 11 上通过原生 Camera2 API + MediaCodec 实现硬件编码 HLS 视频推流，供 `m10-face-android` 统一管理。

---

## 2. 硬件层

### 2.1 RK3566 MIPI CSI 接口能力

来自 RK3566 Datasheet（`Rockchip_RK3566_Datasheet_V1.2-20220601.pdf`）：

| 特性 | 参数 |
|---|---|
| MIPI CSI 通道数 | 2 路独立 (CSI0 + CSI1) |
| 每通道 Lane 数 | 4-lane（可降为 2-lane） |
| 最大带宽 | 每 lane 2.5Gbps，单通道理论峰值 ~10Gbps |
| 支持分辨率 | up to 13MP (4224×3168) |
| DPHY 版本 | MIPI D-PHY v1.2 |
| 支持格式 | RAW8/10/12, YUV422 |

### 2.2 泰山派板载 CSI 接口物理形态

泰山派的 MIPI CSI 接口一般为 **15-pin FFC (FPC排线座)**，pin 间距 1.0mm，兼容树莓派摄像头排线标准。

典型脚序（以泰山派实际板载丝印为准）：

```
PIN | 信号          | 说明
----|--------------|------------------
 1  | GND          | 地
 2  | CSI_D0_N     | MIPI Data Lane 0 差分负
 3  | CSI_D0_P     | MIPI Data Lane 0 差分正
 4  | GND          | 地
 5  | CSI_D1_N     | MIPI Data Lane 1 差分负
 6  | CSI_D1_P     | MIPI Data Lane 1 差分正
 7  | GND          | 地
 8  | CSI_CLK_N    | MIPI Clock 差分负
 9  | CSI_CLK_P    | MIPI Clock 差分正
10  | GND          | 地
11  | CAM_I2C_SDA  | Sensor I2C 数据 (i2c3)
12  | CAM_I2C_SCL  | Sensor I2C 时钟 (i2c3)
13  | VCC_3V3      | Sensor 3.3V 供电
14  | VCC_1V8      | Sensor 1.8V 供电 (部分 sensor 需要)
15  | RST/PWDN     | Sensor 复位或掉电 (可配 GPIO)
```

### 2.3 推荐 Sensor 选型

| Sensor | 分辨率 | 输出格式 | MIPI Lane | I2C Addr | 红外夜视 | 价格(CNY) | 推荐度 |
|---|---|---|---|---|---|---|---|
| **OV5647** | 5MP (2592×1944) | RAW10 | 2-lane | 0x36 | ✅ IRCUT版可选 | ~25 | ⭐⭐⭐ 你已有 |
| OV5648 | 5MP | RAW10 | 2-lane | 0x36 | ❌ | ~30 | ⭐⭐ |
| **IMX219** | 8MP (3280×2464) | RAW10 | 2-lane | 0x10 | ❌ | ~35 | ⭐⭐⭐ 画质更好 |
| GC2053 | 2MP (1920×1080) | RAW10 | 2-lane | 0x37 | ✅ 星光级 | ~20 | ⭐⭐ 低照度好 |
| OV8858 | 8MP | RAW10 | 4-lane | 0x36 | ❌ | ~50 | ⭐ |

**建议**：
- 开发阶段优先用你已有的 **OV5647 红外夜视版**（`rk3566-ipc-car-public` 用的就是它）
- 量产或画质要求高换 **IMX219**
- 暗光环境运行（夜间巡逻车）换 **GC2053 星光级**

### 2.4 物理连接注意事项

- FFC 排线长度 ≤ 15cm，超过需要加信号中继
- 排线远离电机 PWM 线和电池大电流线（MIPI 差分信号敏感）
- 如果 CSI 接口和屏幕 MIPI DSI 共用同一个 FPC 连接器，需要确认是 CSI0 还是 CSI1
- 首次上电前用万用表蜂鸣档确认 VCC 到 GND 没有短路

---

## 3. 内核层

### 3.1 驱动架构

```
用户空间 (Android HAL)
────────────────────────────
内核空间
  drivers/media/platform/rockchip/cif/
  ├── cif_capture.c       # CIF 控制器驱动
  ├── mipi-csi2.c         # MIPI CSI-2 协议层
  └── dev.c               # /dev/videoX 设备节点
  drivers/media/i2c/
  └── ov5647.c            # Sensor 驱动 (V4L2 sub-device)
  drivers/i2c/
  └── i2c-rk3x.c          # I2C 控制器 (与 sensor 通信)
```

### 3.2 设备树 (DTS) 配置

在 kernel device tree 中配置 camera 节点。具体路径取决于 SDK 版本，通常在：

```
kernel/arch/arm64/boot/dts/rockchip/rk3566-tspi-camera.dtsi
```

#### 3.2.1 确认 I2C 总线

用 ADB 进去先看当前 I2C 设备：

```bash
adb shell
# 看 i2c 总线列表
ls /dev/i2c-*

# 扫描 sensor 地址（假设 CSI 挂在 i2c3 上）
# 如果系统有 i2c-tools:
i2cdetect -y 3
```

OV5647 的 I2C 地址是 `0x36`，如果扫到就说明物理连接正确。

#### 3.2.2 DTS 配置模板（OV5647, 2-lane, CSI0）

```dts
// rk3566-tspi-camera.dtsi
&i2c3 {
    status = "okay";
    clock-frequency = <400000>;

    ov5647: ov5647@36 {
        compatible = "ovti,ov5647";
        reg = <0x36>;
        clocks = <&cru CLK_CAM0_OUT>;
        clock-names = "xvclk";
        pinctrl-names = "default";
        pinctrl-0 = <&camerab_pins>;
        powerdown-gpios = <&gpio3 RK_PC1 GPIO_ACTIVE_HIGH>;
        reset-gpios = <&gpio3 RK_PC0 GPIO_ACTIVE_HIGH>;
        rotation = <180>;

        port {
            ov5647_out: endpoint {
                remote-endpoint = <&mipi_csi0_in>;
                data-lanes = <1 2>;
                clock-lanes = <0>;
                link-frequencies = /bits/ 64 <297000000>;
            };
        };
    };
};

&mipi_csi0 {
    status = "okay";

    ports {
        #address-cells = <1>;
        #size-cells = <0>;

        port@0 {
            reg = <0>;
            #address-cells = <1>;
            #size-cells = <0>;

            mipi_csi0_in: endpoint@1 {
                reg = <1>;
                remote-endpoint = <&ov5647_out>;
                data-lanes = <1 2>;
            };
        };

        port@1 {
            reg = <1>;
            #address-cells = <1>;
            #size-cells = <0>;

            mipi_csi0_out: endpoint@0 {
                reg = <0>;
                remote-endpoint = <&cif_in>;
            };
        };
    };
};

&rkcif {
    status = "okay";
    port {
        cif_in: endpoint {
            remote-endpoint = <&mipi_csi0_out>;
        };
    };
};

// GPIO pinctrl (根据泰山派实际 GPIO 调整)
&pinctrl {
    camerab_pins: camerab-pins {
        rockchip,pins =
            <3 RK_PC0 RK_FUNC_GPIO &pcfg_pull_none>,  // RST
            <3 RK_PC1 RK_FUNC_GPIO &pcfg_pull_none>;  // PWDN
    };
};
```

#### 3.2.3 关键变量说明

| 变量 | 含义 | 确定方法 |
|---|---|---|
| `i2c3` | sensor 挂载的 I2C 控制器 | 看泰山派原理图 / `i2cdetect` 扫 |
| `data-lanes = <1 2>` | 使用 lane 1 和 lane 2（2-lane 模式） | OV5647 只支持 2-lane |
| `clock-lanes = <0>` | lane 0 分配给时钟 | 固定 |
| `gpio3 RK_PC0` | Reset GPIO | 看原理图 sensor RST 脚连到哪个 GPIO |
| `gpio3 RK_PC1` | Powerdown GPIO | 看原理图 sensor PWDN 脚连到哪个 GPIO |
| `rotation = <180>` | 摄像头安装方向 | 实测调整 (0/90/180/270) |

**注意**：上面 GPIO 是示例，实际值必须对着泰山派原理图或 BOM 物料单确认。

### 3.3 内核配置 (defconfig)

确保以下内核选项开启：

```
CONFIG_MEDIA_SUPPORT=y
CONFIG_MEDIA_CAMERA_SUPPORT=y
CONFIG_V4L2_FLASH_LED_CLASS=y
CONFIG_VIDEO_OV5647=y            # OV5647 sensor 驱动
CONFIG_VIDEO_ROCKCHIP_CIF=y      # Rockchip CIF 控制器
CONFIG_ROCKCHIP_CIF=y
CONFIG_VIDEO_ROCKCHIP_MIPI_CSI2=y
CONFIG_ROCKCHIP_MIPI_CSI2=y
CONFIG_CAMERA_SENSOR=y           # Android camera sensor 支持
```

### 3.4 Camera HAL 层映射

Rockchip Android Camera HAL 的配置文件通常在：

```
hardware/rockchip/camera/CameraHal/CameraHal_board_config.xml
或
device/rockchip/rk356x/tspi/camera/camera_config.xml
```

关键配置项：

```xml
<BoardFile>
    <SensorList>
        <Sensor
            name="ov5647"
            drvName="ov5647"
            devName="ov5647_back"
            busType="MIPI"
            i2cBus="3"
            i2cAddr="0x36"
            mipiLaneNum="2"
            facing="back"
            orientation="0"
            mirror="false"
            resolution="2592x1944"
            fps="30"
            supportHdr="false"
        />
    </SensorList>
</BoardFile>
```

| 字段 | 值 | 说明 |
|---|---|---|
| `drvName` | 与 kernel sensor 驱动名一致 | HAL 据此匹配 `/dev/v4l-subdevX` 的 driver name |
| `devName` | 自由命名 | 生成 `/dev/videoX` 别名 |
| `facing` | `back` / `front` | 影响 Camera2 `LENS_FACING` 返回值 |
| `orientation` | 0/90/180/270 | 画面旋转角度 |
| `mirror` | true/false | 画面是否镜像 |

---

## 4. SDK 编译（使能 Camera）

### 4.1 编译步骤

```bash
# 1. 同步 Rockchip Android SDK (如未同步)
cd ~/rk3566_android11
repo init -u git://...
repo sync -j8

# 2. 确保 camera DTS 文件存在
ls kernel/arch/arm64/boot/dts/rockchip/rk3566-tspi-camera.dtsi

# 3. 确认 defconfig 包含 camera 驱动
grep -E "OV5647|ROCKCHIP_CIF|MIPI_CSI" kernel/arch/arm64/configs/rockchip_defconfig

# 4. 编译 kernel
source build/envsetup.sh
lunch tspi-userdebug   # 选择泰山派产品配置
./build.sh -K           # 只编 kernel

# 5. 编 Android HAL (camera 相关)
mmm hardware/rockchip/camera/

# 6. 全编（首次或 HAL 有大改）
./build.sh -A
```

### 4.2 只更新 kernel + dtb (快速迭代)

开发阶段如果只改了 DTS 或 sensor 驱动，不需要重新全编 Android 镜像：

```bash
# 单编 kernel
cd kernel
make ARCH=arm64 rockchip_defconfig
make ARCH=arm64 rk3566-tspi.img -j$(nproc)

# 烧录 kernel 和 dtb 分区
adb reboot bootloader
fastboot flash boot boot.img
fastboot flash dtbo dtbo.img     # 如果 DTS 放在 dtbo 分区
fastboot reboot
```

> **注意**：如果 camera DTS 改动放在 `dtbo` 叠加层，只需要刷 dtbo 分区。如果放在主 kernel DTS，需要重刷 `boot.img`。

---

## 5. 验证流程（逐层排查）

### 5.1 物理层验证

```bash
adb shell

# 1. MIPI CSI 控制器是否注册
ls /sys/class/video4linux/
# 期望看到 video0, video1 等

# 2. I2C 总线上有没有 sensor 应答
ls /dev/i2c-*
i2cdetect -y 3    # 如果系统没有 i2cdetect，跳到 dumpsys 步骤
# 期望在 0x36 位置看到 "UU" 或 "36"

# 3. DTS 是否正确加载
cat /sys/firmware/devicetree/base/i2c@.../ov5647@36/status
# 期望输出 "okay"
```

### 5.2 HAL 层验证

```bash
adb shell dumpsys media.camera
# 如果看到以下内容，说明 HAL 层已通：
#
# Camera module HAL API version: 2.4
# Camera 0 (back):
#   Device version: 3.5
#   Orientation: 90
#   ...
#   Static Metadata:
#     android.sensor.info.physicalSize: ...
#     android.scaler.streamConfigurationMap: ...
```

### 5.3 Camera2 API 验证

打开系统自带相机 App 测试：

```bash
# 从启动器打开相机，或者：
adb shell am start -a android.media.action.IMAGE_CAPTURE

# 查看 logcat 过滤 camera 相关日志
adb logcat -c && adb logcat -s CameraManagerService:* CameraDev:* CamX:*
```

或者直接调用 `m10-face-android` 的测试接口：

```bash
# 如果 m10-face-android 已有 camera 测试端点
curl http://<RK3566-IP>:8765/api/v1/camera/test
```

### 5.4 MediaCodec 硬编码验证

```bash
# 确认硬件 H.264 encoder 可用
adb shell dumpsys media.codec | grep -A 3 "video/avc"
# 期望看到：
#   Encoder "OMX.rk.video_encoder.avc"
#   Encoder "c2.rk.avc.encoder"
```

---

## 6. 应用层集成（m10-face-android）

### 6.1 新增模块结构

```
m10-face-android/app/src/main/java/com/m10/faceui/
├── camera/
│   ├── CameraManager.kt          # Camera2 封装：开/关/预览/参数
│   ├── StreamEncoder.kt          # MediaCodec 硬编码 → H.264 byte stream
│   └── HlsStreamServer.kt        # NanoHTTPD 子类，产出 HLS .m3u8 + .ts
├── server/
│   ├── HttpServer.kt             # 已有 :8765（扩展 streaming 端点）
│   └── routes/
│       ├── StreamRoutes.kt       # 新增: /api/v1/stream/start|stop|status
│       └── StateRoutes.kt        # 已有: /api/v1/state（不变）
├── ui/
│   └── MainActivity.kt           # 已有: 面部表情（不变）
└── service/
    └── StreamingService.kt       # Android Foreground Service，后台维持推流
```

### 6.2 Camera2 核心框架

```kotlin
// CameraManager.kt
class M10CameraManager(private val context: Context) {

    private val cameraManager =
        context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
    private var cameraDevice: CameraDevice? = null
    private var captureSession: CameraCaptureSession? = null

    fun openCamera(cameraId: String, surface: Surface) {
        cameraManager.openCamera(cameraId, object : CameraDevice.StateCallback() {
            override fun onOpened(device: CameraDevice) {
                cameraDevice = device
                createCaptureSession(surface)
            }
            override fun onDisconnected(device: CameraDevice) { device.close() }
            override fun onError(device: CameraDevice, error: Int) { device.close() }
        }, null)
    }

    // camera capture → Surface → MediaCodec input (零拷贝)
    private fun createCaptureSession(encoderSurface: Surface) {
        cameraDevice?.createCaptureSession(
            listOf(encoderSurface),
            object : CameraCaptureSession.StateCallback() {
                override fun onConfigured(session: CameraCaptureSession) {
                    captureSession = session
                    val request = cameraDevice!!.createCaptureRequest(
                        CameraDevice.TEMPLATE_RECORD
                    ).apply {
                        addTarget(encoderSurface)
                        set(CaptureRequest.CONTROL_AF_MODE,
                            CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO)
                    }
                    session.setRepeatingRequest(request.build(), null, null)
                }
                // onConfigureFailed: retry or error
            },
            null
        )
    }

    fun close() {
        captureSession?.close()
        cameraDevice?.close()
    }
}
```

### 6.3 MediaCodec 硬编码

```kotlin
// StreamEncoder.kt
class StreamEncoder(
    private val width: Int = 1920,
    private val height: Int = 1440,
    private val bitrate: Int = 1_000_000,  // 1 Mbps
    private val fps: Int = 30,
) {
    private val codec = MediaCodec.createEncoderByType("video/avc")
    private val surface: Surface

    init {
        val format = MediaFormat.createVideoFormat("video/avc", width, height).apply {
            setInteger(MediaFormat.KEY_BIT_RATE, bitrate)
            setInteger(MediaFormat.KEY_FRAME_RATE, fps)
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)   // 每秒一个 I 帧
            setInteger(MediaFormat.KEY_COLOR_FORMAT,
                MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface)
            setInteger(MediaFormat.KEY_BITRATE_MODE,
                MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR)
        }
        codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        surface = codec.createInputSurface()  // 相机直接喂到这个 Surface
        codec.start()
    }

    // 提供给 CameraManager 的 Surface
    fun getInputSurface(): Surface = surface

    // 线程中持续拉取编码后的 H.264 数据
    fun drainEncodedData(outputCallback: (ByteBuffer, MediaCodec.BufferInfo) -> Unit) {
        val bufferInfo = MediaCodec.BufferInfo()
        while (true) {
            val outputIndex = codec.dequeueOutputBuffer(bufferInfo, 10_000)
            when {
                outputIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                    // 可以在这里获取 SPS/PPS 写出到 HLS header
                    val newFormat = codec.outputFormat
                    // ...
                }
                outputIndex >= 0 -> {
                    val outputBuffer = codec.getOutputBuffer(outputIndex)!!
                    outputCallback(outputBuffer, bufferInfo)
                    codec.releaseOutputBuffer(outputIndex, false)
                }
                outputIndex == MediaCodec.INFO_TRY_AGAIN_LATER -> continue
            }
        }
    }

    fun release() {
        codec.stop()
        codec.release()
        surface.release()
    }
}
```

### 6.4 HLS 推流服务器

```kotlin
// HlsStreamServer.kt
// 基于 NanoHTTPD，输出 HLS 直播流
class HlsStreamServer(port: Int = 8888) : NanoHTTPD(port) {

    private var segmentId = 0
    private var m3u8Content = "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXT-X-VERSION:3\n"
    private val segments = mutableListOf<ByteArray>()
    private val maxSegments = 7  // 保留最近 7 个 segment

    // 每收到一个 H.264 NAL unit 包，判断是否切 segment
    fun onEncodedNal(nalData: ByteArray, isKeyFrame: Boolean, timestamp: Long) {
        // ... segment 切片逻辑 ...
        // 每 1 秒切一个 .ts 文件，更新 m3u8
        if (isKeyFrame && shouldStartNewSegment()) {
            startNewSegment()
        }
        addNalToCurrentSegment(nalData)
    }

    override fun serve(session: IHTTPSession): Response {
        return when (session.uri) {
            "/stream/index.m3u8" -> {
                newFixedLengthResponse(
                    Response.Status.OK,
                    "application/vnd.apple.mpegurl",
                    m3u8Content
                )
            }
            else -> {
                // 匹配 /stream/segment_N.ts
                serveSegment(session.uri)
            }
        }
    }
}
```

> **简化替代方案**：不用自己写 HLS 分段逻辑。使用 **[RootEncoder](https://github.com/pedroSG94/RootEncoder)** 库，内置了 Camera2 + MediaCodec + RTSP/RTMP 推流的完整实现，可以直接替代 6.2 ~ 6.4 三节。

### 6.5 推流生命周期管理

```kotlin
// StreamingService.kt
class StreamingService : Service() {
    // 受心跳驱动的按需推流（与 rk3566-ipc-car-public 逻辑一致）
    // - 收到 /api/v1/stream/start → 启动 camera + encoder + HLS server
    // - 客户端每 2s 发心跳 → 维持推流
    // - 5s 无心跳 → 关闭 camera + encoder，释放资源
    // - m10-face-android 的表情播放优先级高于 streaming（共享 GPU 资源时互斥）
}
```

### 6.6 新增 HTTP 端点

在已有 `:8765` HTTP Server 上加 3 个路由：

```
GET  /api/v1/stream/status
     → { status: "idle" | "streaming", bitrate: "1M", clients: 1 }

POST /api/v1/stream/start
     body: { cameraId: "0", bitrate: "2" }
     → { status: "ok", hls_url: "http://192.0.2.10:8888/stream/index.m3u8" }

POST /api/v1/stream/stop
     → { status: "ok" }
```

---

## 7. m10-robot-core (Python 端) 适配

`m10-robot-core` 如果运行在独立 Linux 板上，需要通过 HTTP 向 Android 端发推流控制指令：

```python
# services/streaming_service.py (新增)
import httpx

class StreamingService:
    def __init__(self, config, logger):
        self.android_addr = config.get("android_addr", "192.0.2.10:8765")
        self.logger = logger

    async def start(self, camera_id="0", bitrate=2):
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                f"http://{self.android_addr}/api/v1/stream/start",
                json={"cameraId": camera_id, "bitrate": bitrate},
                timeout=10,
            )
        return resp.json()

    async def stop(self):
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                f"http://{self.android_addr}/api/v1/stream/stop",
                timeout=10,
            )
        return resp.json()
```

---

## 8. 前端 (hls.js)

`web/templates/ws_index.html` 的视频播放部分从 `rk3566-ipc-car-public` 直接复用，零改动。

---

## 9. 故障排查速查表

| 现象 | 排查步骤 |
|---|---|
| `dumpsys media.camera` 无摄像头 | ① DTS 是否正确加载 ② I2C 是否扫到 sensor ③ HAL 的 camera_config.xml 是否正确 |
| I2C 扫不到 sensor (0x36 无应答) | ① FFC 排线接触不良 ② sensor 供电是否正常 (3.3V/1.8V) ③ RST GPIO 电平是否正确 |
| Camera2 能打开但无帧输出 | ① MIPI lane 配置是否与 sensor datasheet 匹配 ② CSI clock 频率是否正确 ③ 检查 `dmesg \| grep -E "cif\|mipi\|ov5647"` |
| MediaCodec 找不到编码器 | ① 确认系统镜像包含 OMX/C2 编码器 ② `dumpsys media.codec` 查看 encoder list |
| 编码帧花屏 | ① COLOR_FormatSurface 未正确传递 ② 分辨率不匹配 sensor 实际输出 ③ I 帧间隔过大 |
| 推流延迟 > 3s | ① hls.js `liveSyncDurationCount` 调小 ② HLS segment 从 2s 减到 500ms ③ 减小 `KEY_I_FRAME_INTERVAL` |

---

## 10. 实施步骤（推荐顺序）

| 阶段 | 任务 | 预计耗时 |
|---|---|---|
| **Phase 1 — 验证硬件** | ADB 进 RK3566，确认 I2C 扫到 sensor、kernel 驱动已加载 | 1h |
| **Phase 2 — 跑通 HAL** | 调用系统相机 App，确认能拍照/录像 | 1h |
| **Phase 3 — MediaCodec** | 写最小 Demo：Camera2 → Surface → MediaCodec → 存本地 .h264 文件 | 4h |
| **Phase 4 — HLS 推流** | 集成 RootEncoder 或自写 HlsStreamServer，浏览器能播 | 4h |
| **Phase 5 — 集成到 m10-face** | StreamingService 加入现有 APK，HTTP 端点扩展 | 2h |
| **Phase 6 — 对接 m10-robot-core** | Python 端通过 HTTP 命令控制推流启停 | 1h |
| **Phase 7 — 端到端测试** | 前端 hls.js 播放 + WebSocket 控制 + 面部表情同步 | 2h |

---

## 11. 兼容风险与降级策略

| 风险 | 概率 | 降级策略 |
|---|---|---|
| 泰山派 Android 镜像未预编 camera HAL | 中 | 用 USB UVC 摄像头先跑通全程，再回头调 CSI |
| Sensor FFC 排线干扰 | 中 | 加磁环、缩短排线、远离电机 PWM 线 |
| MediaCodec 硬编码器被系统占用 | 低 | 确认 `m10-face-android` 的 MediaPlayer 释放后再开 encoding |
| MIPI Lane 数配置错误 | 低 | 对照 sensor datasheet 确认 lane 数，不要猜 |

---

## 12. 参考文件（本工程内已有）

- `RK3566 Datasheet`: `【智能小手机】项目资料/5.屏幕选型与调试/瑞芯微数据手册/Rockchip_RK3566_Datasheet_V1.2-20220601.pdf`
- `Android 烧录配置`: `【智能小手机】项目资料/2.SDK编译/Android配置文件/全烧录/Android_All_Config.cfg`
- `Linux 版 CSI 驱动参考`: `【智能小手机】项目资料/7.手机综合项目/代码补丁/*`
- `rk3566-ipc-car-public FFmpeg 编码参考`: `rtsp/ffmpeg_cmd.json`
- `m10-face-android`: `m10-face-android/app/src/`（现有 APK 工程）
