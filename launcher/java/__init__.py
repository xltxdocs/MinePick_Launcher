"""Java runtime detection and Adoptium download."""

from launcher.java.install import JavaAsset, fetch_assets, install_java
from launcher.java.locate import (
    JavaError,
    JavaRuntime,
    has_suitable_java,
    list_java,
    match_java,
    parse_java_major,
    probe_java_major,
)

__all__ = [
    "JavaAsset",
    "JavaError",
    "JavaRuntime",
    "fetch_assets",
    "has_suitable_java",
    "install_java",
    "list_java",
    "match_java",
    "parse_java_major",
    "probe_java_major",
]
