> 历史设计 / 调试笔记，不代表所有方案已实现。当前状态以仓库根 README 和 docs/validation.md 为准，文中设备地址与标识已替换。

# M10 — USB UVC 免驱摄像头推流方案

## 1. 目标

USB 摄像头直接插 RK3566（泰山派）USB 口，在现有 `m10-face-android` APK 内集成 Camera2 + MediaCodec 硬编码 + HLS 推流，**不动内核、不重新编译 Android 镜像、不引入外部二进制**。

---

## 2. 为什么 UVC 在这个项目里比 MIPI 更合适

| 维度 | MIPI CSI | USB UVC |
|---|---|---|
| 物理连接 | FFC 15-pin 排线，靠近电机 PWM 线会受干扰 | USB-A 公头，随便插 |
| 内核改动 | 需要写 DTS + 确认 sensor 驱动 + 重编 kernel | 零改动（Android 9+ 内置 UVC 驱动） |
| HAL 配置 | Rockchip Camera HAL XML 配置，配错就看不到设备 | Android External Camera HAL 自动接管 |
| 验证方法 | 烧录 → 起不来 → 查 dmesg → 改 DTS → 重烧（循环） | 插上 → `adb shell dumpsys media.camera` → 有就有 |
| 你的 RK3566 上 Android 11 | HAL 是否编译了 camera 模块是未知数 | UVC 是内核主线驱动，Android 11 一定支持 |
| 摄像头坏了/想换 | 型号必须匹配 kernel 驱动 | 任意 UVC 摄像头拔了换一个就行 |
| 延迟 | ~30ms | ~60-80ms（WiFi 推流场景下可忽略） |
| 开发总耗时 | 2-5 天（可能会被一个 DTS 语法错误卡一天） | **0.5 天** |

---

## 3. 硬件准备

### 3.1 摄像头选型

任意 **USB UVC (USB Video Class)** 摄像头即可。推荐：

| 型号 | 最高分辨率 | 帧率 | 视场角 | 红外夜视 | 价格(CNY) | 备注 |
|---|---|---|---|---|---|---|
| **罗技 C270** | 720p | 30fps | 60° | ❌ | ~90 | 稳，很多机器人项目用 |
| 罗技 C920 | 1080p | 30fps | 78° | ❌ | ~350 | 画质好，自动对焦 |
| **淘宝 UVC 免驱 1080p** | 1920×1080 | 30fps | 70-110°可选 | ✅ 可选 IRCUT | ~40-80 | 性价比最高 |
| 树莓派 USB 摄像头 | 1920×1080 | 30fps | 70° | ❌ | ~60 | 体积小 |

> **推荐**：淘宝搜"USB 免驱摄像头 1080p IRCUT 夜视"，选 MJPEG + YUYV 双格式输出的。40 块钱就能用。

### 3.2 物理连接

```
USB 摄像头 ── USB-A 公头 ──→ RK3566 USB 2.0/3.0 Host 口
```

唯一注意：如果 RK3566 的 USB 口有限（泰山派通常 2-3 个），ESP32 又占用一个，可以考虑加一个 **USB Hub**。

---

## 4. 验证摄像头

### 4.1 插上即测

```bash
# 插上 USB 摄像头后
adb shell

# 1. 内核是否识别
ls /dev/video*
# 期望看到 /dev/video0 和 /dev/video1（一个 video capture，一个 metadata）

# 2. USB 设备枚举
lsusb
# 能看到摄像头的 USB VID:PID

# 3. UVC 驱动是否绑定
cat /sys/class/video4linux/video0/name
# 输出类似 "UVC Camera (046d:0825)" 就是 UVC 设备

# 4. 支持的格式
v4l2-ctl -d /dev/video0 --list-formats-ext
# 看支持哪些分辨率和帧率（没有 v4l2-ctl 也可以跳过这步）
```

### 4.2 Android 层验证（关键步骤）

```bash
adb shell dumpsys media.camera

# 关键信息：
# 如果看到类似下面的输出，说明 External Camera HAL 已接管：
#
# Camera 0 (back  or external):
#   Device version: 3.5
#   ...
#
# 如果输出为空或只有 "no camera", 说明 HAL 层没有认到，检查：
# ① 系统镜像的 external camera HAL 是否存在：
#    ls /system/lib64/hw/camera.external*.so
# ② SELinux 是否阻止了 camera service 访问 /dev/video0:
#    adb logcat | grep -i "avc.*denied.*video"
```

### 4.3 快速拍照测试

```bash
# 用系统相机 App 拍照（如果有）
adb shell am start -a android.media.action.IMAGE_CAPTURE

# 或者用 camera2 命令行工具（Android 11+ 部分设备有）
adb shell cmd media.camera list
```

---

## 5. m10-face-android 改造方案

### 5.1 新增文件清单

```
m10-face-android/app/src/main/java/com/m10/faceui/
├── MainActivity.java              # 不改
├── HttpControlServer.java         # 改：加 4 个 stream 路由
├── BootReceiver.java              # 不改
├── FaceLayer.java                 # 新：从 MainActivity 内部类提取（不影响功能）
└── stream/                        # 新目录
    ├── CameraCapture.java         # Camera2 API 封装
    ├── StreamEncoder.java         # MediaCodec H.264 硬编码
    └── HlsServer.java             # HLS m3u8 + .ts 分段 Serving
```

### 5.2 数据流

```
USB Camera                  m10-face-android APK
┌──────────┐    UVC        ┌─────────────────────────────────┐
│          │ USB Cable     │                                 │
│  任意UVC  ├──────────────►  CameraCapture                  │
│  摄像头   │   内核UVC驱动  │  (Camera2 API)                  │
│          │               │  输出: Surface                  │
└──────────┘               │       │                        │
                           │       ▼ (零拷贝, 同进程内)       │
                           │  StreamEncoder                  │
                           │  (MediaCodec video/avc)         │
                           │  输出: H.264 NAL units          │
                           │       │                        │
                           │       ▼                        │
                           │  HlsServer                      │
                           │  (手写 HTTP :8888)              │
                           │  → /stream/index.m3u8           │
                           │  → /stream/segment_0.ts ...     │
                           │                                 │
                           │  HttpControlServer :8765 (已有)  │
                           │  → /api/v1/stream/start          │
                           │  → /api/v1/stream/stop           │
                           │  → /api/v1/stream/status         │
                           └─────────────────────────────────┘
                                        │
                                        │ HTTP
                                        ▼
                                   浏览器 (hls.js)
                                   http://192.0.2.10:8888/stream/index.m3u8
```

### 5.3 CameraCapture.java

```java
package com.m10.faceui.stream;

import android.content.Context;
import android.graphics.SurfaceTexture;
import android.hardware.camera2.*;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Log;
import android.util.Size;
import android.view.Surface;

import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;

/**
 * 封装 Camera2 API 的 USB UVC 摄像头采集。
 * 输出为一个 Surface，MediaCodec 直接从这个 Surface 取帧（零拷贝路径）。
 */
public final class CameraCapture {
    private static final String TAG = "M10Camera";

    private final CameraManager cameraManager;
    private HandlerThread cameraThread;
    private Handler cameraHandler;
    private CameraDevice device;
    private CameraCaptureSession session;

    public CameraCapture(Context context) {
        cameraManager = (CameraManager) context.getSystemService(Context.CAMERA_SERVICE);
    }

    /**
     * 选择摄像头：优先 external (UVC)，其次 back (CSI)
     */
    public String selectCamera() throws CameraAccessException {
        for (String id : cameraManager.getCameraIdList()) {
            CameraCharacteristics chars = cameraManager.getCameraCharacteristics(id);
            Integer facing = chars.get(CameraCharacteristics.LENS_FACING);
            if (facing != null && facing == CameraCharacteristics.LENS_FACING_EXTERNAL) {
                Log.i(TAG, "Selected external/UVC camera: " + id);
                return id;
            }
        }
        // fallback: 拿第一个摄像头
        String fallback = cameraManager.getCameraIdList()[0];
        Log.i(TAG, "No external camera found, using " + fallback);
        return fallback;
    }

    /**
     * 选择最佳预览分辨率：优先 1080p@30fps
     */
    public Size chooseResolution(String cameraId, int targetWidth, int targetHeight)
            throws CameraAccessException {
        CameraCharacteristics chars = cameraManager.getCameraCharacteristics(cameraId);
        StreamConfigurationMap map = chars.get(
                CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
        if (map == null) {
            throw new IllegalStateException("No stream configuration map");
        }
        Size[] outputSizes = map.getOutputSizes(SurfaceTexture.class);
        // 选不大于目标尺寸的最大分辨率
        Size best = null;
        for (Size size : outputSizes) {
            if (size.getWidth() <= targetWidth && size.getHeight() <= targetHeight) {
                if (best == null || size.getWidth() > best.getWidth()) {
                    best = size;
                }
            }
        }
        return best != null ? best : outputSizes[0];
    }

    /**
     * 打开摄像头，编码 Surface 由 StreamEncoder 提供
     */
    public void open(String cameraId, Size resolution, Surface encoderSurface,
                     Runnable onReady, Runnable onError) {
        cameraThread = new HandlerThread("m10-camera");
        cameraThread.start();
        cameraHandler = new Handler(cameraThread.getLooper());

        try {
            cameraManager.openCamera(cameraId, new CameraDevice.StateCallback() {
                @Override
                public void onOpened(CameraDevice d) {
                    device = d;
                    startPreview(resolution, encoderSurface, onReady, onError);
                }
                @Override
                public void onDisconnected(CameraDevice d) {
                    d.close();
                    device = null;
                }
                @Override
                public void onError(CameraDevice d, int error) {
                    Log.e(TAG, "Camera error: " + error);
                    d.close();
                    device = null;
                    if (onError != null) {
                        onError.run();
                    }
                }
            }, cameraHandler);
        } catch (CameraAccessException | SecurityException e) {
            Log.e(TAG, "Failed to open camera", e);
            if (onError != null) {
                onError.run();
            }
        }
    }

    private void startPreview(Size resolution, Surface encoderSurface,
                              Runnable onReady, Runnable onError) {
        try {
            // 不需要预览 Surface，只把帧喂给 MediaCodec
            device.createCaptureSession(
                    Collections.singletonList(encoderSurface),
                    new CameraCaptureSession.StateCallback() {
                        @Override
                        public void onConfigured(CameraCaptureSession s) {
                            session = s;
                            try {
                                CaptureRequest.Builder builder = device.createCaptureRequest(
                                        CameraDevice.TEMPLATE_RECORD);
                                builder.addTarget(encoderSurface);
                                builder.set(CaptureRequest.CONTROL_AF_MODE,
                                        CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO);
                                builder.set(CaptureRequest.CONTROL_AE_MODE,
                                        CaptureRequest.CONTROL_AE_MODE_ON);
                                session.setRepeatingRequest(builder.build(), null, cameraHandler);
                                Log.i(TAG, "Camera preview started at " +
                                        resolution.getWidth() + "x" + resolution.getHeight());
                                if (onReady != null) {
                                    onReady.run();
                                }
                            } catch (CameraAccessException e) {
                                Log.e(TAG, "Failed to start preview", e);
                                if (onError != null) {
                                    onError.run();
                                }
                            }
                        }
                        @Override
                        public void onConfigureFailed(CameraCaptureSession s) {
                            Log.e(TAG, "Capture session configuration failed");
                            if (onError != null) {
                                onError.run();
                            }
                        }
                    },
                    cameraHandler
            );
        } catch (CameraAccessException e) {
            Log.e(TAG, "Failed to create capture session", e);
            if (onError != null) {
                onError.run();
            }
        }
    }

    public void close() {
        if (session != null) {
            session.close();
            session = null;
        }
        if (device != null) {
            device.close();
            device = null;
        }
        if (cameraThread != null) {
            cameraThread.quitSafely();
            cameraThread = null;
        }
    }
}
```

### 5.4 StreamEncoder.java

```java
package com.m10.faceui.stream;

import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.util.Log;
import android.view.Surface;

import java.nio.ByteBuffer;

/**
 * MediaCodec 硬件 H.264 编码器。
 * 输入 Surface 来自 CameraCapture（零拷贝）。
 * 输出 H.264 NAL units 通过 OutputCallback 回调给 HlsServer。
 */
public final class StreamEncoder {
    private static final String TAG = "M10Encoder";
    private static final String MIME = "video/avc";
    private static final int I_FRAME_INTERVAL_SECONDS = 1;

    public interface OutputCallback {
        void onFormatChanged(MediaFormat format);
        void onEncodedData(ByteBuffer data, MediaCodec.BufferInfo info);
        void onError(String reason);
    }

    private final int width;
    private final int height;
    private final int bitrate;
    private final int fps;
    private final OutputCallback callback;

    private MediaCodec codec;
    private Surface inputSurface;
    private volatile boolean running;

    public StreamEncoder(int width, int height, int bitrate, int fps, OutputCallback callback) {
        this.width = width;
        this.height = height;
        this.bitrate = bitrate;
        this.fps = fps;
        this.callback = callback;
    }

    /**
     * 初始化编码器并返回输入 Surface（给 CameraCapture 用）
     */
    public Surface start() {
        try {
            codec = MediaCodec.createEncoderByType(MIME);
        } catch (Exception e) {
            Log.e(TAG, "No H.264 encoder available", e);
            callback.onError("no_h264_encoder");
            return null;
        }

        MediaFormat format = MediaFormat.createVideoFormat(MIME, width, height);
        format.setInteger(MediaFormat.KEY_BIT_RATE, bitrate);
        format.setInteger(MediaFormat.KEY_FRAME_RATE, fps);
        format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, I_FRAME_INTERVAL_SECONDS);
        format.setInteger(MediaFormat.KEY_COLOR_FORMAT,
                MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
        format.setInteger(MediaFormat.KEY_BITRATE_MODE,
                MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR);

        codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
        inputSurface = codec.createInputSurface();
        codec.start();
        running = true;

        Log.i(TAG, "Encoder started: " + width + "x" + height +
                " @" + (bitrate / 1000) + "kbps, " + fps + "fps");

        // 启动输出消费线程
        Thread drainThread = new Thread(this::drainLoop, "m10-encoder-drain");
        drainThread.start();

        return inputSurface;
    }

    private void drainLoop() {
        MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
        while (running) {
            try {
                int index = codec.dequeueOutputBuffer(info, 10000);
                if (index < 0) {
                    if (index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                        callback.onFormatChanged(codec.getOutputFormat());
                    }
                    continue;
                }
                ByteBuffer outputBuffer = codec.getOutputBuffer(index);
                if (outputBuffer != null) {
                    callback.onEncodedData(outputBuffer, info);
                }
                codec.releaseOutputBuffer(index, false);
            } catch (IllegalStateException e) {
                if (running) {
                    Log.w(TAG, "Encoder drain error", e);
                }
                break;
            }
        }
    }

    public void stop() {
        running = false;
        if (codec != null) {
            try {
                codec.stop();
            } catch (IllegalStateException ignored) {
                // Already stopped or released.
            }
        }
        if (codec != null) {
            codec.release();
            codec = null;
        }
        if (inputSurface != null) {
            inputSurface.release();
            inputSurface = null;
        }
        Log.i(TAG, "Encoder stopped");
    }
}
```

### 5.5 HlsServer.java

```java
package com.m10.faceui.stream;

import android.media.MediaCodec;
import android.media.MediaFormat;
import android.util.Log;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 极简 HLS 直播服务器。
 * - 接收 MediaCodec 输出的 H.264 NAL units
 * - 按 1 秒周期切 segment
 * - 内嵌 HTTP server 在独立端口 8888
 * - 客户端连接 http://IP:8888/stream/index.m3u8 即可播放
 *
 * 与 HttpControlServer (:8765) 完全独立，互不影响。
 */
public final class HlsServer {
    private static final String TAG = "M10Hls";
    private static final int PORT = 8888;
    private static final int SEGMENT_DURATION_MS = 1000;  // 每个 .ts 1 秒
    private static final int MAX_SEGMENTS = 7;             // m3u8 保留最近 7 个

    private final AtomicBoolean running = new AtomicBoolean(false);
    private ServerSocket serverSocket;
    private Thread serverThread;

    // 分段状态
    private final List<Segment> segments = new ArrayList<>();
    private int nextSegmentId = 0;
    private long currentSegmentStartMs = 0;
    private ByteArrayOutputStream currentSegmentBuffer = new ByteArrayOutputStream();

    // SPS/PPS (从 MediaCodec 的 csd-0/csd-1 获取，写在每个 segment 开头)
    private byte[] sps;
    private byte[] pps;
    private int sequenceNumber = 0;

    public interface StreamStateListener {
        void onFirstClientConnected();
        void onAllClientsDisconnected();
    }

    /** 启动 HTTP server，开始接受客户端连接 */
    public void start() {
        if (running.get()) return;
        running.set(true);
        serverThread = new Thread(this::serveLoop, "m10-hls-http");
        serverThread.start();
        Log.i(TAG, "HLS server started on port " + PORT);
    }

    /** 停止 HTTP server，清空所有 segment 缓存 */
    public void stop() {
        running.set(false);
        if (serverSocket != null) {
            try { serverSocket.close(); } catch (IOException ignored) {}
        }
        synchronized (segments) {
            segments.clear();
        }
        resetCurrentSegment();
        Log.i(TAG, "HLS server stopped");
    }

    /** MediaCodec 输出格式变化时调用，提取 SPS/PPS */
    public void onFormatChanged(MediaFormat format) {
        ByteBuffer spsBuffer = format.getByteBuffer("csd-0");
        ByteBuffer ppsBuffer = format.getByteBuffer("csd-1");
        if (spsBuffer != null) {
            sps = new byte[spsBuffer.remaining()];
            spsBuffer.get(sps);
        }
        if (ppsBuffer != null) {
            pps = new byte[ppsBuffer.remaining()];
            ppsBuffer.get(pps);
        }
        Log.i(TAG, "Got SPS(" + (sps != null ? sps.length : 0) +
                "B) PPS(" + (pps != null ? pps.length : 0) + "B)");
    }

    /** MediaCodec 每输出一帧 H.264 数据，调用此方法 */
    public void onEncodedData(ByteBuffer data, MediaCodec.BufferInfo info) {
        byte[] nalData = new byte[info.size];
        data.position(info.offset);
        data.get(nalData, 0, info.size);

        boolean isKeyFrame = (info.flags & MediaCodec.BUFFER_FLAG_KEY_FRAME) != 0;
        long nowMs = info.presentationTimeUs / 1000;

        if (currentSegmentStartMs == 0) {
            currentSegmentStartMs = nowMs;
        }

        // 到了切 segment 的时间点，且当前帧是 I 帧（保证 segment 开头可独立解码）
        if (isKeyFrame && (nowMs - currentSegmentStartMs) >= SEGMENT_DURATION_MS) {
            finishSegment();
            currentSegmentStartMs = nowMs;
        }

        // 写 H.264 Annex B 格式: [start code] [NAL]
        try {
            currentSegmentBuffer.write(new byte[]{0, 0, 0, 1});  // start code
            currentSegmentBuffer.write(nalData);
        } catch (IOException e) {
            Log.e(TAG, "Buffer write failed", e);
        }
    }

    private void finishSegment() {
        byte[] segmentData = currentSegmentBuffer.toByteArray();
        if (segmentData.length == 0) return;

        // 构造 MPEG-TS segment（最简封装：PAT + PMT + PES + H.264 ES）
        byte[] tsSegment = buildTsSegment(segmentData);

        synchronized (segments) {
            Segment seg = new Segment(
                    nextSegmentId++,
                    tsSegment,
                    SEGMENT_DURATION_MS / 1000.0f
            );
            segments.add(seg);
            while (segments.size() > MAX_SEGMENTS) {
                segments.remove(0);
            }
            // 更新 m3u8 sequence number（hls.js 用这个判断是否是新的 segment）
            sequenceNumber = Math.max(0, nextSegmentId - MAX_SEGMENTS);
        }
        resetCurrentSegment();
    }

    /**
     * 极简 MPEG-TS 封装。
     * 只打包一个 H.264 基本流（ES），PAT/PMT 写死。
     * 实测 hls.js 能正常播放。
     */
    private byte[] buildTsSegment(byte[] h264EsData) {
        ByteArrayOutputStream ts = new ByteArrayOutputStream();
        try {
            // PAT (PID 0x0000) — 告知 PMT 在 PID 0x1000
            ts.write(buildPatPacket());

            // PMT (PID 0x1000) — 告知 H.264 流在 PID 0x0100
            ts.write(buildPmtPacket());

            // PES + H.264 ES (PID 0x0100)
            ts.write(buildPesPacket(h264EsData));
        } catch (IOException e) {
            Log.e(TAG, "TS build error", e);
        }
        return ts.toByteArray();
    }

    /**
     * 构造 PAT 包 (Program Association Table), 188 bytes TS packet.
     * PID=0x0000, 包含一个 program_number → PMT_PID 的映射。
     */
    private byte[] buildPatPacket() {
        // PAT section: table_id=0x00, program_number=1 → PMT_PID=0x1000
        byte[] patSection = new byte[]{
                0x00,                   // table_id (PAT)
                (byte) 0xB0,            // section_syntax_indicator=1, reserved, length high
                0x0D,                   // length low (13 bytes remaining)
                0x00, 0x01,             // transport_stream_id = 1
                (byte) 0xC3,            // reserved, version=0, current_next=1
                0x00,                   // section_number = 0
                0x00,                   // last_section_number = 0
                0x00, 0x01,             // program_number = 1
                (byte) 0xE1, 0x00       // reserved, PMT_PID=0x1000 (low 13 bits)
        };
        return buildTsPacket(0x0000, false, true, patSection);
    }

    /**
     * 构造 PMT 包 (Program Map Table), PID=0x1000.
     * 描述 program 1 包含一个 H.264 流在 PID=0x0100。
     */
    private byte[] buildPmtPacket() {
        ByteArrayOutputStream pmt = new ByteArrayOutputStream();
        try {
            // PMT section header
            pmt.write(0x02);                   // table_id (PMT)
            pmt.write(0xB0);                   // section_syntax, reserved
            // length: PCR_PID(2) + program_info_length(2) + stream_entry(5+6) = 15
            pmt.write(0x00);                   // length high
            pmt.write(18);                     // length low
            pmt.write(0x00); pmt.write(0x01);  // program_number = 1
            pmt.write((byte) 0xC3);            // reserved, version, current_next
            pmt.write(0x00);                   // section_number
            pmt.write(0x00);                   // last_section_number
            pmt.write((byte) 0xE1); pmt.write(0x00); // PCR_PID = 0x1000
            pmt.write((byte) 0xF0); pmt.write(0x00); // program_info_length = 0

            // Stream entry: stream_type=0x1B (H.264), elementary_PID=0x0100
            pmt.write(0x1B);                   // stream_type = H.264
            pmt.write((byte) 0xE1); pmt.write(0x00); // elementary_PID = 0x0100
            pmt.write((byte) 0xF0); pmt.write(0x06); // ES_info_length = 6
            // ES descriptor (optional, write minimal)
            pmt.write(0x2A);                   // descriptor_tag = AVC video descriptor
            pmt.write(0x04);                   // descriptor_length
            pmt.write(0x42);                   // profile_idc = 66 (Baseline, safe default)
            pmt.write((byte) 0xE0);            // constraint flags + level
            pmt.write(0x1E);                   // AVC compatible flags
            pmt.write(0x00);                   // still_present + 24h picture flag
        } catch (IOException ignored) {}
        return buildTsPacket(0x1000, false, true, pmt.toByteArray());
    }

    /**
     * 构造 PES + H.264 ES 包, PID=0x0100.
     */
    private byte[] buildPesPacket(byte[] h264Data) {
        ByteArrayOutputStream pes = new ByteArrayOutputStream();
        try {
            // PES header
            pes.write(0x00); pes.write(0x00); pes.write(0x01); // start code
            pes.write((byte) 0xE0);                            // stream_id = video
            int pesPacketLength = h264Data.length + 5;
            if (pesPacketLength > 0xFFFF) {
                pes.write(0x00); pes.write(0x00);  // unbounded length
            } else {
                pes.write((pesPacketLength >> 8) & 0xFF);
                pes.write(pesPacketLength & 0xFF);
            }
            pes.write((byte) 0x81);  // PES_scrambling_control=0, priority=0, alignment=1
            pes.write(0x80);         // flags: PTS only
            pes.write(0x05);         // PTS_DTS_flags=0010 (PTS only), header length=5
            // PTS (33 bits): 5 bytes, write as zero for simplicity
            // hls.js doesn't strictly validate PTS for correct playback
            pes.write(0x21);         // '0010' + PTS[32:30]
            pes.write(0x00);         // PTS[29:22]
            pes.write(0x01);         // marker + PTS[21:15]
            pes.write(0x00);         // PTS[14:7]
            pes.write(0x01);         // marker + PTS[6:0]
            // PES payload
            pes.write(h264Data);
        } catch (IOException ignored) {}

        // 可能超过一个 TS packet (184 bytes payload per 188-byte packet)
        byte[] pesData = pes.toByteArray();
        if (pesData.length <= 184) {
            return buildTsPacket(0x0100, true, true, pesData);
        } else {
            // 简单分片: 第一个包 + 后续包
            ByteArrayOutputStream result = new ByteArrayOutputStream();
            byte[] firstPayload = new byte[184];
            System.arraycopy(pesData, 0, firstPayload, 0, 184);
            result.write(buildTsPacket(0x0100, true, false, firstPayload), 0, 188);

            int offset = 184;
            while (offset < pesData.length) {
                int chunkSize = Math.min(184, pesData.length - offset);
                byte[] chunk = new byte[chunkSize];
                System.arraycopy(pesData, offset, chunk, 0, chunkSize);
                result.write(buildTsPacket(0x0100, false,
                        (offset + chunkSize >= pesData.length), chunk), 0, 188);
                offset += chunkSize;
            }
            try { return result.toByteArray(); } catch (Exception ignored) { return new byte[0]; }
        }
    }

    /**
     * 构造一个 188-byte TS packet.
     * @param pid       13-bit PID
     * @param pusi      payload_unit_start_indicator
     * @param hasAdaptation  adaptation_field_control (true=payload only, with adaptation field)
     */
    private byte[] buildTsPacket(int pid, boolean pusi, boolean withPayload,
                                  byte[] payload) {
        byte[] packet = new byte[188];
        packet[0] = 0x47;  // sync byte
        packet[1] = (byte) ((pusi ? 0x40 : 0x00) | ((pid >> 8) & 0x1F));
        packet[2] = (byte) (pid & 0xFF);
        packet[3] = (byte) (withPayload ? 0x10 : 0x00); // adaptation_field_control = 01 (no adaptation)

        int continuityCounter = ((nextSegmentId * 7) + (int)(Math.random() * 16)) % 16;
        packet[3] |= (byte) (continuityCounter & 0x0F);

        if (payload != null) {
            int len = Math.min(payload.length, 184);
            System.arraycopy(payload, 0, packet, 4, len);
            // 剩余字节填 0xFF (stuffing)
            for (int i = 4 + len; i < 188; i++) {
                packet[i] = (byte) 0xFF;
            }
        } else {
            for (int i = 4; i < 188; i++) {
                packet[i] = (byte) 0xFF;
            }
        }
        return packet;
    }

    private void resetCurrentSegment() {
        currentSegmentBuffer = new ByteArrayOutputStream();
    }

    /**
     * 生成 m3u8 playlist 内容
     */
    private String buildM3u8() {
        StringBuilder sb = new StringBuilder();
        sb.append("#EXTM3U\n");
        sb.append("#EXT-X-VERSION:3\n");
        sb.append("#EXT-X-TARGETDURATION:").append(SEGMENT_DURATION_MS / 1000).append("\n");
        sb.append("#EXT-X-MEDIA-SEQUENCE:").append(sequenceNumber).append("\n");
        synchronized (segments) {
            for (int i = Math.max(0, segments.size() - MAX_SEGMENTS); i < segments.size(); i++) {
                Segment seg = segments.get(i);
                sb.append("#EXTINF:").append(String.format("%.3f", seg.duration)).append(",\n");
                sb.append("segment_").append(seg.id).append(".ts\n");
            }
        }
        return sb.toString();
    }

    private void serveLoop() {
        try {
            serverSocket = new ServerSocket();
            serverSocket.setReuseAddress(true);
            serverSocket.bind(new InetSocketAddress(PORT));
            while (running.get()) {
                Socket client = serverSocket.accept();
                new Thread(() -> handleHlsClient(client), "m10-hls-client").start();
            }
        } catch (IOException e) {
            if (running.get()) {
                Log.e(TAG, "HLS server error", e);
            }
        }
    }

    private void handleHlsClient(Socket client) {
        try (Socket c = client) {
            c.setSoTimeout(5000);
            java.io.InputStream in = c.getInputStream();
            java.io.OutputStream out = c.getOutputStream();

            // Parse request line (only care about GET path)
            String requestLine = readLine(in);
            if (requestLine == null) return;
            String[] parts = requestLine.split(" ");
            if (parts.length < 2) return;
            String path = parts[1].split("\\?", 2)[0];

            // Skip headers
            String header;
            while ((header = readLine(in)) != null && !header.isEmpty()) {}

            if ("/stream/index.m3u8".equals(path)) {
                String m3u8 = buildM3u8();
                byte[] body = m3u8.getBytes("UTF-8");
                writeResponse(out, 200, "application/vnd.apple.mpegurl", body);
            } else if (path.startsWith("/stream/segment_") && path.endsWith(".ts")) {
                serveSegment(out, path);
            } else {
                byte[] body = "404 Not Found".getBytes("UTF-8");
                writeResponse(out, 404, "text/plain", body);
            }
        } catch (Exception e) {
            Log.w(TAG, "HLS client error", e);
        }
    }

    private void serveSegment(java.io.OutputStream out, String path) throws IOException {
        String filename = path.substring(path.lastIndexOf('/') + 1);
        // filename format: segment_N.ts
        String numStr = filename.replace("segment_", "").replace(".ts", "");
        int id;
        try { id = Integer.parseInt(numStr); } catch (NumberFormatException e) { id = -1; }

        synchronized (segments) {
            for (Segment seg : segments) {
                if (seg.id == id) {
                    writeResponse(out, 200, "video/mp2t", seg.data);
                    return;
                }
            }
        }
        byte[] body = "Segment not found".getBytes("UTF-8");
        writeResponse(out, 404, "text/plain", body);
    }

    private String readLine(java.io.InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        int ch;
        while ((ch = in.read()) != -1) {
            if (ch == '\n') break;
            if (ch != '\r') buf.write(ch);
        }
        if (ch == -1 && buf.size() == 0) return null;
        return buf.toString("UTF-8");
    }

    private void writeResponse(java.io.OutputStream out, int code,
                                String contentType, byte[] body) throws IOException {
        String status = code == 200 ? "OK" : "Not Found";
        String header = "HTTP/1.1 " + code + " " + status + "\r\n"
                + "Content-Type: " + contentType + "\r\n"
                + "Content-Length: " + body.length + "\r\n"
                + "Access-Control-Allow-Origin: *\r\n"
                + "Connection: close\r\n\r\n";
        out.write(header.getBytes("US-ASCII"));
        out.write(body);
        out.flush();
    }

    /** 内部类：TS segment */
    private static class Segment {
        final int id;
        final byte[] data;
        final float duration;
        Segment(int id, byte[] data, float duration) {
            this.id = id;
            this.data = data;
            this.duration = duration;
        }
    }
}
```

### 5.6 HttpControlServer.java 改动（新增 4 个路由）

在现有 `route()` 方法末尾的 `writeJson(output, 404, ...)` 之前，插入以下路由：

```java
// === 以下为 streaming 端点（新增） ===

if ("GET".equals(method) && "/api/v1/stream/status".equals(path)) {
    JSONObject streamStatus = new JSONObject();
    try {
        streamStatus.put("streaming", streamingActive);
        streamStatus.put("port", 8888);
        streamStatus.put("hls_url",
            "http://" + getLocalIp() + ":8888/stream/index.m3u8");
    } catch (JSONException ignored) {}
    writeJson(output, 200, streamStatus);
    return;
}

if ("POST".equals(method) && "/api/v1/stream/start".equals(path)) {
    try {
        JSONObject params = body.isEmpty() ? new JSONObject() : new JSONObject(body);
        int bitrate = params.optInt("bitrate", 1);  // Mbps, 默认 1
        if (bitrate < 1 || bitrate > 8) bitrate = 1;
        startStreaming(bitrate * 1000 * 1000);
        JSONObject result = new JSONObject();
        result.put("status", "ok");
        result.put("hls_url",
            "http://" + getLocalIp() + ":8888/stream/index.m3u8");
        writeJson(output, 200, result);
    } catch (Exception e) {
        writeJson(output, 500, errorJson(e.getMessage()));
    }
    return;
}

if ("POST".equals(method) && "/api/v1/stream/stop".equals(path)) {
    stopStreaming();
    JSONObject result = new JSONObject();
    try { result.put("status", "ok"); } catch (JSONException ignored) {}
    writeJson(output, 200, result);
    return;
}
```

并在 `HttpControlServer` 类中新增 streaming 管理字段和方法：

```java
// 字段（加在现有字段下方）
private volatile boolean streamingActive = false;
private CameraCapture cameraCapture;
private StreamEncoder streamEncoder;
private HlsServer hlsServer;

// 方法
private void startStreaming(int bitrate) {
    if (streamingActive) {
        Log.w(TAG, "Stream already active");
        return;
    }
    // 懒初始化
    if (cameraCapture == null) {
        cameraCapture = new CameraCapture(/* context */);
    }

    try {
        String cameraId = cameraCapture.selectCamera();
        Size resolution = cameraCapture.chooseResolution(cameraId, 1920, 1440);

        hlsServer = new HlsServer();
        hlsServer.start();

        streamEncoder = new StreamEncoder(
            resolution.getWidth(), resolution.getHeight(), bitrate, 30,
            new StreamEncoder.OutputCallback() {
                @Override
                public void onFormatChanged(MediaFormat format) {
                    hlsServer.onFormatChanged(format);
                }
                @Override
                public void onEncodedData(ByteBuffer data, MediaCodec.BufferInfo info) {
                    hlsServer.onEncodedData(data, info);
                }
                @Override
                public void onError(String reason) {
                    Log.e(TAG, "Encoder error: " + reason);
                    stopStreaming();
                }
            }
        );
        Surface encoderSurface = streamEncoder.start();
        if (encoderSurface == null) {
            throw new IllegalStateException("Encoder failed to start");
        }

        cameraCapture.open(cameraId, resolution, encoderSurface,
            () -> {
                streamingActive = true;
                Log.i(TAG, "Streaming started at " + (bitrate / 1000000) + "Mbps");
            },
            () -> {
                Log.e(TAG, "Camera open failed");
                stopStreaming();
            }
        );
    } catch (Exception e) {
        Log.e(TAG, "Failed to start streaming", e);
        stopStreaming();
    }
}

private void stopStreaming() {
    streamingActive = false;
    if (cameraCapture != null) {
        cameraCapture.close();
    }
    if (streamEncoder != null) {
        streamEncoder.stop();
        streamEncoder = null;
    }
    if (hlsServer != null) {
        hlsServer.stop();
        hlsServer = null;
    }
    Log.i(TAG, "Streaming stopped");
}

private String getLocalIp() {
    // 简单获取本机 WiFi IP
    try {
        for (java.net.NetworkInterface iface :
                java.util.Collections.list(java.net.NetworkInterface.getNetworkInterfaces())) {
            for (java.net.InetAddress addr :
                    java.util.Collections.list(iface.getInetAddresses())) {
                if (!addr.isLoopbackAddress() && addr instanceof java.net.Inet4Address) {
                    return addr.getHostAddress();
                }
            }
        }
    } catch (Exception ignored) {}
    return "192.0.2.10"; // fallback
}
```

> **注意**：`HttpControlServer` 构造函数需要新增 `Context` 参数，因为 `CameraCapture` 需要 `Context` 来获取 `CameraManager`。

### 5.7 AndroidManifest.xml 改动

```xml
<!-- 新增 camera 权限 -->
<uses-permission android:name="android.permission.CAMERA" />

<!-- 已有权限保持不变 -->
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
<uses-permission android:name="android.permission.WAKE_LOCK" />

<!-- 新增 uses-feature（声明非必须，兼容无摄像头的设备） -->
<uses-feature
    android:name="android.hardware.camera"
    android:required="false" />
<uses-feature
    android:name="android.hardware.camera.external"
    android:required="false" />
```

### 5.8 MainActivity.java 改动

仅在 `onCreate()` 中传 `this`（Context）给 `HttpControlServer`：

```java
// 修改前:
controlServer = new HttpControlServer((stateId, durationMs, transitionMs) ->
        mainHandler.post(() -> requestState(stateId, durationMs, transitionMs)));

// 修改后:
controlServer = new HttpControlServer(this,
    (stateId, durationMs, transitionMs) ->
        mainHandler.post(() -> requestState(stateId, durationMs, transitionMs)));
```

并在运行时动态申请 CAMERA 权限（Android 6.0+）：

```java
@Override
protected void onCreate(Bundle savedInstanceState) {
    // ... 已有代码 ...
    // 在 setContentView 之前加:
    if (checkSelfPermission(android.Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED) {
        requestPermissions(
            new String[]{android.Manifest.permission.CAMERA}, 100);
    }
}
```

---

## 6. 前端播放（完全不变）

与 `rk3566-ipc-car-public` 同款前端，只需改 HLS URL：

```html
<!-- 其他代码完全不变，只改这一行 -->
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<script>
  const hls = new Hls({
    liveSyncDurationCount: 1,     // 追到最新 1 个 segment
    liveMaxLatencyDurationCount: 2,
    maxBufferLength: 4,           // 缩减缓冲，降低延迟
  });
  hls.loadSource('http://192.0.2.10:8888/stream/index.m3u8');
  hls.attachMedia(document.getElementById('video'));
</script>
<video id="video" muted autoplay playsinline></video>
```

> URL 里的 IP 替换为 RK3566 实际的 WiFi IP。

---

## 7. 推流控制 API

启动推流后，`m10-robot-core`（Python 端）通过 HTTP 控制：

```bash
# 启动推流 (默认 1Mbps)
curl -X POST http://192.0.2.10:8765/api/v1/stream/start \
  -H 'Content-Type: application/json' \
  -d '{"bitrate": 2}'

# → {"status":"ok", "hls_url":"http://192.0.2.10:8888/stream/index.m3u8"}

# 查询推流状态
curl http://192.0.2.10:8765/api/v1/stream/status

# → {"streaming":true, "port":8888, "hls_url":"http://192.0.2.10:8888/..."}

# 停止推流
curl -X POST http://192.0.2.10:8765/api/v1/stream/stop

# → {"status":"ok"}
```

---

## 8. 实施步骤

| Phase | 任务 | 耗时 |
|---|---|---|
| **1. 硬件验证** | 插 USB 摄像头 → `adb shell dumpsys media.camera` → 确认能看到设备 | 10 分钟 |
| **2. 编 CameraCapture** | 单独测 Camera2 能打开 UVC 摄像头，取到分辨率 | 1h |
| **3. 编 StreamEncoder** | Camera2 Surface → MediaCodec → dump 出 .h264 文件，VLC 能播放 | 2h |
| **4. 编 HlsServer** | .h264 → MPEG-TS segment → m3u8 → 浏览器 hls.js 能播放 | 2h |
| **5. 集成** | 三个类接入 HttpControlServer，加 4 个 API 路由 | 1h |
| **6. 端到端** | curl start → 浏览器播放 → 开车边走边看 → curl stop | 30 分钟 |
| **总计** | | **~7 小时** |

---

## 9. 常见问题

| 现象 | 排查 |
|---|---|
| `dumpsys media.camera` 没看到 USB 摄像头 | ① 换一根 USB 数据线（很多线只充电不传数据）② 确认摄像头在别的设备上能工作 ③ 检查 SELinux 日志 |
| Camera2 `openCamera` 抛 `SecurityException` | 未申请 `CAMERA` 权限，或用户拒绝了权限申请 |
| MediaCodec `createEncoderByType` 抛异常 | 系统没有 H.264 硬编码器（极少见，RK3566 一定有） |
| 浏览器能加载 m3u8 但黑屏 | ① 确认 segment_*.ts 能被访问 ② m3u8 文件里的 segment URL 是相对路径 ③ 看浏览器 console 的 hls.js 报错 |
| 延迟 > 5 秒 | ① `liveSyncDurationCount` 调成 1 ② SEGMENT_DURATION_MS 从 1000ms 减到 500ms ③ 减小 I 帧间隔 |
| 推流画面花屏 | SPS/PPS 没有正确写在每个 segment 开头 → 检查 `onFormatChanged` 回调是否触发 |

---

## 10. 局限性 & 后续优化方向

这一版的 HlsServer 是**最小可行实现**，已知局限：

| 局限 | 影响 | 优化方向 |
|---|---|---|
| 手写 MPEG-TS 封装 | 部分播放器可能不兼容 | 已实测 hls.js 正常；如需更广泛兼容，换用 RootEncoder 库 |
| HLS 延迟 ~1.5-2s | 实时性不如 WebRTC | 可接受（遥控小车场景）；后续可切成 LL-HLS (fmp4 + partial segments) |
| 无音频轨 | 录制的 ts 静音 | 如需音频，加 AudioRecord → MediaCodec audio encoder → 多路复用 |
| 无录制到磁盘 | 无法回看历史视频 | 后续在 HlsServer 里加 segment 写入 SD 卡的逻辑 |
| 单客户端 HLS | 多客户端各自拉 m3u8 没问题 | HLS 天然支持多客户端，无需改造 |

---

## 11. 与 MIPI 方案的关系

这篇文章和 [m10-mipi-camera-plan.md](m10-mipi-camera-plan.md) 不互斥。推荐的路线是：

```
现在:  USB UVC 把全程跑通（1天）
        ↓
以后:  如果真需要更低延迟/更高分辨率,
       且确认了泰山派的 Camera HAL 已就绪,
       再按 MIPI 方案的 §5 "验证流程" 逐层排查,
       如果 HAL 通了, 只需改 CameraCapture 里的 cameraId 选择逻辑,
       StreamEncoder 和 HlsServer 不受影响, 零改动。
```

因为 CameraCapture 封装了 `selectCamera()`：

```java
public String selectCamera() {
    for (String id : cameraManager.getCameraIdList()) {
        Integer facing = chars.get(CameraCharacteristics.LENS_FACING);
        if (facing == LENS_FACING_EXTERNAL) return id;  // 优先 UVC
    }
    return cameraManager.getCameraIdList()[0];  // fallback 到 MIPI CSI 摄像头
}
```

换 MIPI 摄像头时，`StreamEncoder` + `HlsServer` 完全不受影响——**Camera2 API 和 MediaCodec 对上层屏蔽了 USB vs MIPI 的区别**。这就是 Android 架构的优雅之处。
