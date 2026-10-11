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

"""Opt-in observation of the status-line accessibility path - nothing here changes it.

A windowed build has no console, so the only way to see what the announcement path decided is a file.
Set ``MCLAUNCHER_A11Y_TRACE=1`` and every accessibility-relevant fact is appended to
``%TEMP%\\minepick_a11y_trace.log`` (override the path with ``MCLAUNCHER_A11Y_TRACE_FILE``):

- whether anything is listening (``QAccessible.isActive()``), every time it is asked, with the moment;
- every status change: old text -> new text, each gate's verdict, whether the message went out at all,
  and one verdict per carrier it was handed to (``channel_label_name``, ``channel_bar_name``,
  ``channel_label_announcement``) - so a message that is not heard can be traced to the carrier that
  was meant to carry it;
- the accessibility-related environment variables, so "was it forced silent?" is answerable.

The switch is off by default and off means *nothing happens*: no file, no extra queries, no retained
state. Every function here takes what it needs from the caller or from the environment, so reading the
trace cannot add a question the application would not otherwise have asked: ``recorded_isActive()``
is the single exception, and it exists so that the one query the gate needs is also the one recorded.

The verdicts recorded here are observations of the production gate, not a second copy of it: the gate
in ``gui.widgets`` stays the only place that decides whether an announcement is sent.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

TRACE_ENV = "MCLAUNCHER_A11Y_TRACE"
TRACE_FILE_ENV = "MCLAUNCHER_A11Y_TRACE_FILE"
DEFAULT_TRACE_NAME = "minepick_a11y_trace.log"

# Environment variables that decide whether the announcement can work at all, so the log answers
# "was it forced silent?" without asking the user to re-read their shell. The third one is the
# production escape hatch and is named by the module that owns it (gui.widgets owns that gate).
REPORTED_ENV = ("QT_ACCESSIBILITY", "QT_LINUX_ACCESSIBILITY_ALWAYS_ON")

_UNSET = "<unset>"
# Enough of a status message to recognise it, short enough that a progress line cannot flood the log.
_TEXT_LIMIT = 160
# Numbers the records written so far in this process, so the lines of one event stay identifiable.
_sequence = 0


def alert_env_name() -> str:
    """Name of the force-silence escape hatch, asked of the module that owns that gate."""
    try:
        from gui.widgets import A11Y_ALERT_ENV

        return A11Y_ALERT_ENV
    except Exception:  # noqa: BLE001 - the name is only ever used in log text
        return "MCLAUNCHER_NO_A11Y_ALERT"


def trace_enabled() -> bool:
    """True when ``MCLAUNCHER_A11Y_TRACE=1`` asked for the log. Read per call: no caching, no state."""
    return os.environ.get(TRACE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def trace_path() -> Path:
    """Where the log goes: ``MCLAUNCHER_A11Y_TRACE_FILE`` when set, else ``%TEMP%\\minepick_a11y_trace.log``."""
    override = os.environ.get(TRACE_FILE_ENV, "").strip()
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / DEFAULT_TRACE_NAME


def env_snapshot() -> dict[str, str]:
    """Current values of the accessibility-related environment variables (``<unset>`` when absent)."""
    names = (*REPORTED_ENV, alert_env_name())
    return {name: os.environ.get(name) or _UNSET for name in names}


def _env_fields() -> dict[str, str]:
    """The same snapshot keyed for a log line, so it travels inside one record rather than beside it."""
    return {f"env {name}": value for name, value in env_snapshot().items()}


def _text(value: str) -> str:
    """A status message as one log line: newlines collapsed, long messages truncated."""
    flat = " ".join(str(value or "").split())
    if len(flat) > _TEXT_LIMIT:
        return f"{flat[:_TEXT_LIMIT]}... ({len(flat)} chars)"
    return flat


def _stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _lines(tag: str, fields: dict[str, str]) -> list[str]:
    """One `timestamp | tag#n | name=value` line per fact: greppable, and diffable between runs.

    The ``#n`` numbers the records in write order, so the several lines that describe one event can be
    put back together as that event - and so a reader can follow the sequence without a timestamp diff.
    """
    global _sequence
    _sequence += 1
    return [f"{_stamp()} | {tag}#{_sequence} | {name}={value}" for name, value in fields.items()]


def _write(lines: list[str]) -> None:
    """Append already-formatted lines. Never raises: a diagnostic must not break a status update."""
    try:
        path = trace_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("".join(line + "\n" for line in lines))
    except Exception:  # noqa: BLE001 - diagnostics are optional, the launcher is not
        return


def _window_facts() -> dict[str, str]:
    """What Qt knows about this process's windows - the thing a screen reader actually attaches to.

    A probe run in an empty process answers ``isActive() == False`` for a reason that has nothing to
    do with the real window: no window, nothing to attach to. These counts make that visible.
    """
    unknown = {
        "platform_plugin": _UNSET,
        "top_level_windows": "0",
        "visible_top_level_windows": "0",
    }
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return unknown
        widgets = app.topLevelWidgets()
        return {
            "platform_plugin": str(app.platformName()) or _UNSET,
            "top_level_windows": str(len(widgets)),
            "visible_top_level_windows": str(sum(1 for w in widgets if w.isVisible())),
        }
    except Exception:  # noqa: BLE001 - written before Qt is fully usable sometimes
        return unknown


def _probe_isActive() -> bool:
    """Ask the same question the announcement gate asks, and report what Qt answered.

    This is a query, never a switch: it can only ever return what the gate would have seen anyway.
    The answer travels back to the caller so one question serves both the gate and the log.
    """
    try:
        from PySide6.QtGui import QAccessible

        return bool(QAccessible.isActive())
    except Exception:  # noqa: BLE001 - accessibility is optional, exactly as in the gate
        return False


def init(reason: str = "startup") -> Path | None:
    """Open the log (when enabled) and write the process header. Returns the path, or None when off.

    The header answers ``isActive()`` once so the log starts with the state of the process it belongs
    to. Off means off: nothing below runs, so no file and no query.
    """
    if not trace_enabled():
        return None
    path = trace_path()
    fields = {
        "reason": reason,
        "pid": str(os.getpid()),
        "argv0": Path(sys.argv[0]).name if sys.argv and sys.argv[0] else _UNSET,
        "frozen": str(bool(getattr(sys, "frozen", False))),
    }
    try:
        from PySide6.QtCore import qVersion

        fields["qt"] = qVersion()
    except Exception:  # noqa: BLE001 - the header must survive a Qt-less process
        fields["qt"] = _UNSET
    fields.update(_window_facts())
    fields["isActive_at_init"] = str(_probe_isActive())
    fields.update(_env_fields())
    _write(_lines("session", fields))
    return path


def recorded_isActive() -> bool:
    """Query ``isActive()`` once for the caller's gate *and* log the answer.

    With tracing off the query belongs to the caller and the answer is simply passed back: one
    environment lookup and the same single question Qt was already being asked. That is the whole
    measurement, and it is why the gate can call this unconditionally.
    """
    active = _probe_isActive()
    if not trace_enabled():
        return active
    fields = {"moment": "status change", "isActive": str(active)}
    fields.update(_window_facts())
    _write(_lines("isActive", fields))
    return active


def record_announce(
    phase: str,
    before: str,
    after: str,
    *,
    forced_silent: bool | None = None,
    reader_active: bool | None = None,
    sent: bool | None = None,
    channels: dict[str, str] | None = None,
    reason: str = "",
) -> None:
    """Log one status-change decision: the texts, each gate verdict, and the outcome.

    ``None`` for a gate means it was never consulted on this path - different from ``False``, which
    means it was asked and said no. That distinction is what separates "the gate closed" from "the
    decision never got that far".

    ``channels`` is what the send step did per carrier (``{"label_name": "sent", ...}``, see
    ``gui.widgets.A11Y_CHANNELS``), written as one ``channel_<name>=<verdict>`` field each. It is
    ``None`` on the paths that never reach the send step: when a gate closed there is no carrier to
    report on, and the gate verdict above is the whole answer. ``sent`` stays the summary - at least
    one carrier took the message - so the field means the same thing it always did.

    With the switch off this is the whole cost of the call: one environment lookup, then return. The
    keyword defaults exist so the call sites read the same whether or not anyone is reading the log.
    """
    if not trace_enabled():
        return
    _record_announce(phase, before, after, forced_silent, reader_active, sent, channels, reason)


def _record_announce(
    phase: str,
    before: str,
    after: str,
    forced_silent: bool | None,
    reader_active: bool | None,
    sent: bool | None,
    channels: dict[str, str] | None,
    reason: str,
) -> None:
    alert = alert_env_name()
    if forced_silent is None:
        silence = "not-consulted"
    elif forced_silent:
        silence = f"BLOCK (FORCED-SILENT by {alert}=1)"
    else:
        silence = f"PASS ({alert} not set)"
    if reader_active is None:
        reader = "not-consulted"
    elif reader_active:
        reader = "PASS (QAccessible.isActive() == True)"
    else:
        reader = "BLOCK (QAccessible.isActive() == False: no reader attached)"

    fields = {
        "before": repr(_text(before)),
        "after": repr(_text(after)),
        "gate1_force_silence": silence,
        "gate2_reader": reader,
        "sent": str(bool(sent)),
    }
    if reason:
        fields["why"] = reason
    # One line per carrier, in the order gui.widgets sends them, so two messages can be compared line
    # by line. A carrier that was skipped says why it was skipped, which is the difference between
    # "nothing can carry it here" and "it went out and was still not heard".
    for channel, verdict in (channels or {}).items():
        fields[f"channel_{channel}"] = verdict
    fields.update(_env_fields())
    _write(_lines(f"announce/{phase}", fields))
