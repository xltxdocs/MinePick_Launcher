"""Resources page: mod search (Modrinth) / modpacks / resource packs / shader packs + installed content management."""

from __future__ import annotations

import time
from typing import ClassVar

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
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
from launcher.mods import (
    ModsError,
    fetch_project,
    fetch_versions,
    install_mod,
    install_modpack,
    install_resourcepack,
    install_shaderpack,
    resolve_slugs,
    search_projects,
)
from launcher.mods.models import ModInfo, ModSearchHit, ModVersion
from launcher.mods.zh_names import has_cjk, search_local

tr = i18n.tr


class _VersionPickerDialog(QDialog):
    """Modrinth project version picker dialog (version / loader / MC version)."""

    def __init__(self, slug: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.slug = slug
        self._versions: list[ModVersion] = []
        self.setWindowTitle(tr("mods.picker.title"))
        self.setMinimumSize(560, 380)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            [
                tr("mods.picker.col.version"),
                tr("mods.picker.col.loaders"),
                tr("mods.picker.col.game_versions"),
            ]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.status = QLabel(tr("mods.picker.loading"))
        self.status.setObjectName("hint")
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_button.setText(tr("mods.picker.ok"))
        ok_button.setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            tr("mods.picker.cancel")
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)

        self.table.itemSelectionChanged.connect(
            lambda: ok_button.setEnabled(self.selected_version() is not None)
        )
        self.table.cellDoubleClicked.connect(
            lambda _row, _col: self.accept() if self.selected_version() is not None else None
        )

        def do_fetch() -> object:
            return fetch_versions(slug)

        run_in_background(
            do_fetch,
            on_result=self._fill,
            on_error=lambda m: self.status.setText(tr("mods.picker.fail", m)),
        )

    def _fill(self, versions: list[ModVersion]) -> None:
        self._versions = versions
        self.table.setRowCount(0)
        self.table.setRowCount(len(versions))
        for row, version in enumerate(versions):
            self.table.setItem(row, 0, QTableWidgetItem(version.version_number))
            self.table.setItem(row, 1, QTableWidgetItem(", ".join(version.loaders)))
            self.table.setItem(row, 2, QTableWidgetItem(", ".join(version.game_versions)))
        if versions:
            self.status.setText("")
        else:
            self.status.setText(tr("mods.picker.none"))

    def selected_version(self) -> ModVersion | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._versions):
            return None
        return self._versions[row]


class _ContentTab(QWidget):
    """Generic resource tab. kind: mod / modpack / resourcepack / shaderpack"""

    CONTENT_SUBDIR: ClassVar[dict[str, str]] = {
        "mod": "mods",
        "resourcepack": "resourcepacks",
        "shaderpack": "shaderpacks",
    }

    def __init__(self, kind: str) -> None:
        super().__init__()
        self.kind = kind
        self._entries: list[object] = []  # ModSearchHit (search) or ModInfo (slug query)
        self._hit: ModSearchHit | None = None
        self._current: ModInfo | None = None
        self._current_slug = ""
        self._current_mod_version_id = ""
        self._current_loader = ""
        self._current_game_version = ""

        self.loader_combo = QComboBox()
        for name in ("fabric", "forge", "neoforge"):
            self.loader_combo.addItem(name, name)
        self.game_version_edit = QLineEdit("1.20.1")
        self.slug_edit = QLineEdit()
        self.slug_edit.setPlaceholderText(tr("mods.slug.placeholder"))
        self.query_button = QPushButton(tr("mods.query"))
        self.search_edit = QLineEdit()
        placeholder_key = {
            "resourcepack": "mods.search.placeholder.rp",
            "shaderpack": "mods.search.placeholder.sp",
            "modpack": "mods.search.placeholder.modpack",
        }.get(kind, "mods.search.placeholder")
        self.search_edit.setPlaceholderText(tr(placeholder_key))
        self.search_button = QPushButton(tr("mods.search.button"))
        self.popular_button = QPushButton(tr("mods.popular"))
        self._popular_loaded = False
        self._popular_cache: tuple[str, float, list] | None = None
        self.install_button = QPushButton(tr("mods.install"))
        self.open_folder_button = QPushButton(tr("mods.open_folder"))
        self.list = QListWidget()
        apply_no_focus_outline(self.list)
        self.title_label = QLabel(tr("mods.select"))
        self.title_label.setObjectName("title")
        self.desc_label = QLabel("")
        self.desc_label.setWordWrap(True)
        self.dep_required = QLabel("")
        self.dep_optional = QLabel("")
        self.status = QLabel(tr("mods.status.default"))
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)

        query_row = QHBoxLayout()
        if kind == "mod":
            query_row.addWidget(QLabel(tr("mods.loader")))
            query_row.addWidget(self.loader_combo)
        query_row.addWidget(QLabel(tr("mods.game_version")))
        query_row.addWidget(self.game_version_edit)
        query_row.addWidget(self.slug_edit, 1)
        query_row.addWidget(self.query_button)

        left = QVBoxLayout()
        left.addWidget(QLabel(tr("mods.list.label")))
        left.addWidget(self.list, 1)

        right = QVBoxLayout()
        right.addWidget(self.title_label)
        right.addWidget(self.desc_label)
        right.addWidget(self.dep_required)
        right.addWidget(self.dep_optional)
        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.install_button)
        if kind != "modpack":
            buttons_row.addWidget(self.open_folder_button)
        buttons_row.addStretch(1)
        right.addLayout(buttons_row)
        right.addWidget(self.status)
        right.addStretch(1)

        body = QHBoxLayout()
        body.addLayout(left, 1)
        body.addLayout(right, 2)

        layout = QVBoxLayout(self)
        self._search_row = QHBoxLayout()
        self._search_row.addWidget(self.search_edit, 1)
        self._search_row.addWidget(self.search_button)
        self._search_row.addWidget(self.popular_button)
        layout.addLayout(self._search_row)
        layout.addLayout(query_row)
        layout.addLayout(body, 1)

        self.list.currentRowChanged.connect(self._on_select)
        self.query_button.clicked.connect(self.query)
        self.search_button.clicked.connect(self._search)
        self.search_edit.returnPressed.connect(self._search)
        self.popular_button.clicked.connect(self.load_popular)
        self.install_button.clicked.connect(self._on_install_clicked)
        if kind != "modpack":
            self.open_folder_button.clicked.connect(self._open_content_folder)

        self._update_install_button()

    # ---------- List & details ----------

    def _set_entries(self, entries: list[object]) -> None:
        self._entries = entries
        self.list.clear()
        for entry in entries:
            text = getattr(entry, "title", "")
            if isinstance(entry, ModSearchHit) and entry.downloads:
                text += "   | " + tr("mods.search.downloads", f"{entry.downloads:,}")
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, entry)
            self.list.addItem(item)
        if entries:
            self.list.setCurrentRow(0)

    def _clear_entries(self) -> None:
        self._set_entries([])
        self._hit = None
        self._current = None
        self.title_label.setText(tr("mods.select"))
        self.desc_label.setText("")
        self.dep_required.setText("")
        self.dep_optional.setText("")
        self._update_install_button()

    def _on_select(self, row: int) -> None:
        if row < 0 or row >= len(self._entries):
            return
        entry = self._entries[row]
        if isinstance(entry, ModSearchHit):
            self._hit = entry
            self._current = None
            self.title_label.setText(entry.title)
            self.desc_label.setText(entry.description)
            self.dep_required.setText("")
            self.dep_optional.setText(tr("mods.search.downloads", f"{entry.downloads:,}"))
            self.status.setText(tr("mods.status.default"))
        elif isinstance(entry, ModInfo):
            self._hit = None
            self._show_mod(entry)
        self._update_install_button()

    def _show_mod(self, mod: ModInfo) -> None:
        self._current = mod
        self.title_label.setText(mod.title)
        self.desc_label.setText(mod.description)
        none_tag = '<span style="color:#8b9bb4;">' + tr("mods.dep.none") + "</span>"
        self.dep_required.setText(
            '<span style="color:#e06c75; font-weight:bold;">' + tr("mods.dep.required") + "</span> "
            + (
                " ".join(_tag(dep, "#e06c75", "#3a2026") for dep in mod.depends)
                if mod.depends
                else none_tag
            )
            + ' <span style="color:#8b9bb4;">' + tr("mods.dep.required.hint") + "</span>"
        )
        self.dep_optional.setText(
            '<span style="color:#8b9bb4;">' + tr("mods.dep.optional") + "</span> "
            + (
                " ".join(_tag(dep, "#8b9bb4", "#232a36") for dep in mod.optional_depends)
                if mod.optional_depends
                else none_tag
            )
            + ' <span style="color:#8b9bb4;">' + tr("mods.dep.optional.hint") + "</span>"
        )
        self._update_install_button()

    def _update_install_button(self) -> None:
        if self._hit is not None:
            self.install_button.setText(tr("mods.search.pick"))
            self.install_button.setEnabled(True)
        else:
            self.install_button.setText(tr("mods.install"))
            self.install_button.setEnabled(self._current is not None)

    # ---------- Search ----------

    def _search(self) -> None:
        query = self.search_edit.text().strip()
        if not query:
            return
        self.search_button.setEnabled(False)
        self.status.setText(tr("mods.search.msg.searching", query))

        project_type = {"resourcepack": "resourcepack", "shaderpack": "shader", "modpack": "modpack"}.get(
            self.kind, "mod"
        )

        def do_search() -> object:
            if self.page.current_source() == "curseforge":
                from launcher.mods import curseforge as cf

                return cf.search_projects(
                    query,
                    limit=30,
                    kind=self.kind,
                    game_version=self.game_version_edit.text().strip(),
                    loader=self.loader_combo.currentData() if self.kind == "mod" else "",
                )
            hits = search_projects(query, limit=30, project_type=project_type)
            if has_cjk(query):
                # Chinese query: pin local Chinese-name table matches to the top, then merge Modrinth results
                local_hits = []
                for slug in search_local(query)[:10]:
                    try:
                        p = fetch_project(slug)
                    except ModsError:
                        continue
                    local_hits.append(
                        ModSearchHit(
                            slug=p.get("slug") or slug,
                            title=p.get("title") or slug,
                            description=p.get("description") or "",
                            downloads=int(p.get("downloads") or 0),
                            icon_url=p.get("icon_url") or "",
                        )
                    )
                seen = {h.slug for h in local_hits}
                hits = local_hits + [h for h in hits if h.slug not in seen]
            return hits

        run_in_background(
            do_search,
            on_result=lambda hits: self._on_search_ok(hits, query),
            on_error=lambda m: self.status.setText(tr("mods.search.msg.fail", m)),
            on_finished=lambda: self.search_button.setEnabled(True),
        )

    def _on_search_ok(self, hits: list[ModSearchHit], query: str) -> None:
        if not hits:
            self._set_entries([])
            self._hit = None
            self._current = None
            self.title_label.setText(tr("mods.select"))
            self.desc_label.setText("")
            self.dep_required.setText("")
            self.dep_optional.setText("")
            self.status.setText(tr("mods.search.msg.none", query))
            self._update_install_button()
            return
        self._set_entries(list(hits))
        self.status.setText("")

    # ---------- Popular Top 30 (by downloads) ----------

    def load_popular(self) -> None:
        """Load this type's top 30 by downloads; cached for 10 minutes per source."""
        self._popular_loaded = True
        source = self.page.current_source()
        if self._popular_cache is not None:
            cached_source, cached_at, cached_hits = self._popular_cache
            if cached_source == source and time.monotonic() - cached_at < 600:
                self._on_popular_ok(cached_hits)
                return
        self.popular_button.setEnabled(False)
        self.status.setText(tr("mods.search.msg.searching", tr("mods.popular")))
        project_type = {"resourcepack": "resourcepack", "shaderpack": "shader", "modpack": "modpack"}.get(
            self.kind, "mod"
        )

        def do_fetch() -> object:
            if self.page.current_source() == "curseforge":
                from launcher.mods import curseforge as cf

                return cf.search_projects("", limit=30, kind=self.kind)
            return search_projects("", limit=30, project_type=project_type)

        run_in_background(
            do_fetch,
            on_result=self._on_popular_ok,
            on_error=lambda m: self.status.setText(tr("mods.popular.fail", m)),
            on_finished=lambda: self.popular_button.setEnabled(True),
        )

    def _on_popular_ok(self, hits: list[ModSearchHit]) -> None:
        self._popular_cache = (self.page.current_source(), time.monotonic(), list(hits))
        self._set_entries(list(hits))
        self.status.setText(tr("mods.popular.status"))

    # ---------- slug query (kept) ----------

    def query(self) -> None:
        slug = self.slug_edit.text().strip()
        if not slug:
            self.status.setText(tr("mods.status.default"))
            return
        loader = self.loader_combo.currentData() if self.kind == "mod" else None
        game_version = self.game_version_edit.text().strip()
        self.query_button.setEnabled(False)
        self.status.setText(tr("mods.msg.querying", slug))

        def do_query() -> object:
            project = fetch_project(slug)
            versions = fetch_versions(slug, loader=loader, game_version=game_version)
            if not versions:
                raise ModsError(tr("mods.msg.no_match", loader or "-", game_version))
            picked = versions[0]
            dep_ids = [d.project_id for d in picked.dependencies if d.project_id]
            slugs = resolve_slugs(dep_ids)
            from launcher.mods.modrinth import to_mod_info

            info = to_mod_info(slug, project, picked, slugs)
            return info, picked

        run_in_background(
            do_query,
            on_result=self._on_query_ok,
            on_error=lambda m: self.status.setText(tr("mods.msg.query_fail", m)),
            on_finished=lambda: self.query_button.setEnabled(True),
        )

    def _on_query_ok(self, result) -> None:
        info, picked = result
        self._current_slug = info.slug
        self._current_mod_version_id = picked.version_id
        self._current_loader = (
            self.loader_combo.currentData() if self.kind == "mod" else None
        )
        self._current_game_version = self.game_version_edit.text().strip()
        if self.kind == "mod":
            kept = [e for e in self._entries if not (isinstance(e, ModInfo) and e.slug == info.slug)]
            self._set_entries([info] + kept)
            self._show_mod(info)
        else:
            self._hit = None
            self._current = info
            self.title_label.setText(info.title)
            self.desc_label.setText(info.description)
            self.dep_required.setText(
                tr(
                    "mods.info.meta",
                    picked.version_number,
                    ", ".join(picked.loaders) or "-",
                    ", ".join(picked.game_versions) or "-",
                )
            )
            self.dep_optional.setText("")
            self._update_install_button()
        self.status.setText(tr("mods.msg.query_done", info.title, picked.version_id))

    # ---------- Install ----------

    def _on_install_clicked(self) -> None:
        if self._hit is not None:
            if self.page.current_source() == "curseforge":
                self._install_cf(self._hit)
            elif self.kind == "mod":
                self._pick_version()
            else:
                self._install_slug(
                    self._hit.slug,
                    mod_version_id=None,
                    loader=None,
                    game_version=None,
                    title=self._hit.title,
                )
            return
        self._on_install()

    def _install_cf(self, hit: ModSearchHit) -> None:
        """Install from CurseForge: pick the latest release file matching the game version and download it to the content directory."""
        if self.kind == "modpack":
            self.status.setText(tr("mods.cf.modpack_unsupported"))
            return
        from launcher.mods import curseforge as cf
        from launcher.mods import resolve_content_dir, resolve_mods_dir

        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()
        game_version = self.game_version_edit.text().strip()
        loader = self.loader_combo.currentData() if self.kind == "mod" else ""
        self.install_button.setEnabled(False)
        self.status.setText(tr("mods.cf.downloading", hit.title))

        def do_install() -> object:
            files = cf.list_files(int(hit.slug), game_version=game_version, loader=loader)
            if not files:
                raise ModsError(tr("mods.cf.no_file", game_version or hit.title))
            picked = files[0]
            if self.kind == "mod":
                target = resolve_mods_dir(
                    game_dir,
                    isolated=cfg.version_isolation,
                    loader=loader,
                    game_version=game_version,
                )
            else:
                subdir = {"resourcepack": "resourcepacks", "shaderpack": "shaderpacks"}.get(
                    self.kind, self.kind
                )
                target = resolve_content_dir(game_dir, subdir, isolated=cfg.version_isolation)
            return cf.download_file(picked, target), picked

        run_in_background(
            do_install,
            on_result=self._on_cf_installed,
            on_error=lambda m: self.status.setText(tr("mods.cf.fail", m)),
            on_finished=lambda: self.install_button.setEnabled(True),
        )

    def _on_cf_installed(self, result) -> None:
        target, _picked = result
        self.status.setText(tr("mods.cf.done", target.name))

    def _pick_version(self) -> None:
        hit = self._hit
        if hit is None:
            return
        dialog = _VersionPickerDialog(hit.slug, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        picked = dialog.selected_version()
        if picked is None:
            return
        loader = picked.loaders[0] if picked.loaders else None
        game_version = picked.game_versions[0] if picked.game_versions else None
        self._install_slug(
            hit.slug,
            mod_version_id=picked.version_id,
            loader=loader,
            game_version=game_version,
            title=hit.title,
        )

    def _install_slug(
        self,
        slug: str,
        *,
        mod_version_id: str | None,
        loader: str | None,
        game_version: str | None,
        title: str | None,
    ) -> None:
        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()
        self.install_button.setEnabled(False)
        self.status.setText(tr("mods.msg.downloading", title or slug))

        def do_install() -> object:
            if self.kind == "resourcepack":
                return install_resourcepack(
                    slug,
                    game_dir=game_dir,
                    game_version=game_version,
                    mod_version_id=mod_version_id,
                    isolated=cfg.version_isolation,
                )
            if self.kind == "shaderpack":
                return install_shaderpack(
                    slug,
                    game_dir=game_dir,
                    game_version=game_version,
                    mod_version_id=mod_version_id,
                    isolated=cfg.version_isolation,
                )
            return install_mod(
                slug,
                game_dir=game_dir,
                loader=loader,
                game_version=game_version,
                mod_version_id=mod_version_id,
                isolated=cfg.version_isolation,
            )

        run_in_background(
            do_install,
            on_result=self._on_installed,
            on_error=lambda m: self.status.setText(tr("mods.msg.install_fail", m)),
            on_finished=self._on_install_finished,
        )

    def _on_install(self) -> None:
        if self._current is None:
            return
        mod = self._current
        cfg, _ = config.load()
        game_dir = cfg.game_dir or paths.default_game_dir()

        if self.kind == "modpack":
            answer = QMessageBox.question(
                self,
                tr("mods.mp.confirm.title"),
                tr("mods.mp.confirm.msg", mod.slug),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

            def do_install(progress) -> object:
                return install_modpack(
                    mod.slug,
                    game_dir=game_dir,
                    cache_dir=paths.launcher_dir() / "cache",
                    mod_version_id=self._current_mod_version_id or None,
                    progress=progress,
                )

            bridge = ProgressBridge()
            rate_tracker = RateTracker()

            def on_progress(p) -> None:
                rate_tracker.set_total(p.total_bytes)
                rate, eta = rate_tracker.update(p.done_bytes)
                if rate > 0:
                    self.status.setText(
                        tr(
                            "mods.mp.progress_rate",
                            p.done_files,
                            p.total_files,
                            p.current,
                            format_rate(rate),
                            format_eta(eta),
                        )
                    )
                else:
                    self.status.setText(
                        tr("mods.mp.progress", p.done_files, p.total_files, p.current)
                    )

            bridge.progress.connect(on_progress)
            self.install_button.setEnabled(False)
            self.status.setText(tr("mods.msg.downloading", mod.slug))
            run_in_background(
                do_install,
                bridge,
                on_result=self._on_modpack_installed,
                on_error=lambda m: (
                    self.status.setText(tr("mods.msg.install_fail", m)),
                    show_fatal(self, tr("mods.msg.install_fail", m)),
                ),
                on_finished=self._on_install_finished,
            )
            return

        if mod.depends:
            answer = QMessageBox.question(
                self,
                tr("mods.dialog.title"),
                tr("mods.dialog.msg", "、".join(mod.depends)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        def do_install() -> object:
            if self.kind == "resourcepack":
                return install_resourcepack(
                    mod.slug,
                    game_dir=game_dir,
                    game_version=self._current_game_version or None,
                    mod_version_id=self._current_mod_version_id or None,
                    isolated=cfg.version_isolation,
                )
            if self.kind == "shaderpack":
                return install_shaderpack(
                    mod.slug,
                    game_dir=game_dir,
                    game_version=self._current_game_version or None,
                    mod_version_id=self._current_mod_version_id or None,
                    isolated=cfg.version_isolation,
                )
            return install_mod(
                mod.slug,
                game_dir=game_dir,
                loader=self._current_loader or None,
                game_version=self._current_game_version or None,
                mod_version_id=self._current_mod_version_id or None,
                isolated=cfg.version_isolation,
            )

        self.install_button.setEnabled(False)
        self.status.setText(tr("mods.msg.downloading", mod.slug))
        run_in_background(
            do_install,
            on_result=self._on_installed,
            on_error=lambda m: (
                self.status.setText(tr("mods.msg.install_fail", m)),
                show_fatal(self, tr("mods.msg.install_fail", m)),
            ),
            on_finished=self._on_install_finished,
        )

    def _on_install_finished(self) -> None:
        self._update_install_button()

    def _on_installed(self, info: ModInfo) -> None:
        if self.kind == "resourcepack":
            self.status.setText(tr("mods.rp.done", info.title, info.slug))
            return
        if self.kind == "shaderpack":
            self.status.setText(tr("mods.sp.done", info.title, info.slug))
            return
        message = tr("mods.msg.installed", info.title, info.slug)
        if info.depends:
            message += " | " + tr("mods.dep.required") + " " + ", ".join(info.depends)
        if info.optional_depends:
            message += " | " + tr("mods.dep.optional") + " " + ", ".join(info.optional_depends)
        self.status.setText(message)

    def _on_modpack_installed(self, pack) -> None:
        message = tr("mods.mp.done", pack.instance_name, pack.minecraft, pack.files_count)
        if pack.loader:
            message += " | " + str(pack.loader) + " " + str(pack.loader_version)
        self.status.setText(message)

    # ---------- Installed content ----------

    def _content_target_args(self) -> dict:
        cfg, _ = config.load()
        return {
            "game_dir": cfg.game_dir or paths.default_game_dir(),
            "loader": self.loader_combo.currentData() if self.kind == "mod" else None,
            "game_version": self.game_version_edit.text().strip() or None,
            "isolated": cfg.version_isolation,
        }

    # ---------- Folder ----------

    def _open_content_folder(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        from launcher.mods.modrinth import resolve_content_dir

        subdir = self.CONTENT_SUBDIR[self.kind]
        args = self._content_target_args()
        game_dir = args.pop("game_dir")
        try:
            target = resolve_content_dir(game_dir, subdir, **args)
        except ModsError:
            target = paths.GamePaths(game_dir).game_dir / subdir
        target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        self.status.setText(tr("mods.msg.folder_opened", str(target)))


class ResourcesPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.title = QLabel(tr("mods.page.title"))
        self.title.setObjectName("title")
        self.tabs = QTabWidget()
        # Remove the tab widget's built-in bottom baseline to stay fully flat
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.tabBar().setFocusPolicy(Qt.NoFocus)  # remove the focus outline on the selected tab's text
        self.mods_tab = _ContentTab("mod")
        self.modpacks_tab = _ContentTab("modpack")
        self.resourcepacks_tab = _ContentTab("resourcepack")
        self.shaderpacks_tab = _ContentTab("shaderpack")
        self.tabs.addTab(self.mods_tab, tr("mods.tab.mods"))
        self.tabs.addTab(self.modpacks_tab, tr("mods.tab.modpacks"))
        self.tabs.addTab(self.resourcepacks_tab, tr("mods.tab.resourcepacks"))
        self.tabs.addTab(self.shaderpacks_tab, tr("mods.tab.shaderpacks"))
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.source_combos: list[QComboBox] = []
        for tab in (
            self.mods_tab,
            self.modpacks_tab,
            self.resourcepacks_tab,
            self.shaderpacks_tab,
        ):
            tab.page = self
            combo = QComboBox()
            combo.addItem(tr("mods.source.modrinth"), "modrinth")
            combo.addItem(tr("mods.source.curseforge"), "curseforge")
            # Wide enough for "CurseForge" plus the arrow and generous padding
            combo.setFixedWidth(combo.fontMetrics().horizontalAdvance("CurseForge") + 60)
            combo.currentIndexChanged.connect(self._on_source_changed)
            tab._search_row.insertWidget(0, combo)
            self.source_combos.append(combo)
        self.source_combo = self.source_combos[0]  # canonical reference

        title_row = QHBoxLayout()
        title_row.addWidget(self.title)
        title_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(title_row)
        layout.addWidget(self.tabs, 1)

    def showEvent(self, event) -> None:
        """Load popular content on first show instead of at construction (lazy page data)."""
        super().showEvent(event)
        self._on_tab_changed(self.tabs.currentIndex())

    def current_source(self) -> str:
        return self.source_combo.currentData() or "modrinth"

    def _on_source_changed(self, _index: int) -> None:
        sender = self.sender()
        if sender is None:
            return
        data = sender.currentData()
        for combo in self.source_combos:
            if combo is not sender:
                combo.blockSignals(True)
                combo.setCurrentIndex(max(combo.findData(data), 0))
                combo.blockSignals(False)
        for tab in (
            self.mods_tab,
            self.modpacks_tab,
            self.resourcepacks_tab,
            self.shaderpacks_tab,
        ):
            tab._clear_entries()
            tab._popular_loaded = False
        self._on_tab_changed(self.tabs.currentIndex())

    def _on_tab_changed(self, index: int) -> None:
        tab = self.tabs.widget(index)
        if isinstance(tab, _ContentTab) and not tab._popular_loaded:
            tab.load_popular()


def _tag(text: str, color: str, background: str) -> str:
    return (
        '<span style="color:' + color + '; background:' + background
        + '; padding:2px 8px; border-radius:3px; margin-right:4px;">'
        + text + "</span>"
    )
