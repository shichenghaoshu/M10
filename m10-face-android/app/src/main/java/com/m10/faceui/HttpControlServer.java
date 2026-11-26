package com.m10.faceui;

import android.content.Context;
import android.graphics.Bitmap;
import android.util.Log;

import com.m10.faceui.detect.CameraInference;
import com.m10.faceui.detect.TFLiteDetector;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

final class HttpControlServer {
    interface StateListener {
        void onStateRequested(int stateId, long durationMs, long transitionMs);
    }

    static final int PORT = 8765;
    private static final String TAG = "M10FaceHttp";
    private static final int MAX_BODY_BYTES = 8192;
    private static final String[] STATE_KEYS = {
            "idle_blink", "idle_breathe", "happy", "excited", "playful",
            "sleep", "curious", "listening", "thinking", "low_battery"
    };
    private static final String[] STATE_NAMES = {
            "默认待机·灵动眨眼", "极简待机·呼吸灯效果", "猫咪开心·撒娇表情",
            "超级兴奋·星星眼", "调皮眨眼·互动回应", "睡眠模式·安静打呼",
            "好奇疑惑·探索状态", "聆听模式·声波响应", "思考模式·三点循环",
            "低电量·委屈求充电"
    };

    private final StateListener listener;
    private final AtomicBoolean running = new AtomicBoolean(false);
    private final AtomicInteger currentState = new AtomicInteger(1);
    private final Map<String, Integer> aliases = new HashMap<>();
    private ServerSocket serverSocket;
    private Thread serverThread;

    // 目标检测（可选）
    private final Context appContext;
    private TFLiteDetector detector;
    private CameraInference cameraInference;
    private volatile boolean detectionReady;

    HttpControlServer(Context context, StateListener listener) {
        this.appContext = context.getApplicationContext();
        this.listener = listener;
        for (int index = 0; index < STATE_KEYS.length; index++) {
            aliases.put(STATE_KEYS[index], index + 1);
        }
        aliases.put("idle", 1);
        aliases.put("standby", 1);
        aliases.put("blink", 1);
        aliases.put("breathe", 2);
        aliases.put("joy", 3);
        aliases.put("super_excited", 4);
        aliases.put("wink", 5);
        aliases.put("sleeping", 6);
        aliases.put("question", 7);
        aliases.put("listen", 8);
        aliases.put("think", 9);
        aliases.put("battery_low", 10);
    }

    void setCurrentState(int stateId) {
        currentState.set(stateId);
    }

    synchronized void start() {
        if (running.get()) {
            return;
        }
        running.set(true);
        serverThread = new Thread(this::serveLoop, "m10-face-http");
        serverThread.start();
    }

    synchronized void stop() {
        running.set(false);
        if (serverSocket != null) {
            try {
                serverSocket.close();
            } catch (IOException ignored) {
                // Socket close is best effort during Activity teardown.
            }
        }
        serverSocket = null;
        serverThread = null;
        shutdownDetection();
    }

    // ---- 目标检测模块 ----

    /**
     * 初始化检测器。模型文件需已推送到设备。
     * @param modelPath TFLite 模型路径，如 "/data/local/tmp/detect.tflite"
     */
    public boolean initDetection(String modelPath) {
        try {
            detector = new TFLiteDetector();
            if (!detector.loadModel(modelPath)) {
                Log.e(TAG, "Failed to load detection model from " + modelPath);
                return false;
            }
            cameraInference = new CameraInference(appContext);
            if (!cameraInference.selectCamera()) {
                Log.e(TAG, "No camera available for detection");
                detector.close();
                detector = null;
                return false;
            }
            detectionReady = true;
            Log.i(TAG, "Detection initialized, camera=" + cameraInference +
                    " model=" + modelPath);
            return true;
        } catch (Exception e) {
            Log.e(TAG, "Failed to init detection", e);
            detectionReady = false;
            return false;
        }
    }

    public boolean isDetectionReady() {
        return detectionReady && detector != null && detector.isReady();
    }

    private void shutdownDetection() {
        detectionReady = false;
        if (detector != null) {
            detector.close();
            detector = null;
        }
        if (cameraInference != null) {
            cameraInference.shutdown();
            cameraInference = null;
        }
    }

    private void serveLoop() {
        try {
            ServerSocket socket = new ServerSocket();
            socket.setReuseAddress(true);
            socket.bind(new InetSocketAddress(PORT));
            serverSocket = socket;
            Log.i(TAG, "HTTP control listening on 0.0.0.0:" + PORT);
            while (running.get()) {
                Socket client = socket.accept();
                Thread worker = new Thread(() -> handleClient(client), "m10-face-http-client");
                worker.start();
            }
        } catch (IOException exception) {
            if (running.get()) {
                Log.e(TAG, "HTTP control server stopped unexpectedly", exception);
            }
        } finally {
            running.set(false);
        }
    }

    private void handleClient(Socket client) {
        try (Socket socket = client;
             BufferedInputStream input = new BufferedInputStream(socket.getInputStream());
             BufferedOutputStream output = new BufferedOutputStream(socket.getOutputStream())) {
            socket.setSoTimeout(3000);
            String requestLine = readLine(input);
            if (requestLine == null || requestLine.isEmpty()) {
                return;
            }
            String[] requestParts = requestLine.split(" ");
            if (requestParts.length < 2) {
                writeJson(output, 400, errorJson("invalid request line"));
                return;
            }

            String method = requestParts[0].toUpperCase(Locale.US);
            String path = requestParts[1].split("\\?", 2)[0];
            int contentLength = 0;
            String headerLine;
            while ((headerLine = readLine(input)) != null && !headerLine.isEmpty()) {
                int separator = headerLine.indexOf(':');
                if (separator <= 0) {
                    continue;
                }
                String headerName = headerLine.substring(0, separator).trim().toLowerCase(Locale.US);
                String headerValue = headerLine.substring(separator + 1).trim();
                if ("content-length".equals(headerName)) {
                    contentLength = Integer.parseInt(headerValue);
                }
            }

            if (contentLength < 0 || contentLength > MAX_BODY_BYTES) {
                writeJson(output, 413, errorJson("request body too large"));
                return;
            }
            byte[] bodyBytes = readBytes(input, contentLength);
            String body = new String(bodyBytes, StandardCharsets.UTF_8);
            route(output, method, path, body);
        } catch (Exception exception) {
            Log.w(TAG, "Rejected HTTP control request", exception);
        }
    }

    private void route(BufferedOutputStream output, String method, String path, String body) throws IOException {
        if ("OPTIONS".equals(method)) {
            writeJson(output, 200, new JSONObject());
            return;
        }
        if ("GET".equals(method) && "/health".equals(path)) {
            JSONObject health = new JSONObject();
            try {
                health.put("status", "ok");
                health.put("service", "m10-face-android");
                health.put("port", PORT);
                health.put("state", currentState.get());
            } catch (JSONException ignored) {
                // Fixed keys and primitive values cannot fail here.
            }
            writeJson(output, 200, health);
            return;
        }
        if ("GET".equals(method) && "/api/v1/state".equals(path)) {
            writeJson(output, 200, stateJson(currentState.get()));
            return;
        }
        if ("GET".equals(method) && "/api/v1/states".equals(path)) {
            JSONObject response = new JSONObject();
            JSONArray states = new JSONArray();
            for (int stateId = 1; stateId <= 10; stateId++) {
                states.put(stateJson(stateId));
            }
            try {
                response.put("states", states);
            } catch (JSONException ignored) {
                // Fixed JSON value cannot fail here.
            }
            writeJson(output, 200, response);
            return;
        }
        if (("POST".equals(method) || "PUT".equals(method))
                && ("/api/v1/state".equals(path) || "/api/state".equals(path))) {
            try {
                JSONObject command = new JSONObject(body);
                int stateId = parseState(command.opt("state"));
                long durationMs = clamp(command.optLong("duration_ms", 0), 0, 3_600_000);
                long transitionMs = clamp(command.optLong("transition_ms", 140), 0, 2_000);
                listener.onStateRequested(stateId, durationMs, transitionMs);
                writeJson(output, 200, stateJson(stateId));
            } catch (JSONException | IllegalArgumentException exception) {
                writeJson(output, 422, errorJson(exception.getMessage()));
            }
            return;
        }
        // ---- 跟随控制 API (检测 + 控制决策一步完成) ----
        if ("POST".equals(method) && "/api/v1/follow".equals(path)) {
            if (!isDetectionReady()) {
                writeJson(output, 503, errorJson("detection_not_ready"));
                return;
            }
            try {
                // 采集一帧
                long t0 = System.currentTimeMillis();
                Bitmap frame = cameraInference.captureOneFrame();
                long t1 = System.currentTimeMillis();

                if (frame == null) {
                    writeJson(output, 500, errorJson("camera_capture_failed"));
                    return;
                }

                // 检测人
                List<TFLiteDetector.Detection> detections =
                        detector.detect(frame, 0.35f, true);
                long t2 = System.currentTimeMillis();

                int frameW = frame.getWidth();
                int frameH = frame.getHeight();
                frame.recycle();

                JSONObject result = new JSONObject();
                result.put("status", "ok");
                result.put("capture_ms", t1 - t0);
                result.put("inference_ms", t2 - t1);

                if (!detections.isEmpty()) {
                    TFLiteDetector.Detection best = detections.get(0);
                    int cx = best.left + (best.right - best.left) / 2;
                    int area = (best.right - best.left) * (best.bottom - best.top);
                    int frameArea = frameW * frameH;
                    float areaRatio = (float) area / frameArea;

                    // 跟随控制决策
                    String motorCommand;
                    if (areaRatio > 0.30f) {
                        motorCommand = "backward";   // 太近，后退
                    } else if (areaRatio < 0.06f) {
                        motorCommand = "forward";    // 太远，前进
                    } else if (cx < frameW * 0.35f) {
                        motorCommand = "left";       // 人在左侧，左转
                    } else if (cx > frameW * 0.65f) {
                        motorCommand = "right";      // 人在右侧，右转
                    } else {
                        motorCommand = "stop";       // 人在中间，距离合适
                    }

                    JSONObject det = new JSONObject();
                    det.put("label", best.label);
                    det.put("confidence", Math.round(best.confidence * 1000) / 1000.0);
                    det.put("x", best.left);
                    det.put("y", best.top);
                    det.put("width", best.right - best.left);
                    det.put("height", best.bottom - best.top);
                    result.put("detection", det);
                    result.put("target_cx", cx);
                    result.put("target_cy", best.top + (best.bottom - best.top) / 2);
                    result.put("area_ratio", Math.round(areaRatio * 1000) / 1000.0);
                    result.put("motor_command", motorCommand);
                } else {
                    result.put("detection", JSONObject.NULL);
                    result.put("motor_command", "stop");  // 没看到人，停
                }

                writeJson(output, 200, result);
            } catch (Exception e) {
                Log.e(TAG, "Follow error", e);
                writeJson(output, 500, errorJson("follow_error: " + e.getMessage()));
            }
            return;
        }

        // ---- 目标检测 API ----
        if ("GET".equals(method) && "/api/v1/detect/status".equals(path)) {
            JSONObject status = new JSONObject();
            try {
                status.put("ready", isDetectionReady());
                status.put("model_loaded", detector != null && detector.isReady());
                status.put("camera_ok", cameraInference != null);
            } catch (JSONException ignored) {}
            writeJson(output, 200, status);
            return;
        }

        if ("POST".equals(method) && "/api/v1/detect".equals(path)) {
            if (!isDetectionReady()) {
                writeJson(output, 503, errorJson("detection_not_ready"));
                return;
            }
            try {
                JSONObject params = body.isEmpty() ? new JSONObject() : new JSONObject(body);
                String mode = params.optString("mode", "person"); // person | all
                double minConf = params.optDouble("min_confidence", 0.4);

                // 采集一帧
                long t0 = System.currentTimeMillis();
                Bitmap frame = cameraInference.captureOneFrame();
                long t1 = System.currentTimeMillis();

                if (frame == null) {
                    writeJson(output, 500, errorJson("camera_capture_failed"));
                    return;
                }

                // 检测
                List<TFLiteDetector.Detection> detections =
                        detector.detect(frame, (float) minConf, "person".equals(mode));
                long t2 = System.currentTimeMillis();

                frame.recycle();

                // 构建响应
                JSONObject result = new JSONObject();
                result.put("status", "ok");
                result.put("capture_ms", t1 - t0);
                result.put("inference_ms", t2 - t1);
                result.put("total_ms", t2 - t0);
                result.put("mode", mode);

                if (!detections.isEmpty()) {
                    JSONArray arr = new JSONArray();
                    for (TFLiteDetector.Detection d : detections) {
                        JSONObject det = new JSONObject();
                        det.put("label", d.label);
                        det.put("confidence", Math.round(d.confidence * 1000) / 1000.0);
                        det.put("x", d.left);
                        det.put("y", d.top);
                        det.put("width", d.right - d.left);
                        det.put("height", d.bottom - d.top);
                        arr.put(det);
                    }
                    result.put("detections", arr);
                    result.put("count", detections.size());
                    // 如果检测到人，返回画面中心最显著的人的信息
                    TFLiteDetector.Detection best = detections.get(0);
                    int personCx = best.left + (best.right - best.left) / 2;
                    int personCy = best.top + (best.bottom - best.top) / 2;
                    result.put("target_cx", personCx);
                    result.put("target_cy", personCy);
                    result.put("target_width", best.right - best.left);
                    result.put("target_height", best.bottom - best.top);
                } else {
                    result.put("detections", new JSONArray());
                    result.put("count", 0);
                }

                writeJson(output, 200, result);
            } catch (Exception e) {
                Log.e(TAG, "Detection error", e);
                writeJson(output, 500, errorJson("detection_error: " + e.getMessage()));
            }
            return;
        }

        writeJson(output, 404, errorJson("not found"));
    }

    private int parseState(Object value) {
        if (value == null || value == JSONObject.NULL) {
            throw new IllegalArgumentException("state is required");
        }
        int stateId;
        if (value instanceof Number) {
            stateId = ((Number) value).intValue();
        } else {
            String text = String.valueOf(value).trim().toLowerCase(Locale.US)
                    .replace('-', '_').replace(' ', '_');
            if (text.endsWith(".mp4")) {
                text = text.substring(0, text.length() - 4);
            }
            Integer alias = aliases.get(text);
            if (alias != null) {
                stateId = alias;
            } else {
                try {
                    stateId = Integer.parseInt(text);
                } catch (NumberFormatException exception) {
                    throw new IllegalArgumentException("unknown state: " + value);
                }
            }
        }
        if (stateId < 1 || stateId > 10) {
            throw new IllegalArgumentException("state id must be between 1 and 10");
        }
        return stateId;
    }

    private static JSONObject stateJson(int stateId) {
        JSONObject state = new JSONObject();
        try {
            state.put("id", stateId);
            state.put("key", STATE_KEYS[stateId - 1]);
            state.put("name", STATE_NAMES[stateId - 1]);
            state.put("video", stateId + ".mp4");
        } catch (JSONException ignored) {
            // Fixed values cannot fail here.
        }
        return state;
    }

    private static JSONObject errorJson(String message) {
        JSONObject error = new JSONObject();
        try {
            error.put("error", message == null ? "invalid request" : message);
        } catch (JSONException ignored) {
            // Fixed key cannot fail here.
        }
        return error;
    }

    private static long clamp(long value, long minimum, long maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    private static String readLine(BufferedInputStream input) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        int current;
        while ((current = input.read()) != -1) {
            if (current == '\n') {
                break;
            }
            if (current != '\r') {
                buffer.write(current);
            }
            if (buffer.size() > MAX_BODY_BYTES) {
                throw new IOException("HTTP line too long");
            }
        }
        if (current == -1 && buffer.size() == 0) {
            return null;
        }
        return buffer.toString("UTF-8");
    }

    private static byte[] readBytes(BufferedInputStream input, int length) throws IOException {
        byte[] bytes = new byte[length];
        int offset = 0;
        while (offset < length) {
            int count = input.read(bytes, offset, length - offset);
            if (count < 0) {
                throw new IOException("incomplete request body");
            }
            offset += count;
        }
        return bytes;
    }

    private static void writeJson(BufferedOutputStream output, int statusCode, JSONObject payload) throws IOException {
        byte[] body = payload.toString().getBytes(StandardCharsets.UTF_8);
        String statusText;
        switch (statusCode) {
            case 200:
                statusText = "OK";
                break;
            case 400:
                statusText = "Bad Request";
                break;
            case 404:
                statusText = "Not Found";
                break;
            case 413:
                statusText = "Payload Too Large";
                break;
            default:
                statusText = "Unprocessable Entity";
                break;
        }
        String headers = "HTTP/1.1 " + statusCode + " " + statusText + "\r\n"
                + "Content-Type: application/json; charset=utf-8\r\n"
                + "Content-Length: " + body.length + "\r\n"
                + "Access-Control-Allow-Origin: *\r\n"
                + "Access-Control-Allow-Headers: Content-Type, Authorization\r\n"
                + "Access-Control-Allow-Methods: GET, POST, PUT, OPTIONS\r\n"
                + "Connection: close\r\n\r\n";
        output.write(headers.getBytes(StandardCharsets.US_ASCII));
        output.write(body);
        output.flush();
    }
}
