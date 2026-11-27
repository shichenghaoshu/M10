"""Dreamupers' FFmpeg recipe, with configured paths and owned child processes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.request

import yaml

from .settings import ROOT, UPSTREAM


def download_mediamtx(destination: Path):
    manifest = json.loads((ROOT / "m10_runtime/media-assets.json").read_text())
    arch = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64", "amd64": "amd64"}.get(platform.machine().lower())
    if platform.system() != "Linux" or arch not in manifest["assets"]:
        raise RuntimeError("Automatic MediaMTX download supports Linux arm64/amd64 only")
    source = manifest["assets"][arch]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as work:
        archive = Path(work) / "release.tar.gz"
        digest = hashlib.sha256()
        with urllib.request.urlopen(source["url"], timeout=60) as response, archive.open("wb") as out:
            total = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > 128 * 1024 * 1024:
                    raise RuntimeError("MediaMTX archive exceeds size limit")
                out.write(block)
                digest.update(block)
        if digest.hexdigest() != source["sha256"]:
            raise RuntimeError("MediaMTX archive SHA-256 mismatch")
        with tarfile.open(archive, "r:gz") as tar:
            member = next((m for m in tar.getmembers() if m.name in {"mediamtx", "./mediamtx"} and m.isfile()), None)
            if member is None:
                raise RuntimeError("MediaMTX executable missing from verified archive")
            binary = Path(work) / "mediamtx"
            with tar.extractfile(member) as inp, binary.open("wb") as out:
                shutil.copyfileobj(inp, out)
            binary.chmod(0o755)
            for m in tar.getmembers():
                if m.isfile() and Path(m.name).name.upper() == "LICENSE":
                    (destination.parent / "LICENSE.mediamtx").write_bytes(tar.extractfile(m).read())
            os.replace(binary, destination)
        (destination.parent / "mediamtx-source.json").write_text(json.dumps({**source, "version": manifest["version"]}, indent=2) + "\n")


def executable(value: str) -> str | None:
    path = Path(value).expanduser()
    if not path.is_absolute() and "/" in value:
        path = ROOT / path
    if "/" in value:
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(value)


class Media:
    def __init__(self, config: dict, data: Path):
        self.config, self.data = dict(config), data
        self.processes = []
        self.log = None
        self.error = None
        self.last_hls_at = None
        self.lock = threading.RLock()

    def preflight(self) -> dict:
        if not self.config["enabled"]:
            return {"ready": False, "state": "disabled", "missing": []}
        missing = []
        ffmpeg, mediamtx = executable(self.config["ffmpeg"]), executable(self.config["mediamtx"])
        if platform.system() != "Linux":
            missing.append("V4L2 capture requires Linux")
        if not Path(self.config["device"]).exists():
            missing.append("Camera device not found: " + self.config["device"])
        if not mediamtx:
            missing.append("MediaMTX executable not installed")
        if not ffmpeg:
            missing.append("FFmpeg not installed")
        else:
            try:
                probe = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=5)
                if not re.search(r"\b" + re.escape(self.config["encoder"]) + r"\b", probe.stdout):
                    missing.append("FFmpeg encoder missing: " + self.config["encoder"])
            except (OSError, subprocess.TimeoutExpired) as exc:
                missing.append(str(exc))
        return {"ready": not missing, "state": "ready" if not missing else "unavailable", "missing": missing}

    def command(self) -> list[str]:
        cmd = json.loads((UPSTREAM / "rtsp/ffmpeg_cmd.json").read_text())["cmd"][:]
        # Preserve the upstream V4L2 -> H264 -> RTSP recipe, adapting each host.
        for option in ["-profile:v", "-level", "-rc_mode", "-flags", "-tune", "-preset"]:
            if option in cmd:
                i = cmd.index(option)
                del cmd[i:i + 2]
        replacements = {"-i": self.config["device"], "-input_format": self.config["input_format"],
                        "-framerate": str(self.config["framerate"]), "-video_size": self.config["video_size"],
                        "-vf": "fps=" + str(self.config["framerate"]), "-c:v": self.config["encoder"],
                        "-b:v": str(self.config["bitrate_mbps"]) + "M", "-bufsize": str(self.config["bitrate_mbps"]) + "M"}
        for option, value in replacements.items():
            cmd[cmd.index(option) + 1] = value
        cmd[0] = executable(self.config["ffmpeg"]) or self.config["ffmpeg"]
        cmd[-1] = "rtsp://127.0.0.1:" + str(self.config["rtsp_port"]) + "/stream"
        cmd[1:1] = ["-nostdin", "-loglevel", "warning"]
        cmd[-1:-1] = ["-rtsp_transport", "tcp"]
        return cmd

    def server_config(self) -> dict:
        upstream = yaml.safe_load((UPSTREAM / "rtsp/mediamtx.yml").read_text())
        return {"logLevel": "warn", "rtsp": True, "rtspTransports": ["tcp"],
                "rtspAddress": "127.0.0.1:" + str(self.config["rtsp_port"]),
                "hls": True, "hlsAddress": "127.0.0.1:" + str(self.config["hls_port"]),
                "hlsVariant": "mpegts", "hlsAllowOrigins": [],
                "webrtc": False, "rtmp": False, "srt": False, "api": False,
                "readTimeout": upstream["readTimeout"], "writeTimeout": upstream["writeTimeout"],
                "paths": {"stream": {"source": "publisher"}}}

    def start(self):
        with self.lock:
            if len(self.processes) == 2 and all(p.poll() is None for p in self.processes):
                return self.status()
            self.stop()
            check = self.preflight()
            if not check["ready"]:
                raise RuntimeError("; ".join(check["missing"]) or "Media is disabled; use --stream")
            for port in [self.config["rtsp_port"], self.config["hls_port"]]:
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", port))
            self.data.mkdir(parents=True, exist_ok=True)
            cfg = self.data / "mediamtx.yaml"
            cfg.write_text(yaml.safe_dump(self.server_config()))
            self.log = (self.data / "media.log").open("ab")
            try:
                server = subprocess.Popen([executable(self.config["mediamtx"]), str(cfg)], stdout=self.log, stderr=self.log)
                self.processes.append(server)
                deadline = time.monotonic() + 3
                while True:
                    if server.poll() is not None:
                        raise RuntimeError("MediaMTX exited; see .m10/media.log")
                    try:
                        with socket.create_connection(("127.0.0.1", self.config["rtsp_port"]), timeout=0.1):
                            break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError("MediaMTX did not open RTSP")
                        time.sleep(0.05)
                capture = subprocess.Popen(self.command(), stdout=self.log, stderr=self.log)
                self.processes.append(capture)
                time.sleep(0.2)
                if capture.poll() is not None:
                    raise RuntimeError("FFmpeg exited; see .m10/media.log")
                self.error = None
                return self.status()
            except Exception as exc:
                self.error = str(exc)
                self.stop()
                raise

    def stop(self):
        with self.lock:
            for process in reversed(self.processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            self.processes = []
            self.last_hls_at = None
            if self.log:
                self.log.close()
                self.log = None
            return self.status()

    def status(self):
        with self.lock:
            running = bool(self.processes) and all(p.poll() is None for p in self.processes)
            return {"enabled": self.config["enabled"], "running": running,
                    "preview_received": running and self.last_hls_at is not None,
                    "encoder": self.config["encoder"], "device": self.config["device"],
                    "url": "/stream/index.m3u8" if running else None, "error": self.error}
