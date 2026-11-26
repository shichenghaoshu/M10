package com.m10.faceui.detect;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.ImageFormat;
import android.graphics.Rect;
import android.graphics.YuvImage;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.TotalCaptureResult;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Log;
import android.view.Surface;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.util.Collections;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Camera2 单帧采集器。
 * 每次调用 captureOneFrame() 打开摄像头、取一帧、关闭摄像头。
 * 用于按需检测场景（不当摄像头常驻前台使用时）。
 */
public final class CameraInference {
    private static final String TAG = "M10CamInfer";
    private static final int CAPTURE_TIMEOUT_SEC = 3;

    private final CameraManager cameraManager;
    private final HandlerThread cameraThread;
    private final Handler cameraHandler;

    private String cameraId;
    private int captureWidth = 640;
    private int captureHeight = 480;

    public CameraInference(Context context) {
        cameraManager = (CameraManager) context.getSystemService(Context.CAMERA_SERVICE);
        cameraThread = new HandlerThread("m10-camera-infer");
        cameraThread.start();
        cameraHandler = new Handler(cameraThread.getLooper());
    }

    /**
     * 选择摄像头：优先 external (UVC)，fallback 任意。
     */
    public boolean selectCamera() {
        try {
            for (String id : cameraManager.getCameraIdList()) {
                CameraCharacteristics chars = cameraManager.getCameraCharacteristics(id);
                Integer facing = chars.get(CameraCharacteristics.LENS_FACING);
                if (facing != null && facing == CameraCharacteristics.LENS_FACING_EXTERNAL) {
                    cameraId = id;
                    Log.i(TAG, "Selected external camera: " + id);
                    return true;
                }
            }
            // fallback
            String[] ids = cameraManager.getCameraIdList();
            if (ids.length > 0) {
                cameraId = ids[0];
                Log.i(TAG, "Fallback to camera: " + cameraId);
                return true;
            }
        } catch (CameraAccessException e) {
            Log.e(TAG, "Failed to enumerate cameras", e);
        }
        return false;
    }

    public void setCaptureSize(int width, int height) {
        this.captureWidth = width;
        this.captureHeight = height;
    }

    /**
     * 采集一帧，返回 RGB Bitmap。
     * 每次调用都完整走 open → capture → close 的流程。
     */
    public Bitmap captureOneFrame() {
        if (cameraId == null) {
            Log.e(TAG, "No camera selected");
            return null;
        }

        ImageReader imageReader = ImageReader.newInstance(
                captureWidth, captureHeight, ImageFormat.JPEG, 2);
        CountDownLatch captureLatch = new CountDownLatch(1);
        Bitmap[] result = new Bitmap[1];

        try {
            cameraManager.openCamera(cameraId, new CameraDevice.StateCallback() {
                @Override
                public void onOpened(CameraDevice device) {
                    try {
                        Surface surface = imageReader.getSurface();
                        CaptureRequest.Builder builder = device.createCaptureRequest(
                                CameraDevice.TEMPLATE_STILL_CAPTURE);
                        builder.addTarget(surface);

                        device.createCaptureSession(
                                Collections.singletonList(surface),
                                new CameraCaptureSession.StateCallback() {
                                    @Override
                                    public void onConfigured(CameraCaptureSession session) {
                                        try {
                                            session.capture(builder.build(),
                                                    new CameraCaptureSession.CaptureCallback() {
                                                        @Override
                                                        public void onCaptureCompleted(
                                                                CameraCaptureSession s,
                                                                CaptureRequest req,
                                                                TotalCaptureResult res) {
                                                            captureLatch.countDown();
                                                        }
                                                    }, cameraHandler);
                                        } catch (CameraAccessException e) {
                                            Log.e(TAG, "Capture failed", e);
                                            captureLatch.countDown();
                                        }
                                    }

                                    @Override
                                    public void onConfigureFailed(CameraCaptureSession s) {
                                        Log.e(TAG, "Session config failed");
                                        captureLatch.countDown();
                                    }
                                }, cameraHandler);
                    } catch (CameraAccessException e) {
                        Log.e(TAG, "Create session failed", e);
                        captureLatch.countDown();
                    }
                }

                @Override
                public void onDisconnected(CameraDevice device) {
                    device.close();
                }

                @Override
                public void onError(CameraDevice device, int error) {
                    Log.e(TAG, "Camera error: " + error);
                    device.close();
                    captureLatch.countDown();
                }
            }, cameraHandler);

            // 等待采集完成
            boolean finished = captureLatch.await(CAPTURE_TIMEOUT_SEC, TimeUnit.SECONDS);
            if (!finished) {
                Log.w(TAG, "Capture timed out");
                return null;
            }

            // 从 ImageReader 取出图像
            Image image = imageReader.acquireLatestImage();
            if (image != null) {
                try {
                    ByteBuffer buffer = image.getPlanes()[0].getBuffer();
                    byte[] jpegData = new byte[buffer.remaining()];
                    buffer.get(jpegData);

                    BitmapFactory.Options opts = new BitmapFactory.Options();
                    opts.inPreferredConfig = Bitmap.Config.ARGB_8888;
                    result[0] = BitmapFactory.decodeByteArray(
                            jpegData, 0, jpegData.length, opts);
                } finally {
                    image.close();
                }
            }
        } catch (CameraAccessException | SecurityException e) {
            Log.e(TAG, "Camera access error", e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } finally {
            imageReader.close();
        }

        return result[0];
    }

    public void shutdown() {
        cameraThread.quitSafely();
    }
}
