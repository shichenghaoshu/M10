"""CI smoke check of the real pinned MediaMTX binary, without camera or motor."""
from __future__ import annotations

from pathlib import Path
import socket
import subprocess
import tempfile
import time

import yaml

from .media import Media, download_mediamtx
from .settings import ROOT, load_settings


def main():
    binary = ROOT / ".m10/bin/mediamtx"
    if not binary.exists():
        download_mediamtx(binary)
    settings = load_settings("demo")["media"]
    with socket.socket() as rtsp, socket.socket() as hls:
        rtsp.bind(("127.0.0.1", 0))
        hls.bind(("127.0.0.1", 0))
        settings["rtsp_port"] = rtsp.getsockname()[1]
        settings["hls_port"] = hls.getsockname()[1]
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        config = work / "mediamtx.yaml"
        config.write_text(yaml.safe_dump(Media(settings, work).server_config()))
        with (work / "log").open("wb") as log:
            process = subprocess.Popen([str(binary), str(config)], stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 5
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("MediaMTX rejected generated configuration: " + (work / "log").read_text())
                    try:
                        with socket.create_connection(("127.0.0.1", settings["rtsp_port"]), timeout=0.2) as peer:
                            peer.sendall(b"OPTIONS rtsp://127.0.0.1/stream RTSP/1.0\r\nCSeq: 1\r\n\r\n")
                            result = peer.recv(4096)
                            if b"RTSP/1.0 200" not in result:
                                raise RuntimeError("Unexpected RTSP response: " + repr(result))
                            break
                    except OSError:
                        if time.monotonic() > deadline:
                            raise RuntimeError("MediaMTX did not open RTSP")
                        time.sleep(0.05)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    print("PASS pinned MediaMTX + generated config + RTSP response (no camera/motor)")


if __name__ == "__main__":
    main()
