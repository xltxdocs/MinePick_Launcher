"""模组与加载器数据模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LoaderVersion(BaseModel):
    """加载器版本（含安装器下载信息）。"""

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
    """Modrinth 项目的某个版本。"""

    model_config = ConfigDict(extra="ignore")

    version_id: str
    version_number: str = ""
    loaders: list[str] = []
    game_versions: list[str] = []
    files: list[ModFile] = []
    dependencies: list[ModDependency] = []


class ModInfo(BaseModel):
    """面向 UI 的模组信息；依赖仅提示不强制安装。"""

    model_config = ConfigDict(extra="ignore")

    slug: str
    title: str
    description: str = ""
    depends: list[str] = []  # 必要前置（slug 列表）
    optional_depends: list[str] = []  # 可选前置（slug 列表）


class ModSearchHit(BaseModel):
    """Modrinth 搜索结果条目。"""

    model_config = ConfigDict(extra="ignore")

    slug: str
    title: str
    description: str = ""
    downloads: int = 0
    icon_url: str = ""


class InstalledContent(BaseModel):
    """已安装内容文件条目（mods / resourcepacks / shaderpacks）。"""

    model_config = ConfigDict(extra="ignore")

    name: str
    path: str
    size: int = 0
