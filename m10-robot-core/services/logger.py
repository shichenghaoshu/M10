from __future__ import annotations

import logging
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

RECENT_LOGS: deque[str] = deque(maxlen=200)


class RecentLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        RECENT_LOGS.append(self.format(record))


def setup_logger(base_path: Path) -> logging.Logger:
    log_dir = base_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "m10_robot_core.log"

    logger = logging.getLogger("m10_robot_core")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(log_file, maxBytes=1_048_576, backupCount=3)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    recent_handler = RecentLogHandler()
    recent_handler.setFormatter(formatter)
    logger.addHandler(recent_handler)

    return logger


def get_recent_logs(limit: int = 50) -> list[str]:
    if limit <= 0:
        return []
    return list(RECENT_LOGS)[-limit:]
