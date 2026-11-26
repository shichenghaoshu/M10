package com.m10.faceui;

import android.app.Activity;
import android.content.res.AssetFileDescriptor;
import android.graphics.Color;
import android.graphics.Matrix;
import android.graphics.SurfaceTexture;
import android.media.MediaPlayer;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.Gravity;
import android.view.Surface;
import android.view.TextureView;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.widget.FrameLayout;

import java.io.IOException;

public final class MainActivity extends Activity {
    private static final String TAG = "M10FaceUI";
    private static final int DEFAULT_STATE = 1;
    private static final int[] STATE_RESOURCES = {
            R.raw.face_01, R.raw.face_02, R.raw.face_03, R.raw.face_04, R.raw.face_05,
            R.raw.face_06, R.raw.face_07, R.raw.face_08, R.raw.face_09, R.raw.face_10
    };

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private FaceLayer layerA;
    private FaceLayer layerB;
    private FaceLayer activeLayer;
    private View rightEdgeMask;
    private HttpControlServer controlServer;
    private int currentState = 0;
    private int switchGeneration = 0;
    private Runnable pendingReset;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN,
                WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
                | WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);

        FrameLayout stage = new FrameLayout(this);
        stage.setBackgroundColor(Color.BLACK);
        layerA = new FaceLayer(stage);
        layerB = new FaceLayer(stage);
        rightEdgeMask = new View(this);
        rightEdgeMask.setBackgroundColor(Color.BLACK);
        FrameLayout.LayoutParams maskParams = new FrameLayout.LayoutParams(
                12, ViewGroup.LayoutParams.MATCH_PARENT, Gravity.RIGHT);
        stage.addView(rightEdgeMask, maskParams);
        setContentView(stage);

        controlServer = new HttpControlServer(this,
                (stateId, durationMs, transitionMs) ->
                mainHandler.post(() -> requestState(stateId, durationMs, transitionMs)));
        controlServer.start();
        requestState(DEFAULT_STATE, 0, 0);

        // 尝试加载检测模型（如果设备上已推送了模型文件）
        String modelPath = "/data/local/tmp/detect.tflite";
        new Thread(() -> {
            boolean ok = controlServer.initDetection(modelPath);
            Log.i(TAG, "Detection init: " + (ok ? "ready" : "skipped (no model)"));
        }, "m10-detection-init").start();
    }

    @Override
    protected void onResume() {
        super.onResume();
        enterImmersiveMode();
        if (activeLayer != null) {
            activeLayer.resume();
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            enterImmersiveMode();
        }
    }

    @Override
    public void onBackPressed() {
        enterImmersiveMode();
    }

    @Override
    protected void onDestroy() {
        if (pendingReset != null) {
            mainHandler.removeCallbacks(pendingReset);
        }
        if (controlServer != null) {
            controlServer.stop();
        }
        if (layerA != null) {
            layerA.release();
        }
        if (layerB != null) {
            layerB.release();
        }
        super.onDestroy();
    }

    private void enterImmersiveMode() {
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
    }

    private void requestState(int stateId, long durationMs, long transitionMs) {
        if (pendingReset != null) {
            mainHandler.removeCallbacks(pendingReset);
            pendingReset = null;
        }
        switchState(stateId, transitionMs);
        if (durationMs > 0) {
            pendingReset = () -> {
                pendingReset = null;
                switchState(DEFAULT_STATE, 140);
            };
            mainHandler.postDelayed(pendingReset, durationMs);
        }
    }

    private void switchState(int stateId, long transitionMs) {
        if (stateId < 1 || stateId > STATE_RESOURCES.length) {
            Log.w(TAG, "Rejected invalid state " + stateId);
            return;
        }
        if (stateId == currentState && activeLayer != null && activeLayer.isPlaying()) {
            controlServer.setCurrentState(stateId);
            return;
        }

        currentState = stateId;
        controlServer.setCurrentState(stateId);
        int generation = ++switchGeneration;
        FaceLayer previous = activeLayer;
        FaceLayer target = previous == layerA ? layerB : layerA;
        long safeTransition = Math.max(0, Math.min(transitionMs, 2000));
        target.prepare(STATE_RESOURCES[stateId - 1], generation, (readyLayer, readyGeneration) -> {
            if (readyGeneration != switchGeneration) {
                readyLayer.releasePlayer();
                return;
            }
            readyLayer.getView().animate().cancel();
            readyLayer.getView().setAlpha(0f);
            readyLayer.getView().bringToFront();
            rightEdgeMask.bringToFront();
            readyLayer.getView().animate().alpha(1f).setDuration(safeTransition).start();
            if (previous != null && previous != readyLayer) {
                previous.getView().animate().cancel();
                previous.getView().animate().alpha(0f).setDuration(safeTransition)
                        .withEndAction(previous::releasePlayer).start();
            }
            activeLayer = readyLayer;
            Log.i(TAG, "Showing face state " + stateId);
        });
    }

    private static final class FaceLayer implements TextureView.SurfaceTextureListener {
        interface ReadyListener {
            void onReady(FaceLayer layer, int generation);
        }

        private final TextureView textureView;
        private Surface surface;
        private MediaPlayer mediaPlayer;
        private int pendingResource;
        private int pendingGeneration;
        private ReadyListener pendingListener;

        FaceLayer(FrameLayout parent) {
            textureView = new TextureView(parent.getContext());
            textureView.setAlpha(0f);
            // Transparent composition keeps the black parent visible outside
            // square videos and avoids RK3566 rotation-stride edge artifacts.
            textureView.setOpaque(false);
            textureView.setSurfaceTextureListener(this);
            FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    Gravity.CENTER);
            parent.addView(textureView, params);
        }

        TextureView getView() {
            return textureView;
        }

        boolean isPlaying() {
            return mediaPlayer != null && mediaPlayer.isPlaying();
        }

        void resume() {
            if (mediaPlayer != null && !mediaPlayer.isPlaying()) {
                mediaPlayer.start();
            }
        }

        void prepare(int resourceId, int generation, ReadyListener listener) {
            pendingResource = resourceId;
            pendingGeneration = generation;
            pendingListener = listener;
            if (surface != null) {
                preparePending();
            }
        }

        private void preparePending() {
            final int resourceId = pendingResource;
            final int generation = pendingGeneration;
            final ReadyListener listener = pendingListener;
            if (resourceId == 0 || listener == null || surface == null) {
                return;
            }
            pendingResource = 0;
            pendingListener = null;
            releasePlayer();

            MediaPlayer player = new MediaPlayer();
            mediaPlayer = player;
            try (AssetFileDescriptor descriptor = textureView.getResources().openRawResourceFd(resourceId)) {
                if (descriptor == null) {
                    throw new IOException("Video resource has no file descriptor");
                }
                player.setDataSource(descriptor.getFileDescriptor(), descriptor.getStartOffset(), descriptor.getLength());
                player.setSurface(surface);
                player.setLooping(true);
                player.setVolume(0f, 0f);
                player.setScreenOnWhilePlaying(true);
                player.setOnVideoSizeChangedListener((ignored, width, height) -> applyFitTransform(width, height));
                player.setOnPreparedListener(prepared -> {
                    if (prepared != mediaPlayer) {
                        prepared.release();
                        return;
                    }
                    applyFitTransform(prepared.getVideoWidth(), prepared.getVideoHeight());
                    prepared.start();
                    listener.onReady(this, generation);
                });
                player.setOnErrorListener((failed, what, extra) -> {
                    Log.e(TAG, "MediaPlayer error what=" + what + " extra=" + extra);
                    if (failed == mediaPlayer) {
                        releasePlayer();
                    }
                    return true;
                });
                player.prepareAsync();
            } catch (IOException | RuntimeException exception) {
                Log.e(TAG, "Unable to prepare face video", exception);
                releasePlayer();
            }
        }

        private void applyFitTransform(int videoWidth, int videoHeight) {
            int viewWidth = textureView.getWidth();
            int viewHeight = textureView.getHeight();
            if (videoWidth <= 0 || videoHeight <= 0 || viewWidth <= 0 || viewHeight <= 0) {
                return;
            }
            float fitScale = Math.min((float) viewWidth / videoWidth, (float) viewHeight / videoHeight);
            float renderedWidth = videoWidth * fitScale;
            float renderedHeight = videoHeight * fitScale;
            Matrix transform = new Matrix();
            transform.setScale(renderedWidth / viewWidth, renderedHeight / viewHeight,
                    viewWidth / 2f, viewHeight / 2f);
            textureView.setTransform(transform);
        }

        void releasePlayer() {
            MediaPlayer player = mediaPlayer;
            mediaPlayer = null;
            if (player != null) {
                try {
                    player.stop();
                } catch (IllegalStateException ignored) {
                    // Player may still be preparing.
                }
                player.reset();
                player.release();
            }
        }

        void release() {
            pendingResource = 0;
            pendingListener = null;
            releasePlayer();
            if (surface != null) {
                surface.release();
                surface = null;
            }
        }

        @Override
        public void onSurfaceTextureAvailable(SurfaceTexture surfaceTexture, int width, int height) {
            surface = new Surface(surfaceTexture);
            preparePending();
        }

        @Override
        public void onSurfaceTextureSizeChanged(SurfaceTexture surfaceTexture, int width, int height) {
            if (mediaPlayer != null) {
                applyFitTransform(mediaPlayer.getVideoWidth(), mediaPlayer.getVideoHeight());
            }
        }

        @Override
        public boolean onSurfaceTextureDestroyed(SurfaceTexture surfaceTexture) {
            releasePlayer();
            if (surface != null) {
                surface.release();
                surface = null;
            }
            return true;
        }

        @Override
        public void onSurfaceTextureUpdated(SurfaceTexture surfaceTexture) {
            // No per-frame work; decoding stays entirely in MediaPlayer.
        }
    }
}
