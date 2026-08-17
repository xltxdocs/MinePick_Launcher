"""统一日志配置：控制台（rich 可用时）+ 可选文件。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOGGER_NAME = "launcher"


def configure_logging(
    verbose: bool = False, log_file: Path | None = None
) -> logging.Logger:
    """配置根 logger（幂等：已有 handler 时直接复用）。"""
    logger = logging.getLogger(LOGGER_NAME)
    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)
    logger.propagate = False
    if logger.handlers:
        return logger

    try:
        from rich.logging import RichHandler

        console_handler: logging.Handler = RichHandler(
            rich_tracebacks=True, markup=True, show_time=False
        )
        console_handler.setLevel(level)
    except ImportError:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        console_handler.setLevel(level)
    logger.addHandler(console_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "") -> logging.Logger:
    """获取 launcher 命名空间下的子 logger。"""
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)
