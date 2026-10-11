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

"""Shared widget helpers: no-focus-outline views, no-wheel controls and a global wheel blocker."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QObject, Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QSizePolicy,
    QSpinBox,
    QStatusBar,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTabBar,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui import a11y_trace


class NoFocusDelegate(QStyledItemDelegate):
    """List/table delegate: remove the HasFocus state when painting so the style engine stops drawing the focus rectangle."""

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        super().initStyleOption(option, index)
        option.state &= ~QStyle.StateFlag.State_HasFocus


def apply_no_focus_outline(view) -> None:
    """Apply a no-focus-outline delegate and smooth pixel scrolling to list/table views.

    Pixel scrolling keeps the wheel from moving the current item: with the
    default per-item scroll mode, scrolling "selects" whichever item ends up
    under the cursor.
    """
    view.setItemDelegate(NoFocusDelegate(view))
    for method in ("setVerticalScrollMode", "setHorizontalScrollMode"):
        setter = getattr(view, method, None)
        if setter is not None:
            setter(QAbstractItemView.ScrollMode.ScrollPerPixel)
    attach_hover_scrollbar(view)


def name_table_for_screen_readers(table, name: str) -> None:
    """Give a table view *and* its header a readable accessible name (WCAG 4.1.2).

    A table is a keyboard stop - Tab reaches it and the arrow keys move inside it - but it has no text
    of its own, so a screen reader announces "table" with no indication of what it holds. The header is
    a stop of its own as well (it is what makes column sorting reachable from the keyboard), and it
    reports the hovered/selected *column title* as its accessible name, which names the column rather
    than the table; without its own name a reader lands on the header with no context at all.

    Call this before or after ``setHorizontalHeaderLabels`` / ``setModel`` - it only sets names, it
    never reads the headers, so it cannot depend on their content.
    """
    table.setAccessibleName(name)
    header = table.horizontalHeader()
    if header is not None:
        header.setAccessibleName(name)


def disable_keeping_focus(button) -> None:
    """Disable a button that just started work without handing focus to another control.

    Qt moves focus to the next widget in the focus chain when the focused widget becomes
    disabled. That dropped the caret into unrelated text fields (clicking "Microsoft sign-in"
    put it in the offline username box) and even parked focus on a destructive button (after
    "install" on the versions page it landed on "uninstall", where a stray Enter would remove
    the version). Giving up focus first leaves no widget focused instead.
    """
    if button.hasFocus():
        button.clearFocus()
    button.setEnabled(False)


class NoWheelSpinBox(QSpinBox):
    """Spin box that ignores the mouse wheel so scrolling the page never changes its value."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """Double spin box that ignores the mouse wheel so scrolling the page never changes its value."""

    def wheelEvent(self, event) -> None:
        event.ignore()


class WheelBlocker(QObject):
    """Application-wide event filter.

    Blocks wheel input on controls that react to it (combo boxes, spin boxes,
    tab bars) so the mouse wheel only scrolls page content such as lists, tables
    and scroll areas.

    Open dropdown lists are the one exception: they must stay wheel-scrollable,
    otherwise long lists (every installed font family, for instance) cannot be
    reached at all. The closed combo itself still ignores the wheel, so scrolling
    a page past a combo never changes its value.
    """

    _WHEEL_REACTIVE = (QComboBox, QSpinBox, QDoubleSpinBox, QTabBar)

    @staticmethod
    def _is_dropdown_view(view) -> bool:
        """True for an item view that belongs to a combo box (its dropdown list)."""
        if view.windowFlags() & Qt.WindowType.Popup:
            return True
        node = view.parent()
        while node is not None:
            if isinstance(node, QComboBox):
                return True
            node = node.parent()
        return False

    @classmethod
    def _is_open_dropdown_list(cls, obj) -> bool:
        """True when the wheel targets a dropdown list: the view, its viewport or its popup."""
        node = obj
        while node is not None:
            if isinstance(node, QAbstractItemView) and cls._is_dropdown_view(node):
                return True
            node = node.parent()
        return False

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.Wheel:
            return False
        if self._is_open_dropdown_list(obj):
            return False  # let the dropdown list scroll
        node = obj
        while node is not None:
            if isinstance(node, self._WHEEL_REACTIVE):
                event.ignore()
                # The wheel would otherwise hand the control focus (Qt WheelFocus),
                # which paints the green focus border: drop that focus again.
                if node.hasFocus():
                    node.clearFocus()
                return True
            node = node.parent()
        return False


A11Y_ALERT_ENV = "MCLAUNCHER_NO_A11Y_ALERT"

# The carriers one status message travels on, in the order they are sent. A screen reader that ignores
# one of them can still hear the message on another, and the trace (MCLAUNCHER_A11Y_TRACE=1) writes one
# verdict per carrier under its name - so "did the message leave at all, and on which carrier?" is a
# question the log answers per message instead of in aggregate.
#
# There is deliberately no alert carrier here, and adding one back would undo this feature. On Windows
# Qt's accessibility bridge calls PlaySound for exactly three events - PopupMenuStart, MenuCommand and
# QAccessible::Alert - and an alert on a widget that is not a QMessageBox plays the "SystemAsterisk"
# sound, reader attached or not (QWindowsUiaAccessibility::notifyAccessibilityUpdate). The event the
# status line used to send was therefore the one and only thing that made the launcher chime once per
# status message, while reaching no reader at all: that same bridge forwards the name change only for
# combo boxes and focused elements, and an alert is not among the events it forwards for static text.
# The announcement is carried by QAccessibleAnnouncementEvent instead - Windows maps that to a UI
# Automation notification, which is the channel Narrator reads out, and Qt never turns it into a sound.
# That is WCAG 4.1.3's "available to assistive technology" with none of the system noise; the test
# test_no_alert_event_can_creep_back_into_the_source is what holds the decision in place.
A11Y_CHANNEL_LABEL_NAME = "label_name"  # NameChanged on the label: its text is its accessible name
A11Y_CHANNEL_BAR_NAME = "bar_name"  # the status bar's accessible name, and NameChanged on the bar
A11Y_CHANNEL_LABEL_ANNOUNCEMENT = "label_announcement"  # QAccessibleAnnouncementEvent (Qt 6.8+)
A11Y_CHANNELS = (
    A11Y_CHANNEL_LABEL_NAME,
    A11Y_CHANNEL_BAR_NAME,
    A11Y_CHANNEL_LABEL_ANNOUNCEMENT,
)
A11Y_SENT = "sent"
# Not failures: a bare StatusLabel (page tests, render tools) has no status bar to name, and the
# announcement event only exists from Qt 6.8 on while the project allows PySide6 >= 6.6.
A11Y_SKIPPED_NO_BAR = "skipped (no QStatusBar host)"
A11Y_SKIPPED_OLD_QT = "skipped (needs Qt 6.8: no QAccessibleAnnouncementEvent)"


def a11y_alerts_enabled() -> bool:
    """False when ``MCLAUNCHER_NO_A11Y_ALERT=1`` forces the announcements off.

    The escape hatch, not the normal path: read on every call so it can be flipped without a rebuild.
    The normal path is assistive_tech_is_active() below.
    """
    import os

    return os.environ.get(A11Y_ALERT_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}


def assistive_tech_is_active() -> bool:
    """Whether anything is actually listening to accessibility events.

    False - the usual case - means no screen reader is running, and then an announcement buys nothing:
    nothing consumes the events that would be sent. The gate exists because of what used to be sent -
    an alert, the one event Qt's Windows accessibility bridge answers with a system sound whether or
    not a reader is attached - which is what made the launcher chime on startup, on exit and during
    the first-run wizard, the three moments the status line changes. That event is no longer sent at
    all (see the carrier list above and StatusLabel._send_channels); the gate stays as the single
    switch the whole announcement path is documented and tested against, and because sending to nobody
    is still work nobody asked for. With a reader running the announcement is sent exactly as before,
    so WCAG 4.1.3 is unaffected.

    Any failure here means "no reader": accessibility must never break a status update.
    """
    # The same single question, asked through the trace module so that MCLAUNCHER_A11Y_TRACE=1 can
    # record it. With the trace off this is one environment lookup plus the Qt call itself.
    return a11y_trace.recorded_isActive()


def _status_bar_host(widget):
    """The QStatusBar ``widget`` sits in, or None when it is not hosted on one.

    None is an ordinary answer, not a failure: page-level tests and the offscreen render tools build a
    bare StatusLabel, and the carrier that needs a status bar is then skipped while the others still
    carry the message. Only an ancestor is accepted - ``window().statusBar()`` would *create* a status
    bar on a window that never asked for one.
    """
    try:
        node = widget.parentWidget() if hasattr(widget, "parentWidget") else None
        while node is not None:
            if isinstance(node, QStatusBar):
                return node
            node = node.parentWidget()
    except RuntimeError:  # a half-destroyed C++ object: no host, so no carrier
        return None
    return None


def _channel_failed(exc: BaseException) -> str:
    """One carrier's verdict after it raised: named, so the log says which one broke and how."""
    return f"error ({type(exc).__name__})"


def _attempt(record: dict[str, str], channel: str, send) -> None:
    """Send on one carrier, writing the verdict down instead of letting it break the status update.

    A carrier that raises is recorded and the remaining ones still go out: several carriers exist
    precisely so that one broken or unsupported one cannot silence the status line. Accessibility is
    optional; the status update is not.
    """
    try:
        send()
    except Exception as exc:  # noqa: BLE001 - accessibility is optional: never break a status update
        record[channel] = _channel_failed(exc)
    else:
        record[channel] = A11Y_SENT


def _announcement_event(obj, text: str):
    """Qt's announcement request for ``text``, or None on a Qt that has no such event.

    ``QAccessibleAnnouncementEvent`` and ``QAccessible::Announcement`` arrived in Qt 6.8; the launcher
    allows PySide6 >= 6.6, so "this Qt cannot announce" is an expected state rather than an error, and
    the other carriers carry the message there.
    """
    try:
        from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent
    except ImportError:
        return None
    event = QAccessibleAnnouncementEvent(obj, text)
    politeness = getattr(QAccessible, "AnnouncementPoliteness", None)
    if politeness is not None:
        # Polite is what a status line wants and what the constructor defaults to: on Windows it maps
        # to NotificationProcessing_All, which queues the message instead of interrupting what the
        # reader is saying - the same "never talk over the reader" rule the once-per-message rule
        # follows.
        event.setPoliteness(politeness.Polite)
    return event


class StatusLabel(QLabel):
    """Status text whose colour follows the severity of the last message.

    ``setText`` always returns to the neutral look, so a red error message never
    sticks: the next ordinary message (progress, "done") is muted again. This keeps
    every existing ``setText`` call site unchanged and only marks the failures.

    Every visible change is also announced to assistive technology (WCAG 4.1.3). Qt has no live
    region, so a screen reader would otherwise never learn that the status line changed - it only
    reads the label when the user navigates to it. The announcement is sent once per distinct text:
    the worker pool sets progress messages repeatedly, and repeating an identical announcement would
    only talk over the reader. Severity travels in the message wording itself ("import failed: ..."),
    which is why severity needs no carrier of its own.

    The message leaves on several carriers, not one (see ``_send_channels``): a carrier that a given
    screen reader does not consume costs nothing, while a single one that it ignores loses the message.
    """

    _level = "info"  # severity of the text on display, updated by every setter
    _announced = ""  # last text announced to assistive technology

    def setText(self, text: str) -> None:  # Qt's slot name, kept camelCase on purpose
        self._apply_level("info")
        super().setText(text)
        self._announce(text)

    def set_error(self, text: str) -> None:
        self._apply_level("error")
        super().setText(text)
        self._announce(text)

    def set_warning(self, text: str) -> None:
        self._apply_level("warning")
        super().setText(text)
        self._announce(text)

    def current_level(self) -> str:
        """Severity of the message on display: "info", "warning" or "error"."""
        return self._level

    def _announce(self, text: str) -> None:
        """Tell assistive technology the status line changed - once per distinct message.

        The decision is unchanged; ``MCLAUNCHER_A11Y_TRACE=1`` only writes down what it decided and
        why (``gui.a11y_trace``). With the switch off the trace module reports "off" from one
        environment lookup and is never touched again, so every branch below behaves as before.

        The gates decide *whether* a message is announced, and they are the only thing that does:
        ``MCLAUNCHER_NO_A11Y_ALERT=1`` first, then ``QAccessible.isActive()``. What changed is only how
        many carriers the one announcement is handed to once both gates have passed.
        """
        text = text or ""
        if text == self._announced:
            return
        before = self._announced
        self._announced = text
        if not text:
            # Clearing the status line is not a status message; nothing to observe, nothing to say.
            return
        if not a11y_alerts_enabled():
            # The escape hatch: recorded so the log can tell this silence apart from "no reader".
            a11y_trace.record_announce(
                "blocked", before, text, forced_silent=True, reason=f"{A11Y_ALERT_ENV} forces silence"
            )
            return
        # One query serves both the gate and the log: the gate's answer, written down.
        active = a11y_trace.recorded_isActive()
        if not active:
            # Nobody is listening, and the event would still make Windows play the alert sound.
            a11y_trace.record_announce(
                "blocked", before, text, forced_silent=False, reader_active=False
            )
            return
        try:
            channels = self._send_channels(text)
        except Exception as exc:  # noqa: BLE001 - the promise the single send used to keep
            channels = {channel: _channel_failed(exc) for channel in A11Y_CHANNELS}
        # "sent" means at least one carrier took the message; the per-carrier verdicts say which.
        sent = A11Y_SENT in channels.values()
        a11y_trace.record_announce(
            "sent" if sent else "error",
            before,
            text,
            forced_silent=False,
            reader_active=True,
            sent=sent,
            channels=channels,
        )

    def _send_channels(self, text: str) -> dict[str, str]:
        """Hand one message to every carrier that can reach assistive technology; report each verdict.

        Three carriers, none of them the alert the first implementation sent - that one is gone on
        purpose and must not come back, for two reasons that both come from Qt's Windows backend
        (``QWindowsUiaAccessibility::notifyAccessibilityUpdate``):

        * it is the only accessibility event that backend turns into a sound. ``PlaySound`` runs for
          ``PopupMenuStart``, ``MenuCommand`` and ``QAccessible::Alert``, and an alert on a widget that
          is not a QMessageBox plays the "SystemAsterisk" sound - so with a reader attached every
          distinct status message chimed;
        * it reaches no reader on Windows: an alert is not one of the events that backend forwards for
          a static text widget, while the name change is forwarded only for combo boxes and focused
          elements. It made the noise and carried nothing.

        The broadcast - WCAG 4.1.3 wants the message available to assistive technology - is carried by
        ``QAccessibleAnnouncementEvent`` instead, which Windows maps to a UI Automation notification
        (the channel Narrator reads out) and which Qt never maps to a sound. The message travels as:

        * ``label_name`` - a QLabel's accessible name *is* its text, so NameChanged is the event that
          says "the thing this object stands for changed". Qt itself sends this one from
          ``QLabel::setText``, which is the strongest argument that it is the semantically right
          event; sending it here does not depend on that internal behaviour staying.
        * ``bar_name`` - the status bar receives the same sentence as its accessible name, plus
          NameChanged for it. This is what turns the message into *the status bar's message*: a
          reader that lands on the container reads the sentence instead of an unnamed structure,
          which is the exact complaint the trace run produced ("it read the status bar, not the
          text").
        * ``label_announcement`` - ``QAccessibleAnnouncementEvent``, the one event Qt documents as a
          request to announce this message. On Windows Qt forwards it as a UI Automation
          notification, which is the carrier Narrator consumes for spoken status text; it is the only
          carrier here that a reader is asked to *speak* rather than to re-read.

        Ordered, and always all three keys: the log then reads the same for every message. Each
        carrier is attempted on its own, so an unsupported or failing one is recorded rather than
        allowed to stop the others. None of the three is an event Qt plays a sound for, so an
        announcement can never make Windows chime.
        """
        try:
            from PySide6.QtGui import QAccessible, QAccessibleEvent
        except Exception as exc:  # noqa: BLE001 - no Qt accessibility at all: every carrier fails alike
            return {channel: _channel_failed(exc) for channel in A11Y_CHANNELS}

        record: dict[str, str] = {}

        def update(event) -> None:
            QAccessible.updateAccessibility(event)

        _attempt(
            record,
            A11Y_CHANNEL_LABEL_NAME,
            lambda: update(QAccessibleEvent(self, QAccessible.Event.NameChanged)),
        )

        bar = _status_bar_host(self)
        if bar is None:
            record[A11Y_CHANNEL_BAR_NAME] = A11Y_SKIPPED_NO_BAR
        else:

            def name_the_status_bar() -> None:
                # Name first, event second: a reader that reacts to the event reads the name, not what
                # it was a moment ago.
                bar.setAccessibleName(text)
                update(QAccessibleEvent(bar, QAccessible.Event.NameChanged))

            _attempt(record, A11Y_CHANNEL_BAR_NAME, name_the_status_bar)

        try:
            announcement = _announcement_event(self, text)
        except Exception as exc:  # noqa: BLE001 - a Qt type that will not build is a missing carrier
            record[A11Y_CHANNEL_LABEL_ANNOUNCEMENT] = _channel_failed(exc)
        else:
            if announcement is None:
                record[A11Y_CHANNEL_LABEL_ANNOUNCEMENT] = A11Y_SKIPPED_OLD_QT
            else:
                _attempt(record, A11Y_CHANNEL_LABEL_ANNOUNCEMENT, lambda: update(announcement))
        return record

    def _apply_level(self, level: str) -> None:
        self._level = level
        name = {"error": "statusError", "warning": "statusWarning"}.get(level, "hint")
        if self.objectName() == name:
            return
        self.setObjectName(name)
        style = self.style()
        style.unpolish(self)
        style.polish(self)


def _status_host(widget):
    """Nearest host of the app-wide status line: the widget's window, or an ancestor's.

    A modal dialog (for example the mod version picker) is a top-level window of its
    own, so ``widget.window()`` alone would find no host and the message would be lost:
    walking the parent chain reaches the main window standing behind the dialog.
    """
    node = widget
    while node is not None:
        # A destroyed C++ object raises RuntimeError on any attribute access; a worker
        # callback that lands after its page was torn down must never crash the app, so
        # every step of the walk is guarded and a dead object ends the search.
        if not _is_alive(node):
            return None
        try:
            window = node.window() if hasattr(node, "window") else None
            if window is not None and (
                callable(getattr(window, "set_status", None))
                or getattr(window, "status_label", None) is not None
            ):
                return window
            node = node.parent() if hasattr(node, "parent") else None
        except RuntimeError:
            return None
    return None


def widget_alive(widget) -> bool:
    """False once Qt has destroyed the underlying C++ object (shiboken6 knows).

    A worker result can arrive after its page was closed or torn down; every callback that
    writes widgets must check this first, otherwise it dereferences a freed C++ object.
    """
    try:
        import shiboken6

        return shiboken6.isValid(widget)
    except Exception:  # noqa: BLE001 - shiboken missing or non-Qt object: assume alive
        return True


_is_alive = widget_alive  # internal alias kept for the traversal above


def set_app_status(widget, text: str, level: str | None = None) -> None:
    """Report a page message on the window's single status line.

    The pages own no status label any more: the main window hosts one severity-aware
    line in its status bar (``status_label``) and exposes ``set_status(text, level)``.
    Anything else that embeds a page (offscreen render tools, widget-level unit tests)
    has no such host, so this is a safe no-op there.

    A worker callback can land after its page was destroyed; the traversal and the write
    are therefore guarded so a dead C++ object degrades to a dropped message instead of a
    crash (shiboken raises RuntimeError, and a half-destroyed object can fault natively).
    """
    try:
        host = _status_host(widget)
        if host is None:
            return
        setter = getattr(host, "set_status", None)
        if callable(setter):
            setter(text, level)
            return
        label = host.status_label
        if level == "error":
            label.set_error(text)
        elif level == "warning":
            label.set_warning(text)
        else:
            label.setText(text)
    except RuntimeError:
        return


def build_page_header(title: str, subtitle: str) -> QWidget:
    """Page header: a big title plus one line describing what the page is for."""
    box = QWidget()
    box.setObjectName("pageHeader")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 2)
    layout.setSpacing(1)
    title_label = QLabel(title)
    title_label.setObjectName("pageTitle")
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("pageSubtitle")
    subtitle_label.setWordWrap(True)
    layout.addWidget(title_label)
    layout.addWidget(subtitle_label)
    return box


def style_page_layout(layout) -> None:
    """One spacing scale for every page: 14px outer margin, 8px between blocks."""
    layout.setContentsMargins(14, 12, 14, 6)
    layout.setSpacing(8)


def style_form(form) -> None:
    """One spacing scale for every form: label/value gap and row gap."""
    form.setContentsMargins(0, 0, 0, 0)
    form.setHorizontalSpacing(16)
    form.setVerticalSpacing(8)


def add_search_icon(line_edit) -> None:
    """Leading magnifier icon inside a search field."""
    from PySide6.QtGui import QIcon

    from launcher import paths

    icon_path = paths.resource_path("gui/resources/search.png")
    if icon_path.exists():
        line_edit.addAction(QIcon(str(icon_path)), QLineEdit.LeadingPosition)


class ElidedLabel(QLabel):
    """One-line label that paints its text elided in the middle, keeping the full value.

    Qt has no elide mode for QLabel, and a word-wrapped value inside a QFormLayout keeps the
    row at its unwrapped height, which clipped long paths (measured on the instance overview:
    the effective game directory was cut off by the next row). Painting an elided form keeps
    every row exactly one line tall, while `text()` still returns the logical value and the
    tooltip plus text selection keep the whole string reachable.
    """

    def __init__(
        self,
        text: str = "",
        parent=None,
        elide_mode: Qt.TextElideMode = Qt.TextElideMode.ElideMiddle,
    ) -> None:
        super().__init__(parent)
        self._full_text = ""
        self._elide_mode = elide_mode
        self.setWordWrap(False)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # Ignore the (long) size hint so the surrounding layout hands over the real width
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._apply_elide()

    def text(self) -> str:
        """The logical (unelided) value — what tests and callers expect from text()."""
        return self._full_text

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        metrics = self.fontMetrics()
        width = max(0, self.width() - 2)
        super().setText(
            metrics.elidedText(self._full_text, self._elide_mode, width)
        )


class EmptyState(QLabel):
    """Muted hint shown instead of an empty list/table, hidden as soon as data arrives."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("emptyState")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setVisible(False)

    def update_for(self, count: int) -> None:
        self.setVisible(count == 0)


class _ScrollBarHoverFilter(QObject):
    """Reveals the owning scroll area's slim scrollbar while the pointer is inside it."""

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Enter:
            _set_scrollbars_active(obj, True)
        elif event.type() == QEvent.Type.Leave:
            _set_scrollbars_active(obj, False)
        return False


def _set_scrollbars_active(source, active: bool) -> None:
    node = source
    while node is not None and not isinstance(node, QAbstractScrollArea):
        node = node.parent()
    if node is None:
        return
    for bar in (node.verticalScrollBar(), node.horizontalScrollBar()):
        if bar is None or bool(bar.property("active")) == active:
            continue
        bar.setProperty("active", active)
        style = bar.style()
        style.unpolish(bar)
        style.polish(bar)


def attach_hover_scrollbar(area) -> None:
    """Install the hover filter on a scroll area (and its viewport)."""
    hover_filter = _ScrollBarHoverFilter(area)
    targets = [area]
    viewport_getter = getattr(area, "viewport", None)
    if callable(viewport_getter):
        targets.append(area.viewport())
    for target in targets:
        target.installEventFilter(hover_filter)
    area._hover_scrollbar_filter = hover_filter  # keep the filter alive


class KeyboardFocusTracker(QObject):
    """Marks a focused control when focus came from the keyboard.

    Qt also paints focus for mouse clicks, which this launcher suppresses so the
    interface stays flat; this restores an indicator for keyboard users only.

    The flag means "the most recent input was the keyboard", not "a key was pressed at some point in
    this session". That distinction is the whole feature: a click focuses its target, so keeping the
    stale answer marks a widget the mouse just reached, and once the session had seen a single key
    press - typing in a search box, a space on a checkbox, a Tab - every later mouse click drew a ring
    again. Two things make it hold:

    * a mouse event clears the answer *and* the mark already on the focused control, because Qt tells
      the interface about the new focus **before** it delivers the click. Measured on a click from a
      line edit to the sidebar: ``FocusIn`` on the sidebar, and only then ``MouseButtonPress`` (on the
      scroll area viewport). Marking on that FocusIn and clearing the flag afterwards would leave the
      ring lit with nothing left to take it down - the exact mouse-visible ring this class exists to
      prevent;
    * the widget is restyled on the spot, the same way ``_mark`` does it, so the ring goes out in the
      same event as the click instead of waiting for the next focus change.

    Purely passive pointer movement is deliberately not an input answer: a MouseMove or a HoverMove
    says where the pointer is, not how the user is driving the interface, and the original QSS concern
    (a keyboard user must always see where focus is) would break as soon as the pointer drifted across
    a Tab-focused control. Presses, double clicks, releases, wheel, touch and tablet input do count.
    """

    # Every control family whose stylesheet focus ring is gated on this property. A family missing here
    # never gets marked, so its rule can never match and the control looks the same focused and
    # unfocused - QCheckBox was missing, which is what nine checkboxes across the settings, instance and
    # versions pages looked like: focusable, and with no focus cue at all when reached by Tab.
    _INTERACTIVE = (
        QAbstractButton,  # QCheckBox, QRadioButton, QPushButton and their subclasses
        QAbstractItemView,
        QAbstractScrollArea,  # scroll areas carry a keyboard-only ring of their own
        QAbstractSpinBox,
        QComboBox,
        QLineEdit,
        QPlainTextEdit,
        QTabWidget,  # the resource tabs: the widget is the stop, its tab bar draws the tabs
        QTextEdit,
    )

    # The mouse answering "not the keyboard any more". Releases are in the list because a press can be
    # swallowed by a widget that then never marks anything, while its release still belongs to the same
    # mouse action; DoubleClick is a click the press-only rule would miss entirely.
    _MOUSE_INPUT = (
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.MouseButtonRelease,
        QEvent.Type.Wheel,
        QEvent.Type.TouchBegin,
        QEvent.Type.TabletPress,
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._keyboard = False
        # Controls currently carrying the mark. Usually one (the focused control) or none, and a
        # mouse event is what walks it. A list rather than a set: identity is what matters, and a
        # handful of entries compares faster by identity than by hash.
        self._marked: list = []

    def eventFilter(self, obj, event) -> bool:
        kind = event.type()
        if kind == QEvent.Type.KeyPress:
            self._keyboard = True
        elif kind in self._MOUSE_INPUT:
            self._clear_marks()
            self._keyboard = False
        elif kind == QEvent.Type.FocusIn and isinstance(obj, self._INTERACTIVE):
            self._mark(obj, self._keyboard)
        elif kind == QEvent.Type.FocusOut and isinstance(obj, self._INTERACTIVE):
            self._mark(obj, False)
        return False

    def _mark(self, widget, active: bool) -> None:
        # Marks the control and, while the mark is on, remembers it as the one a mouse event has to take
        # it off again. A widget that was already in the asked-for state is left completely alone:
        # unpolish/polish on every focus change repainted controls for no reason (and, for a view,
        # dropped invisible work into the event loop that the tests then had to pump).
        #
        # A queued FocusOut can arrive after the C++ side of the widget is already gone - during
        # shutdown, or when the garbage collector reclaims a window the tests are finished with.
        # Touching such a wrapper took the whole process down with an access violation (Fatal Python
        # error: Aborted), reproducibly in the full suite and never in a single test file, because only
        # a long run lines the destruction up with the queued event. Every access is guarded; a widget
        # that is still alive behaves exactly as before.
        try:
            import shiboken6

            if not shiboken6.isValid(widget):
                return
            if bool(widget.property("keyboardFocus")) == active:
                return
            widget.setProperty("keyboardFocus", active)
            if active:
                if not any(w is widget for w in self._marked):
                    self._marked.append(widget)
            else:
                self._marked = [w for w in self._marked if w is not widget]
            style = widget.style()
            if style is None:
                return
            style.unpolish(widget)
            style.polish(widget)
        except Exception:  # noqa: BLE001 - an event filter must never raise into Qt's dispatch
            # The widget died between the validity check and the call, or it has no QWidget behaviour to
            # restyle. Either way there is nothing left to mark, and an event filter must never raise
            # into Qt's dispatch. Deliberately not narrowed to RuntimeError: the failures this is here
            # for (a half-destroyed wrapper, an object that is not a widget at all) do not all arrive
            # as RuntimeError.
            return

    def _clear_marks(self) -> None:
        """Take the keyboard mark off every control still carrying it, right now.

        Called when a mouse event says the answer is no longer "keyboard" - the flag is still the old
        answer at this point, which is what tells the two cases apart below.

        Qt reports the new focus before the click that caused it (FocusIn on the sidebar, then
        MouseButtonPress), so the widget the mouse just reached can already be marked by the time the
        click arrives: clearing only the flag would leave that ring lit until something else moved focus.
        Restyling here is what makes the ring go out with the mouse event itself.

        Only widgets this tracker marked are touched, and only their ``keyboardFocus`` property - not
        their focus, geometry or visibility - which is what keeps the unfocused rendering byte-for-byte
        what it was (the property is what the QSS ring is gated on, and nothing else reads it).

        The focused widget is checked even when the list does not hold it, so a mark that arrived some
        other way - an object this tracker never marked, or a property set by hand - cannot outlive the
        keyboard mode either. That extra check runs only when the answer really is changing, so a mouse
        event during keyboard navigation cannot take a mark off the control the user is tabbing through.
        """
        changing = self._keyboard
        for widget in list(self._marked):
            self._forget(widget)
        focused = QApplication.focusWidget() if changing and QApplication is not None else None
        if focused is not None:
            self._forget(focused)

    def _forget(self, widget) -> None:
        """Clear one widget's mark, drop it from the list, and never raise into Qt's dispatch."""
        self._marked = [w for w in self._marked if w is not widget]
        try:
            import shiboken6

            if not shiboken6.isValid(widget):
                return
            if not bool(widget.property("keyboardFocus")):
                return
            widget.setProperty("keyboardFocus", False)
            style = widget.style()
            if style is None:
                return
            style.unpolish(widget)
            style.polish(widget)
        except Exception:  # noqa: BLE001 - see _mark: a dead widget must not break the filter
            return


# The percentage label's box, in px. Wide enough for "100%" at the 11px the stylesheet sets, so the
# digits never push the bar around while the number goes from 0 to 100.
PROGRESS_TEXT_MIN_WIDTH = 44


def build_download_progress(name: str) -> tuple[QWidget, QProgressBar, QLabel]:
    """A download progress row. Returns ``(row, bar, label)``.

    The percentage used to be painted by Qt *inside* the bar, and that surface is not one colour: the
    chunk grows from the left, so a centred "45%" sits on the unfilled background while "55%" sits on
    the accent fill, and past the middle the text straddles both halves of the bar at once. Measured on
    the real platform (tools/measure_progress_text.py), the stylesheet's ``FG_HINT`` text over the
    accent chunk is 1.26:1 in the dark theme and 1.93:1 in the light one - against WCAG AA's 4.5:1 for
    body text. No single colour fixes it: ACCENT is a saturated mid-tone, so a foreground bright enough
    for it is invisible on the dark unfilled half, and one dark enough for that half disappears on the
    fill. The accent is also user-chosen - the settings page offers eight presets, each with its own
    luminance - so no token can be picked to make the two halves agree.

    So the text leaves the moving surface instead of chasing it: it moves one slot to the right, onto
    the static ``BG_LIST`` the row already uses. ``FG_HINT`` there is 6.48:1 in both themes and holds
    for every accent preset, because an accent can no longer reach it. The stylesheet gives the label
    the bar's own fill and border and the right half of its outline, and the layout uses zero spacing
    and no margins, so the pair still reads as one control.

    The two are wrapped in one plain container on purpose: every caller already shows and hides the bar
    when its download starts and ends, and a single widget keeps that working unchanged while the two
    can never drift apart - the label follows the bar's visibility by itself. ``text()`` on the bar is
    still the same percentage, and the bar is still reachable with ``findChild``/``findChildren``, so
    nothing that reads the value is affected.
    """
    row = QWidget()
    row.setContentsMargins(0, 0, 0, 0)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    bar = QProgressBar()
    bar.setObjectName(name)
    # Qt's own text would land on the accent fill; the label carries it instead.
    bar.setTextVisible(False)
    bar.setAccessibleName(name)
    label = QLabel()
    label.setObjectName(f"{name}Text")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setMinimumWidth(PROGRESS_TEXT_MIN_WIDTH)
    label.setVisible(False)
    layout.addWidget(bar, 1)
    layout.addWidget(label)

    def show_value(value: int) -> None:
        # The same scale every progress bar is driven with: setRange(0, 1000), a tenth of a percent a step.
        label.setText(f"{round(value / 10)}%")

    def follow_visibility(shown: bool) -> None:
        label.setVisible(shown)

    bar.valueChanged.connect(show_value)
    show_value(bar.value())
    row.installEventFilter(_VisibilityFollower(row, label, follow_visibility))
    row.setVisible(False)
    return row, bar, label


class _VisibilityFollower(QObject):
    """Keeps a sibling in step with the widget it belongs to (see build_download_progress).

    A container's own ``show``/``hide`` is what every caller already drives, so listening to it costs
    no call-site changes and cannot be forgotten at a new one. ``isVisibleTo(parent)`` is the state the
    callers mean: it ignores whether an ancestor is on screen yet, which matters because these pages are
    built before their window is.
    """

    def __init__(self, watched: QWidget, sibling: QWidget, apply) -> None:
        super().__init__(watched)
        self._sibling = sibling
        self._apply = apply

    def eventFilter(self, obj, event) -> bool:
        if event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
            try:
                import shiboken6

                if not shiboken6.isValid(self._sibling):
                    return False
            except Exception:  # noqa: BLE001 - a filter must never raise into Qt's dispatch
                return False
            self._apply(obj.isVisibleTo(obj.parentWidget()))
        return False


class NumericTableItem(QTableWidgetItem):
    """Table item that sorts by a number instead of the displayed text (8 before 21)."""

    def __init__(self, text: str, value: float) -> None:
        super().__init__(text)
        self._value = value

    def __lt__(self, other) -> bool:
        if isinstance(other, NumericTableItem):
            return self._value < other._value
        return super().__lt__(other)
