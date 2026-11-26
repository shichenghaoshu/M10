package com.m10.faceui.detect;

import android.content.res.AssetFileDescriptor;
import android.graphics.Bitmap;
import android.graphics.Matrix;
import android.util.Log;

import org.tensorflow.lite.Interpreter;

import java.io.FileInputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

/**
 * TFLite 目标检测器。
 * 使用 SSD MobileNet V2 COCO 量化模型 (uint8 input/output)。
 * 纯 CPU 推理，不依赖 GPU delegate。
 */
public final class TFLiteDetector {
    private static final String TAG = "M10Detect";

    // 模型输入尺寸
    private static final int INPUT_SIZE = 300;
    // COCO 数据集 90 个类别的标签（和 SSD MobileNet 的 labelmap 对齐）
    private static final String[] COCO_LABELS = {
        "???", "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
        "truck", "boat", "traffic light", "fire hydrant", "???", "stop sign",
        "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
        "elephant", "bear", "zebra", "giraffe", "???", "backpack", "umbrella", "???",
        "???", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
        "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
        "surfboard", "tennis racket", "bottle", "???", "wine glass", "cup", "fork",
        "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
        "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
        "potted plant", "bed", "???", "dining table", "???", "???", "toilet", "???",
        "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
        "oven", "toaster", "sink", "refrigerator", "???", "book", "clock", "vase",
        "scissors", "teddy bear", "hair drier", "toothbrush"
    };

    private Interpreter interpreter;
    private ByteBuffer inputBuffer;
    private float[][][] outputBoxes;   // [1][10][4] (batch × detections × yxhw)
    private float[][] outputClasses;   // [1][10]
    private float[][] outputScores;    // [1][10]
    private float[]   outputCount;     // [1]

    private volatile boolean ready;

    public TFLiteDetector() {
        outputBoxes = new float[1][10][4];
        outputClasses = new float[1][10];
        outputScores = new float[1][10];
        outputCount = new float[1];
    }

    /**
     * 从文件路径加载 .tflite 模型。
     * Android 上常用路径: /data/local/tmp/detect.tflite
     */
    public boolean loadModel(String modelPath) {
        try {
            FileInputStream fis = new FileInputStream(modelPath);
            FileChannel channel = fis.getChannel();
            MappedByteBuffer modelBuffer = channel.map(
                    FileChannel.MapMode.READ_ONLY, 0, channel.size());

            Interpreter.Options options = new Interpreter.Options();
            options.setNumThreads(4);  // RK3566 有 4 核 A55

            interpreter = new Interpreter(modelBuffer, options);

            // 分配输入 buffer: [1, 300, 300, 3] × uint8 = 270000 bytes
            inputBuffer = ByteBuffer.allocateDirect(1 * INPUT_SIZE * INPUT_SIZE * 3);
            inputBuffer.order(ByteOrder.nativeOrder());

            ready = true;
            Log.i(TAG, "Model loaded from " + modelPath +
                    ", input=" + interpreter.getInputTensorCount() +
                    ", output=" + interpreter.getOutputTensorCount());
            return true;
        } catch (IOException e) {
            Log.e(TAG, "Failed to load model: " + modelPath, e);
            ready = false;
            return false;
        }
    }

    /**
     * 从 Android assets 加载模型（作为备选方案）
     */
    public boolean loadModelFromAssets(AssetFileDescriptor afd) {
        try {
            FileInputStream fis = afd.createInputStream();
            FileChannel channel = fis.getChannel();
            MappedByteBuffer modelBuffer = channel.map(
                    FileChannel.MapMode.READ_ONLY, afd.getStartOffset(), afd.getDeclaredLength());

            Interpreter.Options options = new Interpreter.Options();
            options.setNumThreads(4);

            interpreter = new Interpreter(modelBuffer, options);
            inputBuffer = ByteBuffer.allocateDirect(1 * INPUT_SIZE * INPUT_SIZE * 3);
            inputBuffer.order(ByteOrder.nativeOrder());

            ready = true;
            Log.i(TAG, "Model loaded from assets");
            return true;
        } catch (IOException e) {
            Log.e(TAG, "Failed to load model from assets", e);
            ready = false;
            return false;
        }
    }

    public boolean isReady() {
        return ready && interpreter != null;
    }

    /**
     * 检测结果
     */
    public static class Detection {
        public String label;
        public float confidence;
        /** 归一化坐标 [0..1] */
        public float x1, y1, x2, y2;
        /** 实际图像坐标 */
        public int left, top, right, bottom;

        @Override
        public String toString() {
            return String.format("%s %.0f%% [%d,%d,%d,%d]",
                    label, confidence * 100, left, top, right, bottom);
        }
    }

    /**
     * 对一张 Bitmap 进行检测，返回检测到的目标列表。
     * 只返回置信度 > minConfidence 且类别为 person 的结果。
     * 如果 personOnly=false，返回所有类别。
     */
    public List<Detection> detect(Bitmap bitmap, float minConfidence, boolean personOnly) {
        if (!ready) {
            return Collections.emptyList();
        }

        // 1. 预处理: 缩放到 300×300，转 uint8 RGB
        preprocess(bitmap);

        // 2. 推理 (线程安全)
        synchronized (interpreter) {
            interpreter.runForMultipleInputsOutputs(
                    new Object[]{inputBuffer},
                    new java.util.HashMap<Integer, Object>() {{
                        put(0, outputBoxes);     // TFLite outputs indexed by position
                        put(1, outputClasses);
                        put(2, outputScores);
                        put(3, outputCount);
                    }}
            );
        }

        // 3. 后处理: 解析检测结果
        List<Detection> detections = new ArrayList<>();
        int count = Math.min((int) outputCount[0], 10);
        int imageW = bitmap.getWidth();
        int imageH = bitmap.getHeight();

        for (int i = 0; i < count; i++) {
            float score = outputScores[0][i];
            if (score < minConfidence) continue;

            // 模型输出 class ID 为 0-based float（0=person），转为 1-based int
            int classId = (int) outputClasses[0][i] + 1;
            if (classId < 1 || classId >= COCO_LABELS.length) continue;

            if (personOnly && classId != 1) continue; // class 1 = person

            Detection d = new Detection();
            d.confidence = score;
            d.label = COCO_LABELS[classId];

            // 输出是 [ymin, xmin, ymax, xmax] 归一化坐标
            d.y1 = outputBoxes[0][i][0];
            d.x1 = outputBoxes[0][i][1];
            d.y2 = outputBoxes[0][i][2];
            d.x2 = outputBoxes[0][i][3];

            // 映射回实际图像尺寸
            d.left = Math.max(0, (int) (d.x1 * imageW));
            d.top = Math.max(0, (int) (d.y1 * imageH));
            d.right = Math.min(imageW, (int) (d.x2 * imageW));
            d.bottom = Math.min(imageH, (int) (d.y2 * imageH));

            detections.add(d);
        }

        // 按置信度降序排列
        Collections.sort(detections, (a, b) -> Float.compare(b.confidence, a.confidence));
        return detections;
    }

    /**
     * Bitmap → 300×300 uint8 RGB ByteBuffer
     */
    private void preprocess(Bitmap bitmap) {
        inputBuffer.rewind();

        // 缩放到 300×300
        Bitmap scaled = Bitmap.createScaledBitmap(bitmap, INPUT_SIZE, INPUT_SIZE, true);

        int[] pixels = new int[INPUT_SIZE * INPUT_SIZE];
        scaled.getPixels(pixels, 0, INPUT_SIZE, 0, 0, INPUT_SIZE, INPUT_SIZE);

        // 写入 uint8 RGB 到 ByteBuffer
        for (int pixel : pixels) {
            inputBuffer.put((byte) ((pixel >> 16) & 0xFF));  // R
            inputBuffer.put((byte) ((pixel >> 8) & 0xFF));   // G
            inputBuffer.put((byte) (pixel & 0xFF));           // B
        }

        inputBuffer.rewind();

        if (scaled != bitmap) {
            scaled.recycle();
        }
    }

    public void close() {
        ready = false;
        if (interpreter != null) {
            interpreter.close();
            interpreter = null;
        }
        Log.i(TAG, "Detector closed");
    }
}
