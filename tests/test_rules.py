from launcher.meta.rules import (
    Platform,
    allowed,
    native_classifier,
    resolve_libraries,
)
from launcher.meta.version import Library, OsRule, Rule

WIN = Platform(os="windows", arch="x64", version="10.0.26100")
WIN_X86 = Platform(os="windows", arch="x86", version="10.0.26100")
MAC = Platform(os="osx", arch="arm64", version="14.5.0")
LINUX = Platform(os="linux", arch="arm64", version="6.8.0")


def test_no_rules_default_allowed():
    assert allowed(None, WIN) is True
    assert allowed([], WIN) is True


def test_exclude_os_pattern():
    # 真实模式（1.8.9 lwjgl 主库）：全部允许，再排除 osx
    rules = [Rule(action="allow"), Rule(action="disallow", os=OsRule(name="osx"))]
    assert allowed(rules, WIN) is True
    assert allowed(rules, MAC) is False
    assert allowed(rules, LINUX) is True


def test_single_allow_rule():
    # 单条 allow(osx)：其它平台不命中 -> 初始 False
    rules = [Rule(action="allow", os=OsRule(name="osx"))]
    assert allowed(rules, MAC) is True
    assert allowed(rules, WIN) is False
    assert allowed(rules, LINUX) is False


def test_os_version_regex():
    rule = Rule(action="allow", os=OsRule(name="osx", version=r"14\..*"))
    assert allowed([rule], MAC) is True
    assert allowed([rule], Platform(os="osx", arch="x64", version="13.1.0")) is False


def test_features_demo():
    demo_allow = Rule(action="allow", features={"is_demo_user": True})
    assert allowed([demo_allow], WIN) is False  # 非 demo：规则不命中
    assert (
        allowed([demo_allow], WIN, features=frozenset({"is_demo_user"})) is True
    )


def test_native_classifier_natives_map():
    lib = Library(
        name="org.lwjgl.lwjgl:lwjgl-platform:2.9.1",
        natives={
            "windows": "natives-windows",
            "osx": "natives-osx",
            "linux": "natives-linux",
        },
    )
    assert native_classifier(lib, WIN) == "natives-windows"
    assert native_classifier(lib, MAC) == "natives-osx"
    only_win = Library(
        name="x:y:1", natives={"windows": "natives-windows"}
    )
    assert native_classifier(only_win, MAC) is None


def test_native_classifier_arch_placeholder():
    # 真实模式（1.8.9 twitch-platform）：natives 值含 ${arch}
    lib = Library(
        name="tv.twitch:twitch-platform:6.5",
        natives={"windows": "natives-windows-${arch}"},
        downloads={
            "classifiers": {
                "natives-windows-32": {},
                "natives-windows-64": {},
            }
        },
    )
    assert native_classifier(lib, WIN) == "natives-windows-64"
    assert native_classifier(lib, WIN_X86) == "natives-windows-32"


def test_native_classifier_name_segment():
    # 现代格式（1.20.1）：库名第 4 段为分类器
    lib = Library(name="org.lwjgl:lwjgl-glfw:3.3.1:natives-windows-arm64")
    assert native_classifier(lib, WIN) == "natives-windows-arm64"


def test_resolve_libraries_rule_filtering():
    libs = [
        Library(
            name="net.java.dev.jna:jna:5.13.0",
            rules=[Rule(action="allow", os=OsRule(name="linux", arch="arm64"))],
            downloads={"classifiers": {"natives-linux-arm64": {}}},
        ),
        Library(
            name="org.lwjgl:lwjgl:3.3.3",
            downloads={"classifiers": {"natives-windows": {}}},
        ),
    ]
    res = resolve_libraries(libs, WIN)
    assert [r.library.name for r in res] == ["org.lwjgl:lwjgl:3.3.3"]
    res2 = resolve_libraries(libs, LINUX)
    assert res2[0].classifier == "natives-linux-arm64"


def test_forge_style_client_classifier_is_main():
    # net.minecraftforge:forge:1.20.1-47.4.22:client —— 第 4 段不是 natives，
    # 必须进入主类路径（classifier=None）
    lib = Library(
        name="net.minecraftforge:forge:1.20.1-47.4.22:client",
        downloads={
            "artifact": {
                "path": "net/minecraftforge/forge/1.20.1-47.4.22/forge-1.20.1-47.4.22-client.jar",
                "sha1": "a",
                "size": 1,
                "url": "https://x/forge-client.jar",
            }
        },
    )
    assert native_classifier(lib, WIN) is None
    res = resolve_libraries([lib], WIN)
    assert len(res) == 1
    assert res[0].classifier is None


def test_resolve_libraries_arch_variants():
    # 同 OS 多架构变体（1.20.1 lwjgl-glfw）：按架构过滤
    libs = [
        Library(
            name="org.lwjgl:lwjgl-glfw:3.3.1:natives-windows",
            rules=[Rule(action="allow", os=OsRule(name="windows"))],
        ),
        Library(
            name="org.lwjgl:lwjgl-glfw:3.3.1:natives-windows-x86",
            rules=[Rule(action="allow", os=OsRule(name="windows"))],
        ),
        Library(
            name="org.lwjgl:lwjgl-glfw:3.3.1:natives-windows-arm64",
            rules=[Rule(action="allow", os=OsRule(name="windows"))],
        ),
        Library(
            name="org.lwjgl:lwjgl-glfw:3.3.1:natives-linux",
            rules=[Rule(action="allow", os=OsRule(name="linux"))],
        ),
    ]
    res = resolve_libraries(libs, WIN)
    assert [r.classifier for r in res] == ["natives-windows"]
    res_x86 = resolve_libraries(libs, WIN_X86)
    assert [r.classifier for r in res_x86] == ["natives-windows-x86"]
    linux_x64 = Platform(os="linux", arch="x64", version="6.8.0")
    res_linux = resolve_libraries(libs, linux_x64)
    assert [r.classifier for r in res_linux] == ["natives-linux"]
    # arm64 linux 不匹配无后缀（x64 默认）变体
    assert resolve_libraries(libs, LINUX) == []
