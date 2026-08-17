"""Platform architecture validation: 32-bit (x86) and ARM64 natives classifiers / Adoptium parameter mapping.

(Not actually run on 32-bit/ARM machines; only verifies the code logic: tests as documentation.)
"""

import httpx
import respx

from launcher.java.install import fetch_assets
from launcher.meta.rules import Platform, native_classifier
from launcher.meta.version import Library

X86 = Platform(os="windows", arch="x86", version="10.0")
X64 = Platform(os="windows", arch="x64", version="10.0")
ARM64 = Platform(os="windows", arch="arm64", version="10.0")


def _lwjgl() -> Library:
    return Library.model_validate(
        {
            "name": "org.lwjgl:lwjgl:3.3.3",
            "natives": {"windows": "natives-windows-${arch}"},
            "downloads": {
                "classifiers": {
                    "natives-windows": {},
                    "natives-windows-32": {},
                    "natives-windows-64": {},
                    "natives-windows-arm64": {},
                }
            },
        }
    )


def test_native_classifier_x86_picks_32():
    """32-bit Windows: the legacy natives map expands to natives-windows-32."""
    assert native_classifier(_lwjgl(), X86) == "natives-windows-32"


def test_native_classifier_x64_picks_64():
    assert native_classifier(_lwjgl(), X64) == "natives-windows-64"


def test_native_classifier_arm64():
    assert native_classifier(_lwjgl(), ARM64) == "natives-windows-arm64"


def test_native_classifier_modern_4th_segment_x86():
    """Modern format (the 4th natives-* segment) also returns the original classifier on x86."""
    lib = Library.model_validate(
        {
            "name": "org.lwjgl:lwjgl:3.3.3:natives-windows",
            "downloads": {"classifiers": {"natives-windows": {}}},
        }
    )
    assert native_classifier(lib, X86) == "natives-windows"


@respx.mock
def test_adoptium_arch_mapping():
    """Adoptium query: x86 -> architecture=x86, arm64 -> architecture=aarch64."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=[])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetch_assets(21, platform=X86, client=client)
    fetch_assets(21, platform=ARM64, client=client)
    assert "architecture=x86" in seen[0]
    assert "architecture=aarch64" in seen[1]
