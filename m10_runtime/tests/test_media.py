import json
import hashlib
import io
import tarfile

import pytest

from m10_runtime.doctor import check_upstream
from m10_runtime.media import Media
from m10_runtime.settings import load_settings


def test_upstream_is_pinned_and_unmodified():
    assert check_upstream()["ready"]
    assert check_upstream()["commit"] == "c6d6b428322cf0311b0059f7d5bdd287b4bf65a2"


def test_capture_recipe_uses_profile_not_author_machine_paths(tmp_path):
    settings = load_settings("esp32")["media"]
    settings["device"] = "/dev/video42"
    settings["rtsp_port"] = 18554
    cmd = Media(settings, tmp_path).command()
    assert cmd[cmd.index("-i") + 1] == "/dev/video42"
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[-1] == "rtsp://127.0.0.1:18554/stream"
    assert "-rc_mode" not in cmd
    assert "-nostdin" in cmd


def test_media_stops_only_processes_it_owns(tmp_path):
    class Process:
        stopped = False
        def poll(self): return None if not self.stopped else 0
        def terminate(self): self.stopped = True
        def wait(self, timeout=None): return 0
    media = Media(load_settings("demo")["media"], tmp_path)
    one, two = Process(), Process()
    media.processes = [one, two]
    media.stop()
    assert one.stopped and two.stopped
    assert not media.status()["running"]


def test_media_listeners_are_local_and_paths_are_fixed(tmp_path):
    cfg = Media(load_settings("radxa")["media"], tmp_path).server_config()
    assert cfg["rtspAddress"].startswith("127.0.0.1:")
    assert cfg["hlsAddress"].startswith("127.0.0.1:")
    assert list(cfg["paths"]) == ["stream"]
    assert all(cfg[name] is False for name in ["webrtc", "rtmp", "srt", "moq", "api"])


@pytest.mark.parametrize("valid_checksum", [True, False])
def test_download_requires_checksum_and_extracts_only_expected_binary(tmp_path, monkeypatch, valid_checksum):
    from m10_runtime import media as module
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        content = b"test binary"
        member = tarfile.TarInfo("mediamtx")
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
        ignored = tarfile.TarInfo("../../outside")
        ignored.size = 1
        archive.addfile(ignored, io.BytesIO(b"x"))
    content = payload.getvalue()
    (tmp_path / "m10_runtime").mkdir()
    manifest = {"version": "test", "assets": {"amd64": {"url": "https://example.invalid/archive", "sha256": hashlib.sha256(content).hexdigest() if valid_checksum else "0" * 64}}}
    (tmp_path / "m10_runtime/media-assets.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(module.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(content))
    target = tmp_path / "bin/mediamtx"
    if valid_checksum:
        module.download_mediamtx(target)
        assert target.read_bytes() == b"test binary"
        assert not (tmp_path / "outside").exists()
    else:
        with pytest.raises(RuntimeError, match="SHA-256"):
            module.download_mediamtx(target)
        assert not target.exists()
