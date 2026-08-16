"""#18 平台架构验证：32 位（x86）与 ARM64 的 natives 分类器 / Adoptium 参数映射。

（不实际在 32 位/ARM 机器上运行，仅确认代码逻辑：测试即文档。）
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
    """32 位 Windows：旧格式 natives 映射展开为 natives-windows-32。"""
    assert native_classifier(_lwjgl(), X86) == "natives-windows-32"


def test_native_classifier_x64_picks_64():
    assert native_classifier(_lwjgl(), X64) == "natives-windows-64"


def test_native_classifier_arm64():
    assert native_classifier(_lwjgl(), ARM64) == "natives-windows-arm64"


def test_native_classifier_modern_4th_segment_x86():
    """现代格式（第 4 段 natives-*）对 x86 平台同样返回原分类器。"""
    lib = Library.model_validate(
        {
            "name": "org.lwjgl:lwjgl:3.3.3:natives-windows",
            "downloads": {"classifiers": {"natives-windows": {}}},
        }
    )
    assert native_classifier(lib, X86) == "natives-windows"


@respx.mock
def test_adoptium_arch_mapping():
    """Adoptium 查询：x86 -> architecture=x86，arm64 -> architecture=aarch64。"""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=[])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetch_assets(21, platform=X86, client=client)
    fetch_assets(21, platform=ARM64, client=client)
    assert "architecture=x86" in seen[0]
    assert "architecture=aarch64" in seen[1]
