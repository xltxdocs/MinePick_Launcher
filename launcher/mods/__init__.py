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

"""Mod loaders (Fabric / Forge / NeoForge) and Modrinth downloads (mods / modpacks / resource packs / shaders)."""

from launcher.mods.installer import install_loader, installer_args
from launcher.mods.loaders import (
    LOADERS,
    ModsError,
    list_game_versions,
    list_loader_versions,
)
from launcher.mods.models import (
    InstalledContent,
    LoaderVersion,
    ModDependency,
    ModFile,
    ModInfo,
    ModSearchHit,
    ModVersion,
)
from launcher.mods.modpacks import ModpackInfo, install_modpack
from launcher.mods.modrinth import (
    delete_installed_content,
    fetch_project,
    fetch_versions,
    find_profile_id,
    install_mod,
    install_resourcepack,
    install_shaderpack,
    list_installed_content,
    pick_file,
    resolve_content_dir,
    resolve_mods_dir,
    resolve_slugs,
    search_projects,
    to_mod_info,
)

__all__ = [
    "LOADERS",
    "InstalledContent",
    "LoaderVersion",
    "ModDependency",
    "ModFile",
    "ModInfo",
    "ModSearchHit",
    "ModVersion",
    "ModpackInfo",
    "ModsError",
    "delete_installed_content",
    "fetch_project",
    "fetch_versions",
    "find_profile_id",
    "install_loader",
    "install_mod",
    "install_modpack",
    "install_resourcepack",
    "install_shaderpack",
    "installer_args",
    "list_game_versions",
    "list_installed_content",
    "list_loader_versions",
    "pick_file",
    "resolve_content_dir",
    "resolve_mods_dir",
    "resolve_slugs",
    "search_projects",
    "to_mod_info",
]
