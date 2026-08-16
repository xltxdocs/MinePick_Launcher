"""版本页：清单列表、详情、安装（带进度）、卸载、跳转启动。"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui import i18n
from gui.errors import show_fatal
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
from launcher.meta import fetch_manifest

tr = i18n.tr


class VersionsPage(QWidget):
    launch_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.manifest = None
        self._installed: set[str] = set()

        self.type_combo = QComboBox()
        self.type_combo.addItem(tr("versions.all_types"), None)
        self.type_combo.addItem("release", "release")
        self.type_combo.addItem("snapshot", "snapshot")
        self.type_combo.addItem("old_beta", "old_beta")
        self.type_combo.addItem("old_alpha", "old_alpha")
        self.refresh_button = QPushButton(tr("versions.refresh"))
        self.table = QTableWidget(0, 4)
        apply_no_focus_outline(self.table)
        self.table.setHorizontalHeaderLabels(
            [
                tr("versions.col.id"),
                tr("versions.col.type"),
                tr("versions.col.time"),
                tr("versions.status.col"),
            ]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.info_label = QLabel(tr("versions.info.default"))
        self.info_label.setObjectName("hint")
        self.install_button = QPushButton(tr("versions.install"))
        self.uninstall_button = QPushButton(tr("versions.uninstall"))
        self.detail_button = QPushButton(tr("versions.detail"))
        self.launch_button = QPushButton(tr("versions.goto"))
        self.launch_button.setEnabled(False)
        self.auto_jre_check = QCheckBox(tr("versions.auto_jre"))
        self.auto_jre_check.setChecked(True)  # 默认勾选
        self.auto_jre_check.setObjectName("hint")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status = QLabel("")
        self.status.setObjectName("hint")

        top = QHBoxLayout()
        top.addWidget(self.type_combo)
        top.addWidget(self.refresh_button)
        top.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
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
        self.type_combo.currentIndexChanged.connect(self._refilter)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.install_button.clicked.connect(self.install_selected)
        self.uninstall_button.clicked.connect(self.uninstall_selected)
        self.detail_button.clicked.connect(self.show_details)
        self.launch_button.clicked.connect(
            lambda: self.launch_requested.emit(self._selected_id() or "")
        )
        self._rate = RateTracker()

        self._refresh_installed()

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
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

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
        self.status.setText(tr("versions.msg.fetched", len(manifest.versions)))
        self._refilter()

    def _refilter(self) -> None:
        if self.manifest is None:
            return
        want_type = self.type_combo.currentData()
        versions = [
            v for v in self.manifest.versions
            if want_type is None or v.type == want_type
        ]
        shown = versions[:500]
        self.table.setRowCount(0)
        self.table.setRowCount(len(shown))
        for row, v in enumerate(shown):
            self.table.setItem(row, 0, QTableWidgetItem(v.id))
            self.table.setItem(row, 1, QTableWidgetItem(v.type))
            self.table.setItem(row, 2, QTableWidgetItem(v.release_time))
            if v.id in self._installed:
                status_text = tr("versions.status.installed")
            else:
                status_text = tr("versions.status.not_installed")
            self.table.setItem(row, 3, QTableWidgetItem(status_text))
        self.info_label.setText(tr("versions.msg.shown", len(versions)))

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
            return install_version(
                version_id,
                game_dir=game_dir,
                cache_dir=paths.launcher_dir() / "cache",
                concurrency=cfg.max_concurrent_downloads,
                progress=progress,
                auto_install_java=self.auto_jre_check.isChecked(),
                runtime_dir=paths.launcher_dir() / "runtime",
            )

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
                pass  # 对话框在加载期间被关闭

        run_in_background(
            do_load,
            on_result=lambda result: self._fill_details(view, result),
            on_error=lambda m: _safe_text(tr("versions.detail.fail", m)),
        )
        dialog.exec()

    @staticmethod
    def _fill_details(view, result) -> None:
        """填充版本详情文本；对话框已关闭时静默忽略（RuntimeError）。"""
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
            pass  # 对话框在加载期间被关闭

    def _on_uninstalled(self, version_id: str) -> None:
        self._refresh_installed()
        self._refilter()
        self.status.setText(tr("versions.msg.uninstalled", version_id))

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

    def _on_installed(self, result) -> None:
        self.progress_bar.setVisible(False)
        self.launch_button.setEnabled(True)
        self._refresh_installed()
        self._refilter()
        if result.failed:
            self.status.setText(tr("versions.msg.partial", len(result.failed)))
        else:
            self.status.setText(tr("versions.msg.done", result.downloaded, result.skipped))

    def _on_install_error(self, message: str) -> None:
        self.progress_bar.setVisible(False)
        text = tr("versions.msg.install_fail", message)
        self.status.setText(text)
        show_fatal(self, text)  # #31 致命错误弹窗
