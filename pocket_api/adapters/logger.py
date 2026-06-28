import logging
import json
from datetime import datetime
from pathlib import Path

_LOG: logging.Logger | None = None


def setup_logger(log_dir: str | Path) -> logging.Logger:
    global _LOG
    path = Path(log_dir) / "pocket.log"
    path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("pocket")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    fh = logging.FileHandler(str(path), encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-5s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(fh)

    _LOG = logger
    return logger


def get_logger() -> logging.Logger:
    global _LOG
    if _LOG is None:
        return setup_logger("/tmp")
    return _LOG


def log_event(event: str, **kwargs):
    parts = [f"[{event}]"]
    for k, v in kwargs.items():
        if v is not None:
            parts.append(f"{k}={v}")
    get_logger().info("  ".join(parts))
