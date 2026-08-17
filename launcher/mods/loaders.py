"""Loader version sources: Fabric / Forge / NeoForge (unified LoaderVersion abstraction)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from launcher.i18n import describe_network_error, tr_core
from launcher.meta.manifest import _new_client
from launcher.mods.models import LoaderVersion

FABRIC_META = "https://meta.fabricmc.net/v2"
FORGE_PROMOTIONS_URL = (
    "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
)
FORGE_MAVEN_BASE = "https://maven.minecraftforge.net/net/minecraftforge/forge/"
NEOFORGE_METADATA_URL = (
    "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
)
NEOFORGE_MAVEN_BASE = "https://maven.neoforged.net/releases/net/neoforged/neoforge/"

LOADERS = ("fabric", "forge", "neoforge")


class ModsError(Exception):
    """Mod/loader-related error (user-facing message)."""


def _get_json(url: str, client: httpx.Client | None) -> list | dict:
    own = client is None
    if own:
        client = _new_client()
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise ModsError(
            tr_core("mods.request_failed", url, describe_network_error(exc))
        ) from exc
    finally:
        if own:
            client.close()


def _get_text(url: str, client: httpx.Client | None) -> str:
    own = client is None
    if own:
        client = _new_client()
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError as exc:
        raise ModsError(
            tr_core("mods.request_failed", url, describe_network_error(exc))
        ) from exc
    finally:
        if own:
            client.close()


def _fabric_versions(
    game_version: str, client: httpx.Client | None
) -> list[LoaderVersion]:
    loaders = _get_json(FABRIC_META + "/versions/loader", client)
    installers = _get_json(FABRIC_META + "/versions/installer", client)
    installer_url = installers[0]["url"] if installers else ""
    out: list[LoaderVersion] = []
    for entry in loaders:
        if not entry.get("stable", True):
            continue
        out.append(
            LoaderVersion(
                loader="fabric",
                version=entry["version"],
                game_version=game_version,
                stable=True,
                installer_url=installer_url,
            )
        )
    return out


def _forge_versions(
    game_version: str, client: httpx.Client | None
) -> list[LoaderVersion]:
    data = _get_json(FORGE_PROMOTIONS_URL, client)
    promos = data.get("promos", {})
    out: list[LoaderVersion] = []
    for suffix, recommended in (("-recommended", True), ("-latest", False)):
        key = game_version + suffix
        version = promos.get(key)
        if not version:
            continue
        out.append(
            LoaderVersion(
                loader="forge",
                version=version,
                game_version=game_version,
                stable=True,
                recommended=recommended,
                installer_url=(
                    FORGE_MAVEN_BASE + game_version + "-" + version + "/forge-"
                    + game_version + "-" + version + "-installer.jar"
                ),
            )
        )
    return out


def _version_key(value: str) -> tuple:
    """Sort key that prefers numeric segments and falls back to non-numeric ones (e.g. 20.2.12-beta)."""
    parts: list[tuple[int, object]] = []
    for part in value.split("."):
        try:
            parts.append((0, int(part)))
        except ValueError:
            parts.append((1, part))
    return tuple(parts)


def _neoforge_base(game_version: str) -> str:
    """MC version -> NeoForge version prefix (1.20.2 -> 20.2; 26.1.2 -> 26.1.2)."""
    if game_version.startswith("1."):
        return game_version[2:]
    return game_version


def _neoforge_versions(
    game_version: str, client: httpx.Client | None
) -> list[LoaderVersion]:
    xml_text = _get_text(NEOFORGE_METADATA_URL, client)
    root = ET.fromstring(xml_text)
    base = _neoforge_base(game_version)
    versions = [
        node.text
        for node in root.findall(".//version")
        if node.text
        and node.text.startswith(base + ".")
        and "-" not in node.text  # skip pre-release builds like beta/rc
    ]
    versions.sort(key=_version_key)
    out: list[LoaderVersion] = []
    for version in reversed(versions[-20:]):  # newest first
        out.append(
            LoaderVersion(
                loader="neoforge",
                version=version,
                game_version=game_version,
                stable=True,
                installer_url=(
                    NEOFORGE_MAVEN_BASE + version + "/neoforge-" + version
                    + "-installer.jar"
                ),
            )
        )
    return out


def list_loader_versions(
    loader: str, game_version: str, *, client: httpx.Client | None = None
) -> list[LoaderVersion]:
    """List the available versions of a loader for a given MC version (newest to oldest)."""
    if loader == "fabric":
        return _fabric_versions(game_version, client)  # API already returns newest-first
    if loader == "forge":
        return list(reversed(_forge_versions(game_version, client)))  # latest first
    if loader == "neoforge":
        return _neoforge_versions(game_version, client)  # already newest-first
    raise ModsError(tr_core("mods.unknown_loader", loader))


def list_game_versions(loader: str, *, client: httpx.Client | None = None) -> list[str]:
    """List the MC versions supported by a loader."""
    if loader == "fabric":
        data = _get_json(FABRIC_META + "/versions/game", client)
        return [entry["version"] for entry in data if entry.get("stable", True)]
    if loader == "forge":
        data = _get_json(FORGE_PROMOTIONS_URL, client)
        promos = data.get("promos", {})
        versions = sorted({key.rsplit("-", 1)[0] for key in promos})
        return list(reversed(versions))
    if loader == "neoforge":
        xml_text = _get_text(NEOFORGE_METADATA_URL, client)
        root = ET.fromstring(xml_text)
        bases: set[str] = set()
        for node in root.findall(".//version"):
            if not node.text:
                continue
            parts = node.text.split(".")
            if len(parts) == 3:
                # 20.2.88 -> MC 1.20.2
                bases.add("1." + ".".join(parts[:2]))
            elif len(parts) >= 4:
                # 26.1.2.95 -> MC 26.1.2
                bases.add(".".join(parts[:3]))
        return sorted(bases, reverse=True)
    raise ModsError(tr_core("mods.unknown_loader", loader))
