from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(level: int = logging.INFO) -> None:
    Path("data").mkdir(exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
