"""M7：模组加载器（Fabric / Forge / NeoForge）与 Modrinth 下载（模组/整合包/资源包/光影）。"""

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
