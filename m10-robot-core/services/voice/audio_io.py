"""Streaming audio capture/playback for the M10 voice pipeline.

Wraps sounddevice (PortAudio). No mock data: every failure path returns a
truthful reason string instead of pretending hardware exists.
"""
from __future__ import annotations

import threading
import wave
from collections import deque
from pathlib import Path

try:
    import numpy as np
except ImportError:  # pragma: no cover - environment dependent
    np = None

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover - environment dependent
    sd = None


DEVICE_NAME_KEYWORDS = ("respeaker", "array", "usb audio", "usb audio device", "seeed")


def _deps_status() -> dict | None:
    """Return an error dict if a dependency is missing, else None."""
    if np is None:
        return {"status": "unavailable", "reason": "numpy_not_installed"}
    if sd is None:
        return {"status": "unavailable", "reason": "sounddevice_not_installed"}
    return None


class RingBuffer:
    """Fixed-size mono int16 ring buffer for pre-wake audio."""

    def __init__(self, seconds: float, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self._capacity = int(seconds * sample_rate)
        self._buf = deque(maxlen=self._capacity)
        self._lock = threading.Lock()

    def write(self, chunk: "np.ndarray") -> None:
        with self._lock:
            self._buf.extend(chunk.tolist())

    def read_all(self) -> "np.ndarray":
        with self._lock:
            return np.array(self._buf, dtype=np.int16)


class AudioIO:
    """Owns the capture stream, playback helpers, and the pre-wake ring buffer."""

    def __init__(self, config: dict, logger) -> None:
        self.config = config
        self.logger = logger
        self.sample_rate = int(config.get("sample_rate", 16000))
        self.channels = 1
        self.block_ms = int(config.get("block_ms", 30))
        self.device_index: int | None = config.get("device_index")
        self.output_device_index: int | None = config.get("output_device_index")
        self.ring = RingBuffer(float(config.get("pre_wake_seconds", 2.0)), self.sample_rate)
        self._stream = None
        self._running = False
        self._level = 0.0  # RMS of the latest block, 0..1
        self._frame_callbacks = []
        self._lock = threading.Lock()

    # ---------- discovery ----------

    def list_devices(self) -> dict:
        err = _deps_status()
        if err:
            return err
        try:
            devices = sd.query_devices()
        except Exception as exc:  # PortAudio errors land here
            return {"status": "error", "reason": "portaudio_query_failed", "details": str(exc)}
        result = []
        for idx, dev in enumerate(devices):
            result.append(
                {
                    "index": idx,
                    "name": dev["name"],
                    "max_input_channels": dev["max_input_channels"],
                    "max_output_channels": dev["max_output_channels"],
                    "default_samplerate": dev["default_samplerate"],
                }
            )
        return {"status": "available", "devices": result}

    def find_capture_device(self) -> dict:
        """Pick a capture device: configured index > name keyword > system default."""
        err = _deps_status()
        if err:
            return err
        listing = self.list_devices()
        if listing["status"] != "available":
            return listing
        inputs = [d for d in listing["devices"] if d["max_input_channels"] > 0]
        if not inputs:
            return {"status": "unavailable", "reason": "capture_device_not_found"}

        if self.device_index is not None:
            match = [d for d in inputs if d["index"] == self.device_index]
            if match:
                return {"status": "available", "device": match[0]}
            return {"status": "unavailable", "reason": "configured_device_index_invalid", "device_index": self.device_index}

        for keyword in DEVICE_NAME_KEYWORDS:
            for dev in inputs:
                if keyword in dev["name"].lower():
                    return {"status": "available", "device": dev, "matched_keyword": keyword}
        return {"status": "available", "device": inputs[0], "matched_keyword": "system_default"}

    # ---------- capture ----------

    def add_frame_callback(self, callback) -> None:
        """Register a callback(chunk: np.ndarray[int16]) fired per captured block."""
        self._frame_callbacks.append(callback)

    def _on_audio_block(self, indata, frames, time_info, status) -> None:
        if status:
            self.logger.warning("capture stream status: %s", status)
        mono = indata[:, 0] if indata.ndim > 1 else indata
        chunk = (mono * 32767).astype(np.int16)
        self._level = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))
        self.ring.write(chunk)
        for callback in self._frame_callbacks:
            try:
                callback(chunk)
            except Exception as exc:  # a bad consumer must not kill the stream
                self.logger.error("frame callback failed: %s", exc)

    def start_capture(self) -> dict:
        err = _deps_status()
        if err:
            return err
        with self._lock:
            if self._running:
                return {"status": "available", "detail": "already_running"}
            found = self.find_capture_device()
            if found["status"] != "available":
                return found
            device = found["device"]
            try:
                self._stream = sd.InputStream(
                    device=device["index"],
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype="float32",
                    blocksize=int(self.sample_rate * self.block_ms / 1000),
                    callback=self._on_audio_block,
                )
                self._stream.start()
            except Exception as exc:
                self._stream = None
                return {"status": "error", "reason": "capture_start_failed", "details": str(exc)}
            self._running = True
            self.logger.info("capture started on device %s (%s)", device["index"], device["name"])
            return {"status": "available", "device": device}

    def stop_capture(self) -> dict:
        with self._lock:
            if not self._running:
                return {"status": "available", "detail": "not_running"}
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
                self._running = False
            return {"status": "available", "detail": "stopped"}

    @property
    def running(self) -> bool:
        return self._running

    @property
    def level(self) -> float:
        """RMS of the latest captured block, 0..1."""
        return self._level

    # ---------- playback / wav ----------

    def play_pcm(self, pcm: "np.ndarray", sample_rate: int | None = None) -> dict:
        err = _deps_status()
        if err:
            return err
        try:
            sd.play(pcm.astype(np.float32) / 32767.0, samplerate=sample_rate or self.sample_rate,
                    device=self.output_device_index)
            sd.wait()
        except Exception as exc:
            return {"status": "error", "reason": "playback_failed", "details": str(exc)}
        return {"status": "available"}

    def save_wav(self, pcm: "np.ndarray", path: Path, sample_rate: int | None = None) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate or self.sample_rate)
            wav.writeframes(pcm.astype(np.int16).tobytes())
        return path
