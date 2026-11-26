from __future__ import annotations

from pathlib import Path

import yaml


def test_config_contains_required_sections():
    config_path = Path(__file__).resolve().parents[1] / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    for key in ["device", "serial", "video", "display", "audio", "server", "web", "safety"]:
        assert key in config

    assert config["device"]["id"] == "m10-dev-001"
    assert config["serial"]["baudrate"] == 115200
