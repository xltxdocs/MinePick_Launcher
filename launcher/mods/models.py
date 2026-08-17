"""Mod and loader data models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LoaderVersion(BaseModel):
    """Loader version (with installer download info)."""

    model_config = ConfigDict(extra="ignore")

    loader: str  # fabric / forge / neoforge
    version: str
    game_version: str
    stable: bool = True
    recommended: bool = False
    installer_url: str = ""


class ModFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    filename: str
    url: str
    size: int = 0
    sha1: str | None = None
    sha512: str | None = None
    primary: bool = False


class ModDependency(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_id: str = ""
    slug: str = ""
    dependency_type: str = ""  # required / optional / incompatible / embedded


class ModVersion(BaseModel):
    """A version of a Modrinth project."""

    model_config = ConfigDict(extra="ignore")

    version_id: str
    version_number: str = ""
    loaders: list[str] = []
    game_versions: list[str] = []
    files: list[ModFile] = []
    dependencies: list[ModDependency] = []


class ModInfo(BaseModel):
    """UI-facing mod info; dependencies are only suggested, not force-installed."""

    model_config = ConfigDict(extra="ignore")

    slug: str
    title: str
    description: str = ""
    depends: list[str] = []  # required dependencies (list of slugs)
    optional_depends: list[str] = []  # optional dependencies (list of slugs)


class ModSearchHit(BaseModel):
    """A Modrinth search-result entry."""

    model_config = ConfigDict(extra="ignore")

    slug: str
    title: str
    description: str = ""
    downloads: int = 0
    icon_url: str = ""


class InstalledContent(BaseModel):
    """Installed content-file entry (mods / resourcepacks / shaderpacks)."""

    model_config = ConfigDict(extra="ignore")

    name: str
    path: str
    size: int = 0
