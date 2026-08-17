"""Versions page: manifest list, details, install (with progress), uninstall, jump to launch."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from gui import i18n
from gui.errors import show_fatal
from gui.models.version_list_model import VersionListModel
from gui.widgets import apply_no_focus_outline
from gui.workers import (
    ProgressBridge,
    RateTracker,
    format_eta,
    format_rate,
    run_in_background,
)
from launcher import config, paths
from launcher.install import (
    find_version_dependents,
    install_version,
    list_installed_versions,
    uninstall_version,
)
from launcher.meta import fetch_manifest, version_category

tr = i18n.tr

# Display name per type column
_TYPE_LABELS = {
    "release": "versions.type.release",
    "snapshot": "versions.type.snapshot",
    "april_fools": "versions.type.april",
    "old_beta": "versions.type.old_beta",
    "old_alpha": "versions.type.old_alpha",
}


class _LoaderPromptDialog(QDialog):
    """Ask whether a mod loader is needed when installing a version."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("versions.loader.dialog.title"))
        self.combo = QComboBox()
        for label, data in (
            (tr("versions.loader.none"), None),
            ("Fabric", "fabric"),
            ("Forge", "forge"),
            ("NeoForge", "neoforge"),
        ):
            self.combo.addItem(label, data)
        hint = QLabel(tr("versions.loader.dialog.hint"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("instances.create.ok"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            tr("instances.create.cancel")
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.combo)
        layout.addWidget(self.buttons)

    def selected_loader(self) -> str | None:
        return self.combo.currentData()


class VersionsPage(QWidget):
    launch_requested = Signal(str)
    versions_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.manifest = None
        self._installed: set[str] = set()

        # Category tabs: all / release / snapshot / april fools / legacy
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.tabs: list[QPushButton] = []
        for label, data in (
            ("versions.all_types", None),
            ("versions.type.release", "release"),
            ("versions.type.snapshot", "snapshot"),
            ("versions.type.april", "april_fools"),
            ("versions.filter.legacy", "legacy"),
        ):
            btn = QPushButton(tr(label))
            btn.setCheckable(True)
            btn.setObjectName("categoryTab")
            btn.setProperty("filter", data)
            self.tab_group.addButton(btn)
            self.tabs.append(btn)
        self.tabs[0].setChecked(True)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("versions.search.placeholder"))
        self.search_edit.setClearButtonEnabled(True)
        self.refresh_button = QPushButton(tr("versions.refresh"))
        # Latest version cards: latest release / latest snapshot
        self.latest_labels: dict[str, QLabel] = {}
        self.latest_buttons: dict[str, QPushButton] = {}
        self.table = QTableView()
        self.model = VersionListModel(
            [
                tr("versions.col.id"),
                tr("versions.col.type"),
                tr("versions.col.time"),
                tr("versions.status.col"),
            ]
        )
        self.table.setModel(self.model)
        apply_no_focus_outline(self.table)
        header = self.table.horizontalHeader()
        # Column width: widen the version-name column to fit 20 ASCII characters
        fm = self.table.fontMetrics()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, fm.horizontalAdvance("W" * 20) + 32)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.info_label = QLabel(tr("versions.info.default"))
        self.info_label.setObjectName("hint")
        self.install_button = QPushButton(tr("versions.install"))
        self.uninstall_button = QPushButton(tr("versions.uninstall"))
        self.detail_button = QPushButton(tr("versions.detail"))
        self.launch_button = QPushButton(tr("versions.goto"))
        self.launch_button.setEnabled(False)
        self.auto_jre_check = QCheckBox(tr("versions.auto_jre"))
        self.auto_jre_check.setChecked(True)  # checked by default
        self.auto_jre_check.setObjectName("hint")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status = QLabel("")
        self.status.setObjectName("hint")

        top = QHBoxLayout()
        top.addWidget(self.search_edit)
        top.addStretch(1)
        top.addWidget(self.refresh_button)

        tabs_row = QHBoxLayout()
        for btn in self.tabs:
            tabs_row.addWidget(btn)
        tabs_row.addStretch(1)

        latest_row = QHBoxLayout()
        for kind, key in (
            ("release", "versions.latest.release"),
            ("snapshot", "versions.latest.snapshot"),
        ):
            card = QFrame()
            card.setObjectName("latestCard")
            card_layout = QVBoxLayout(card)
            kind_label = QLabel(tr(key))
            kind_label.setObjectName("latestKind")
            version_label = QLabel(tr("versions.latest.none"))
            version_label.setObjectName("latestVersion")
            install_btn = QPushButton(tr("versions.install.short"))
            install_btn.setEnabled(False)
            install_btn.clicked.connect(
                lambda _checked=False, k=kind: self._install_latest(k)
            )
            card_layout.addWidget(kind_label)
            card_layout.addWidget(version_label)
            card_layout.addWidget(install_btn)
            self.latest_labels[kind] = version_label
            self.latest_buttons[kind] = install_btn
            latest_row.addWidget(card)
        latest_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(tabs_row)
        layout.addLayout(latest_row)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.info_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addWidget(self.install_button)
        buttons.addWidget(self.uninstall_button)
        buttons.addWidget(self.detail_button)
        buttons.addWidget(self.launch_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addWidget(self.auto_jre_check)

        self.refresh_button.clicked.connect(self.refresh)
        self.tab_group.buttonClicked.connect(lambda *_a: self._refilter())
        # Debounce: re-filter only after 200ms of typing inactivity
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._refilter)
        self.search_edit.textChanged.connect(lambda _t: self._search_timer.start(200))
        self.table.selectionModel().selectionChanged.connect(lambda *_a: self._on_select())
        self.install_button.clicked.connect(self.install_selected)
        self.uninstall_button.clicked.connect(self.uninstall_selected)
        self.detail_button.clicked.connect(self.show_details)
        self.launch_button.clicked.connect(
            lambda: self.launch_requested.emit(self._selected_id() or "")
        )
        self._rate = RateTracker()
        self._fetch_started = False
        self._refresh_installed()

    def showEvent(self, event) -> None:
        """Fetch the manifest on first show instead of at construction (lazy page data)."""
        super().showEvent(event)
        if not self._fetch_started:
            self._fetch_started = True
            self.refresh()

    def _game_dir(self) -> Path:
        cfg, _ = config.load()
        env_value = os.environ.get(paths.ENV_GAME_DIR)
        return (
            cfg.game_dir
            or (Path(env_value).expanduser() if env_value else None)
            or paths.default_game_dir()
        )

    def _refresh_installed(self) -> None:
        self._installed = set(list_installed_versions(self._game_dir()))

    def _selected_id(self) -> str | None:
        row = self.table.currentIndex().row()
        return self.model.row_id(row)

    def refresh(self) -> None:
        self.refresh_button.setEnabled(False)
        self.status.setText(tr("versions.msg.fetching"))
        cache = paths.launcher_dir() / "cache" / "version_manifest.json"

        def do_fetch() -> object:
            return fetch_manifest(cache_path=cache)

        run_in_background(
            do_fetch,
            on_result=self._on_manifest,
            on_error=lambda m: self.status.setText(tr("versions.msg.fetch_fail", m)),
            on_finished=lambda: self.refresh_button.setEnabled(True),
        )

    def _on_manifest(self, manifest) -> None:
        self.manifest = manifest
        self._refresh_installed()
        self._update_latest_cards()
        self.status.setText(tr("versions.msg.fetched", len(manifest.versions)))
        self._refilter()

    def _update_latest_cards(self) -> None:
        latest = getattr(self.manifest, "latest", None) or {}
        for kind in ("release", "snapshot"):
            version_id = (latest.get(kind) or "").strip()
            self.latest_labels[kind].setText(version_id or tr("versions.latest.none"))
            self.latest_buttons[kind].setEnabled(bool(version_id))

    def _install_latest(self, kind: str) -> None:
        latest = getattr(self.manifest, "latest", None) or {}
        version_id = (latest.get(kind) or "").strip()
        if version_id:
            self.install_version_id(version_id)

    def _refilter(self) -> None:
        if self.manifest is None:
            return
        checked = self.tab_group.checkedButton()
        want = checked.property("filter") if checked is not None else None
        needle = self.search_edit.text().strip().lower()
        shown = []
        for v in self.manifest.versions:
            category = version_category(v.id, v.type)
            if want is None:
                ok = True
            elif want == "legacy":
                ok = category in ("old_beta", "old_alpha")
            else:
                ok = want == category
            if ok and (not needle or needle in v.id.lower()):
                shown.append((v, category))
        rows = []
        for v, category in shown:
            release = v.release_time
            status_text = (
                tr("versions.status.installed")
                if v.id in self._installed
                else tr("versions.status.not_installed")
            )
            rows.append(
                (
                    v.id,
                    tr(_TYPE_LABELS.get(category, "versions.type.release")),
                    release[:10] if len(release) >= 10 else release,
                    status_text,
                )
            )
        self.model.set_rows(rows)
        self.info_label.setText(tr("versions.msg.shown", len(shown)))

    def _on_select(self) -> None:
        version_id = self._selected_id()
        if version_id is None:
            return
        self.info_label.setText(tr("versions.info.selected", version_id))

    def install_selected(self) -> None:
        version_id = self._selected_id()
        if version_id is None:
            self.status.setText(tr("versions.msg.need_select"))
            return
        self.install_version_id(version_id)

    def install_version_id(self, version_id: str) -> None:
        # Ask about a mod loader before installing
        prompt = _LoaderPromptDialog(self)
        if prompt.exec() != QDialog.DialogCode.Accepted:
            return
        loader = prompt.selected_loader()
        cfg, _ = config.load()
        game_dir = self._game_dir()
        self.install_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.status.setText(tr("versions.msg.installing", version_id))
        self._rate = RateTracker()
        bridge = ProgressBridge()
        bridge.progress.connect(self._on_progress)

        def do_install(progress) -> object:
            result = install_version(
                version_id,
                game_dir=game_dir,
                cache_dir=paths.launcher_dir() / "cache",
                concurrency=cfg.max_concurrent_downloads,
                progress=progress,
                auto_install_java=self.auto_jre_check.isChecked(),
                runtime_dir=paths.launcher_dir() / "runtime",
            )
            profile_id = None
            if loader is not None:
                from launcher.mods import ModsError, install_loader, list_loader_versions

                versions = list_loader_versions(loader, version_id)
                if not versions:
                    raise ModsError(loader + " 不支持 " + version_id)
                profile_id = install_loader(
                    versions[0], game_dir, cache_dir=paths.launcher_dir() / "cache"
                )
            return result, profile_id

        run_in_background(
            do_install,
            bridge,
            on_result=self._on_installed,
            on_error=self._on_install_error,
            on_finished=lambda: self.install_button.setEnabled(True),
        )

    def uninstall_selected(self) -> None:
        version_id = self._selected_id()
        if version_id is None:
            self.status.setText(tr("versions.msg.need_select"))
            return
        if version_id not in self._installed:
            self.status.setText(tr("versions.msg.uninstall_fail", tr("versions.status.not_installed")))
            return
        game_dir = self._game_dir()
        dependents = find_version_dependents(game_dir, version_id)
        message = tr("versions.uninstall.msg", version_id)
        if dependents:
            message += tr("versions.uninstall.msg.deps", ", ".join(dependents))
        answer = QMessageBox.question(
            self,
            tr("versions.uninstall.dialog"),
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.uninstall_button.setEnabled(False)
        self.status.setText(tr("versions.msg.uninstalling", version_id))

        def do_uninstall() -> object:
            return uninstall_version(version_id, game_dir)

        run_in_background(
            do_uninstall,
            on_result=lambda _deps: self._on_uninstalled(version_id),
            on_error=lambda m: self.status.setText(tr("versions.msg.uninstall_fail", m)),
            on_finished=lambda: self.uninstall_button.setEnabled(True),
        )

    def show_details(self) -> None:
        version_id = self._selected_id()
        if version_id is None:
            self.status.setText(tr("versions.msg.need_select"))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("versions.detail.title"))
        dialog.resize(560, 420)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(tr("versions.detail.loading"))
        layout = QVBoxLayout(dialog)
        layout.addWidget(view)
        cache = paths.launcher_dir() / "cache"

        def do_load() -> object:
            from launcher.meta import detect_platform, load_version_json, resolve_libraries

            version = load_version_json(version_id, cache_dir=cache)
            platform = detect_platform()
            resolved = resolve_libraries(version.libraries, platform)
            natives = [r for r in resolved if r.classifier is not None]
            return version, resolved, natives

        def _safe_text(text: str) -> None:
            try:
                view.setPlainText(text)
            except RuntimeError:
                pass  # dialog was closed while loading

        run_in_background(
            do_load,
            on_result=lambda result: self._fill_details(view, result),
            on_error=lambda m: _safe_text(tr("versions.detail.fail", m)),
        )
        dialog.exec()

    @staticmethod
    def _fill_details(view, result) -> None:
        """Fill the version detail text; silently ignore when the dialog was closed (RuntimeError)."""
        try:
            version, resolved, natives = result
        except RuntimeError:
            return
        try:
            if version.java_version is not None:
                java_text = str(version.java_version.major_version) + "（" + version.java_version.component + "）"
            else:
                java_text = tr("versions.detail.java_default")
            client_art = version.downloads.get("client")
            client_url = client_art.url if client_art is not None and client_art.url else "(无 url 字段)"
            if client_art is None:
                client_url, sha1_text, size_text = "(无)", "(无)", "(无)"
            else:
                sha1_text = client_art.sha1 or "(无)"
                size_text = str(client_art.size) if client_art.size is not None else "(无)"
            fmt = (
                tr("versions.detail.legacy")
                if version.is_legacy
                else tr("versions.detail.modern")
            )
            view.setPlainText(
                tr(
                    "versions.detail.line",
                    version.id,
                    version.type,
                    version.release_time or tr("versions.detail.unknown"),
                    version.main_class,
                    java_text,
                    version.asset_index.id,
                    version.assets,
                    version.client_jar_name,
                    client_url,
                    sha1_text,
                    size_text,
                    len(version.libraries),
                    len(resolved),
                    len(natives),
                    fmt,
                    len(version.effective_game_arguments()),
                    len(version.effective_jvm_arguments()),
                )
            )
        except RuntimeError:
            pass  # dialog was closed while loading

    def _on_uninstalled(self, version_id: str) -> None:
        self._refresh_installed()
        self._refilter()
        self.status.setText(tr("versions.msg.uninstalled", version_id))
        self.versions_changed.emit()

    def _on_progress(self, p) -> None:
        if p.total_files:
            self.progress_bar.setValue(int(p.done_files * 1000 / p.total_files))
            self._rate.set_total(p.total_bytes)
            rate, eta = self._rate.update(p.done_bytes)
            if rate > 0:
                self.status.setText(
                    tr(
                        "versions.msg.downloading_rate",
                        p.done_files,
                        p.total_files,
                        p.current,
                        format_rate(rate),
                        format_eta(eta),
                    )
                )
            else:
                self.status.setText(
                    tr("versions.msg.downloading", p.done_files, p.total_files, p.current)
                )

    def _on_installed(self, payload) -> None:
        result, profile_id = payload
        self.progress_bar.setVisible(False)
        self.launch_button.setEnabled(True)
        self._refresh_installed()
        self._refilter()
        if result.failed:
            message = tr("versions.msg.partial", len(result.failed))
        else:
            message = tr("versions.msg.done", result.downloaded, result.skipped)
        if profile_id:
            message += " | " + tr("versions.msg.loader_done", profile_id)
        self.status.setText(message)
        self.versions_changed.emit()

    def _on_install_error(self, message: str) -> None:
        self.progress_bar.setVisible(False)
        text = tr("versions.msg.install_fail", message)
        self.status.setText(text)
        show_fatal(self, text)  # fatal error dialog
