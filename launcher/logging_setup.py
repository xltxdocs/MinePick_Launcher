# SPDX-FileCopyrightText: 2026 WDNDXLTX
# SPDX-License-Identifier: GPL-3.0-only
#
# This file is part of MinePick Launcher.
#
# MinePick Launcher is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# MinePick Launcher is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with MinePick Launcher. If not, see <https://www.gnu.org/licenses/>.

"""Unified logging config: console (rich when available) + optional file."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOGGER_NAME = "launcher"


def configure_logging(
    verbose: bool = False, log_file: Path | None = None
) -> logging.Logger:
    """Configure the root logger (idempotent: reuse existing handlers)."""
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
    """Get a child logger under the launcher namespace."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)
