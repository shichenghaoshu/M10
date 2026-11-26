from __future__ import annotations

import glob
import multiprocessing
from datetime import datetime
from pathlib import Path

try:
    import cv2
except ImportError:  # pragma: no cover - depends on runtime environment
    cv2 = None


class VideoService:
    def __init__(self, config: dict, logger, base_path: Path, discovery_status: dict | None = None) -> None:
        self.config = config
        self.logger = logger
        self.base_path = base_path
        self.discovery_status = discovery_status or {}

    def _candidate_devices(self) -> list[str]:
        configured = self.config.get("device_candidates", [])
        discovered = self.discovery_status.get("devices", []) if self.discovery_status.get("status") == "available" else []
        devices = set(configured)
        devices.update(discovered)
        devices.update(glob.glob("/dev/video*"))
        return sorted(device for device in devices if Path(device).exists())

    def get_status(self) -> dict:
        devices = self._candidate_devices()
        if not self.config.get("enabled", True):
            return {"status": "unavailable", "reason": "video_disabled"}
        if not devices:
            return {"status": "unavailable", "reason": "camera_device_not_found"}
        return {"status": "available", "devices": devices}

    @staticmethod
    def _capture_snapshot_worker(
        device: str,
        width: int,
        height: int,
        output_path: str,
        queue: multiprocessing.queues.Queue,
    ) -> None:
        capture = cv2.VideoCapture(device)
        if not capture.isOpened():
            queue.put({"ok": False, "reason": "open_failed", "device": device})
            return

        try:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            ok, frame = capture.read()
        finally:
            capture.release()

        if not ok or frame is None:
            queue.put({"ok": False, "reason": "capture_failed", "device": device})
            return

        if not cv2.imwrite(output_path, frame):
            queue.put({"ok": False, "reason": "snapshot_write_failed", "device": device})
            return

        queue.put({"ok": True, "device": device, "path": output_path})

    def snapshot(self) -> dict:
        if not self.config.get("enabled", True):
            return {"ok": False, "status": "unavailable", "reason": "video_disabled"}
        devices = self._candidate_devices()
        if not devices:
            return {"ok": False, "status": "unavailable", "reason": "camera_device_not_found"}
        if cv2 is None:
            return {"ok": False, "status": "error", "reason": "opencv_not_installed"}

        snapshot_dir = self.base_path / self.config.get("snapshot_path", "data/snapshots")
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        capture_timeout = float(self.config.get("capture_timeout_seconds", 5.0))
        last_reason = "open_failed"

        for device in devices:
            filename = f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            output_path = snapshot_dir / filename
            ctx = multiprocessing.get_context("spawn")
            queue = ctx.Queue()
            process = ctx.Process(
                target=self._capture_snapshot_worker,
                args=(
                    device,
                    int(self.config.get("width", 640)),
                    int(self.config.get("height", 480)),
                    str(output_path),
                    queue,
                ),
            )
            process.start()
            process.join(timeout=capture_timeout)
            if process.is_alive():
                process.terminate()
                process.join()
                last_reason = "capture_timeout"
                self.logger.warning("Timed out while capturing snapshot from %s", device)
                continue

            if queue.empty():
                last_reason = "capture_failed"
                self.logger.warning("Camera worker exited without result for %s", device)
                continue

            result = queue.get()
            if result.get("ok"):
                relative_path = Path(result["path"]).relative_to(self.base_path).as_posix()
                return {"ok": True, "path": relative_path, "device": result["device"]}

            last_reason = result.get("reason", "open_failed")
            self.logger.warning("Snapshot attempt failed for %s: %s", device, last_reason)

        return {"ok": False, "status": "error", "reason": last_reason, "devices": devices}
