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

import os

from launcher.launch.command import LaunchProfile, build_argv
from launcher.meta.rules import Platform, ResolvedLibrary
from launcher.meta.version import Library, VersionJson

WIN = Platform(os="windows", arch="x64", version="10.0.26100")
MAC = Platform(os="osx", arch="arm64", version="14.5.0")

PROFILE = LaunchProfile(username="Steve", uuid="u-1", access_token="tok", user_type="legacy")

LEGACY_RAW = {
    "id": "1.8.9",
    "type": "release",
    "mainClass": "net.minecraft.client.main.Main",
    "minecraftArguments": (
        "--username ${auth_player_name} --version ${version_name} "
        "--gameDir ${game_directory} --assetsDir ${assets_root} "
        "--assetIndex ${assets_index_name} --uuid ${auth_uuid} "
        "--accessToken ${auth_access_token} --userProperties ${user_properties} "
        "--userType ${user_type}"
    ),
    "assetIndex": {"id": "1.8", "url": "https://x/1.8.json"},
    "libraries": [
        {
            "name": "com.example:lib1:1.0",
            "downloads": {
                "artifact": {
                    "path": "com/example/lib1/1.0/lib1-1.0.jar",
                    "sha1": "a",
                    "size": 1,
                    "url": "https://x/lib1.jar",
                }
            },
        }
    ],
    "downloads": {"client": {"sha1": "b", "size": 2, "url": "https://x/client.jar"}},
    "logging": {"client": {"argument": "-Dlog4j.configurationFile=${path}", "file": {"id": "c", "url": "https://x/c.xml"}}},
}

NEW_RAW = {
    "id": "1.20.1",
    "type": "release",
    "mainClass": "net.minecraft.client.main.Main",
    "arguments": {
        "game": [
            "--username",
            "${auth_player_name}",
            {"rules": [{"action": "allow", "features": {"is_demo_user": True}}], "value": "--demo"},
        ],
        "jvm": [
            {"rules": [{"action": "allow", "os": {"name": "osx"}}], "value": "-XstartOnFirstThread"},
            "-Xmx2G",
            "-Djava.library.path=${natives_directory}",
            "-Dminecraft.launcher.brand=${launcher_name}",
            "-cp",
            "${classpath}",
        ],
    },
    "javaVersion": {"component": "java-runtime-gamma", "majorVersion": 17},
    "assetIndex": {"id": "5", "url": "https://x/5.json"},
    "libraries": [
        {
            "name": "com.example:lib1:1.0",
            "downloads": {
                "artifact": {
                    "path": "com/example/lib1/1.0/lib1-1.0.jar",
                    "sha1": "a",
                    "size": 1,
                    "url": "https://x/lib1.jar",
                }
            },
        }
    ],
    "downloads": {"client": {"sha1": "b", "size": 2, "url": "https://x/client.jar"}},
    "logging": {"client": {"argument": "-Dlog4j.configurationFile=${path}", "file": {"id": "c", "url": "https://x/c.xml"}}},
}


def _one_lib() -> ResolvedLibrary:
    return ResolvedLibrary(
        library=Library(
            name="com.example:lib1:1.0",
            downloads={
                "artifact": {
                    "path": "com/example/lib1/1.0/lib1-1.0.jar",
                    "sha1": "a",
                    "size": 1,
                    "url": "https://x/lib1.jar",
                }
            },
        ),
        classifier=None,
    )


def test_build_argv_legacy(ws_tmp):
    version = VersionJson.model_validate(LEGACY_RAW)
    cmd = build_argv(
        version,
        game_dir=ws_tmp / "mc",
        libraries_dir=ws_tmp / "mc" / "libraries",
        natives_dir=ws_tmp / "mc" / "versions" / "1.8.9" / "natives",
        java_path=ws_tmp / "java.exe",
        java_major=8,
        profile=PROFILE,
        platform=WIN,
        resolved_libraries=[_one_lib()],
        memory_gb=4,
    )
    argv = cmd.argv
    assert argv[0] == str(ws_tmp / "java.exe")
    i_main = argv.index("net.minecraft.client.main.Main")
    jvm = argv[1:i_main]
    game = argv[i_main + 1 :]
    assert "-Xmx4G" in jvm
    natives = str(ws_tmp / "mc" / "versions" / "1.8.9" / "natives")
    assert "-Djava.library.path=" + natives in jvm
    assert "-Dlog4j.configurationFile=" + str(ws_tmp / "mc" / "assets" / "log_configs" / "1.8") in jvm
    classpath = jvm[jvm.index("-cp") + 1]
    sep = os.pathsep
    assert classpath.split(sep)[0].endswith("1.8.9.jar")
    assert classpath.split(sep)[1].endswith("com" + os.sep + "example" + os.sep + "lib1" + os.sep + "1.0" + os.sep + "lib1-1.0.jar")
    assert "--username" in game and "Steve" in game
    assert "--userType" in game and "legacy" in game
    assert "--userProperties" in game and "{}" in game
    assert "--accessToken" in game and "tok" in game
    assert cmd.cwd == ws_tmp / "mc"


def test_build_argv_modern(ws_tmp):
    version = VersionJson.model_validate(NEW_RAW)
    cmd = build_argv(
        version,
        game_dir=ws_tmp / "mc",
        libraries_dir=ws_tmp / "mc" / "libraries",
        natives_dir=ws_tmp / "mc" / "versions" / "1.20.1" / "natives",
        java_path=ws_tmp / "java.exe",
        java_major=17,
        profile=PROFILE,
        platform=WIN,
        resolved_libraries=[_one_lib()],
        memory_gb=6,
    )
    argv = cmd.argv
    # osx-only args are filtered; -Xmx2G is replaced with 6G; demo not enabled
    assert "-XstartOnFirstThread" not in argv
    assert "-Xmx2G" not in argv
    assert "-Xmx6G" in argv
    assert "--demo" not in argv
    assert "-Dminecraft.launcher.brand=MinePick Launcher" in argv
    # demo mode
    cmd2 = build_argv(
        version,
        game_dir=ws_tmp / "mc",
        libraries_dir=ws_tmp / "mc" / "libraries",
        natives_dir=ws_tmp / "mc" / "versions" / "1.20.1" / "natives",
        java_path=ws_tmp / "java.exe",
        java_major=17,
        profile=PROFILE,
        platform=WIN,
        resolved_libraries=[_one_lib()],
        memory_gb=6,
        demo=True,
    )
    assert "--demo" in cmd2.argv


def test_build_argv_language_and_isolation(ws_tmp):
    version = VersionJson.model_validate(NEW_RAW)
    # non-isolated + zh_cn
    cmd = build_argv(
        version,
        game_dir=ws_tmp / "mc",
        libraries_dir=ws_tmp / "mc" / "libraries",
        natives_dir=ws_tmp / "mc" / "versions" / "1.20.1" / "natives",
        java_path=ws_tmp / "java.exe",
        java_major=17,
        profile=PROFILE,
        platform=WIN,
        resolved_libraries=[_one_lib()],
        language="zh_cn",
    )
    game = cmd.argv[cmd.argv.index("net.minecraft.client.main.Main") + 1 :]
    assert game[-2:] == ["--lang", "zh_cn"]
    assert cmd.cwd == ws_tmp / "mc"
    # isolated mode: cwd and gameDir point to versions/<id>
    cmd2 = build_argv(
        version,
        game_dir=ws_tmp / "mc",
        libraries_dir=ws_tmp / "mc" / "libraries",
        natives_dir=ws_tmp / "mc" / "versions" / "1.20.1" / "natives",
        java_path=ws_tmp / "java.exe",
        java_major=17,
        profile=PROFILE,
        platform=WIN,
        resolved_libraries=[_one_lib()],
        isolated=True,
        language="en_us",
    )
    assert cmd2.cwd == ws_tmp / "mc" / "versions" / "1.20.1"
    game2 = cmd2.argv[cmd2.argv.index("net.minecraft.client.main.Main") + 1 :]
    assert game2[-2:] == ["--lang", "en_us"]
    assert (ws_tmp / "mc" / "versions" / "1.20.1" / "mods").is_dir()
    # the language is written via options.txt (inside the isolated directory, no BOM)
    options = ws_tmp / "mc" / "versions" / "1.20.1" / "options.txt"
    assert options.read_text(encoding="utf-8") == "lang:en_us\n"
    # legacy format (minecraftArguments contains --gameDir): gameDir points to the version directory when isolated
    legacy = VersionJson.model_validate(LEGACY_RAW)
    cmd3 = build_argv(
        legacy,
        game_dir=ws_tmp / "mc",
        libraries_dir=ws_tmp / "mc" / "libraries",
        natives_dir=ws_tmp / "mc" / "versions" / "1.8.9" / "natives",
        java_path=ws_tmp / "java.exe",
        java_major=8,
        profile=PROFILE,
        platform=WIN,
        resolved_libraries=[_one_lib()],
        isolated=True,
        language="zh_cn",
    )
    game3 = cmd3.argv[cmd3.argv.index("net.minecraft.client.main.Main") + 1 :]
    i_gd = game3.index("--gameDir")
    assert game3[i_gd + 1] == str(ws_tmp / "mc" / "versions" / "1.8.9")
    assert game3[-2:] == ["--lang", "zh_cn"]


def test_ensure_options_lang(ws_tmp):
    from launcher.launch.command import _ensure_options_lang

    path = ws_tmp / "options.txt"
    _ensure_options_lang(path, "zh_cn")
    assert path.read_text(encoding="utf-8") == "lang:zh_cn\n"
    # keeps other settings, only replaces the lang line
    path.write_text("fov:70\nlang:en_us\ngamma:1.0\n", encoding="utf-8")
    _ensure_options_lang(path, "zh_cn")
    text = path.read_text(encoding="utf-8")
    assert "lang:zh_cn" in text
    assert "fov:70" in text and "gamma:1.0" in text
    assert "lang:en_us" not in text
    # legacy files with a BOM are handled too
    path.write_bytes(b"\xef\xbb\xbflang:en_us\n")
    _ensure_options_lang(path, "zh_cn")
    assert path.read_text(encoding="utf-8") == "lang:zh_cn\n"


def test_build_argv_dedupes_classpath(ws_tmp):
    version = VersionJson.model_validate(NEW_RAW)
    duplicate_lib = _one_lib()
    cmd = build_argv(
        version,
        game_dir=ws_tmp / "mc",
        libraries_dir=ws_tmp / "mc" / "libraries",
        natives_dir=ws_tmp / "mc" / "versions" / "1.20.1" / "natives",
        java_path=ws_tmp / "java.exe",
        java_major=17,
        profile=PROFILE,
        platform=WIN,
        resolved_libraries=[duplicate_lib, duplicate_lib],  # duplicate libraries
    )
    i_main = cmd.argv.index("net.minecraft.client.main.Main")
    jvm = cmd.argv[1:i_main]
    classpath = jvm[jvm.index("-cp") + 1]
    entries = classpath.split(os.pathsep)
    assert len(entries) == len(set(entries))  # no duplicates
    assert entries[0].endswith("1.20.1.jar")


def test_build_argv_assets_dir_override(ws_tmp):
    version = VersionJson.model_validate(LEGACY_RAW)
    shared_assets = ws_tmp / "shared" / "assets"
    cmd = build_argv(
        version,
        game_dir=ws_tmp / "instances" / "myinst",
        libraries_dir=ws_tmp / "shared" / "libraries",
        natives_dir=ws_tmp / "instances" / "myinst" / "versions" / "1.8.9" / "natives",
        java_path=ws_tmp / "java.exe",
        java_major=8,
        profile=PROFILE,
        platform=WIN,
        resolved_libraries=[_one_lib()],
        assets_dir=shared_assets,
    )
    i_main = cmd.argv.index("net.minecraft.client.main.Main")
    game = cmd.argv[i_main + 1 :]
    i_assets = game.index("--assetsDir")
    assert game[i_assets + 1] == str(shared_assets)  # assets point to the shared directory
    jvm = cmd.argv[1:i_main]
    assert any(str(shared_assets / "log_configs" / "1.8") in a for a in jvm)


def test_build_argv_argfile_for_long_classpath(ws_tmp):
    version = VersionJson.model_validate(NEW_RAW)
    long_libs = [
        ResolvedLibrary(
            library=Library(
                name="g" + str(i) + ":a:v",
                downloads={
                    "artifact": {
                        "path": "very/long/path/" + "x" * 180 + "/lib" + str(i) + ".jar",
                        "sha1": "a",
                        "size": 1,
                        "url": "https://x/l.jar",
                    }
                },
            ),
            classifier=None,
        )
        for i in range(40)
    ]
    cmd = build_argv(
        version,
        game_dir=ws_tmp / "mc",
        libraries_dir=ws_tmp / "mc" / "libraries",
        natives_dir=ws_tmp / "mc" / "versions" / "1.20.1" / "natives",
        java_path=ws_tmp / "java.exe",
        java_major=17,
        profile=PROFILE,
        platform=WIN,
        resolved_libraries=long_libs,
    )
    assert cmd.argfile is not None
    assert cmd.argfile.exists()
    assert "@" + str(cmd.argfile) in cmd.argv
    assert cmd.argfile.read_text(encoding="utf-8").endswith(".jar")


def test_build_argv_no_argfile_java8(ws_tmp):
    version = VersionJson.model_validate(NEW_RAW)
    long_libs = [
        ResolvedLibrary(
            library=Library(
                name="g" + str(i) + ":a:v",
                downloads={
                    "artifact": {
                        "path": "very/long/path/" + "x" * 180 + "/l" + str(i) + ".jar",
                        "sha1": "a",
                        "size": 1,
                        "url": "https://x/l.jar",
                    }
                },
            ),
            classifier=None,
        )
        for i in range(40)
    ]
    cmd = build_argv(
        version,
        game_dir=ws_tmp / "mc",
        libraries_dir=ws_tmp / "mc" / "libraries",
        natives_dir=ws_tmp / "mc" / "versions" / "1.20.1" / "natives",
        java_path=ws_tmp / "java.exe",
        java_major=8,
        profile=PROFILE,
        platform=WIN,
        resolved_libraries=long_libs,
    )
    assert cmd.argfile is None  # Java 8 does not support @argfile, stays inline
    assert any(len(arg) > 7000 for arg in cmd.argv)


def test_build_argv_extra_jvm_args(ws_tmp):
    version = VersionJson.model_validate(NEW_RAW)
    cmd = build_argv(
        version,
        game_dir=ws_tmp / "mc",
        libraries_dir=ws_tmp / "mc" / "libraries",
        natives_dir=ws_tmp / "mc" / "versions" / "1.20.1" / "natives",
        java_path=ws_tmp / "java.exe",
        java_major=17,
        profile=PROFILE,
        platform=WIN,
        resolved_libraries=[_one_lib()],
        extra_jvm_args='-XX:+UseG1GC -Dfile.encoding="UTF-8" -Xmx8G -Xms2G',
    )
    jvm = cmd.argv[1 : cmd.argv.index("net.minecraft.client.main.Main")]
    assert "-XX:+UseG1GC" in jvm
    assert "-Dfile.encoding=UTF-8" in jvm  # quotes are stripped
    # -Xmx/-Xms are dropped; memory is controlled by the memory setting
    assert not any(arg.startswith("-Xms") for arg in jvm)
    assert jvm.count("-Xmx4G") == 1
    assert not any(arg.startswith("-Xmx") and arg != "-Xmx4G" for arg in jvm)


def test_build_argv_server_args(ws_tmp):
    version = VersionJson.model_validate(NEW_RAW)
    cmd = build_argv(
        version,
        game_dir=ws_tmp / "mc",
        libraries_dir=ws_tmp / "mc" / "libraries",
        natives_dir=ws_tmp / "mc" / "versions" / "1.20.1" / "natives",
        java_path=ws_tmp / "java.exe",
        java_major=17,
        profile=PROFILE,
        platform=WIN,
        resolved_libraries=[_one_lib()],
        server="mc.example.com",
        server_port=25565,
    )
    game = cmd.argv[cmd.argv.index("net.minecraft.client.main.Main") + 1 :]
    i = game.index("--server")
    assert game[i + 1] == "mc.example.com"
    assert game[game.index("--port") + 1] == "25565"


def test_build_argv_no_extra_jvm_args(ws_tmp):
    version = VersionJson.model_validate(NEW_RAW)
    cmd = build_argv(
        version,
        game_dir=ws_tmp / "mc",
        libraries_dir=ws_tmp / "mc" / "libraries",
        natives_dir=ws_tmp / "mc" / "versions" / "1.20.1" / "natives",
        java_path=ws_tmp / "java.exe",
        java_major=17,
        profile=PROFILE,
        platform=WIN,
        resolved_libraries=[_one_lib()],
        extra_jvm_args="   ",
    )
    jvm = cmd.argv[1 : cmd.argv.index("net.minecraft.client.main.Main")]
    assert jvm.count("-Xmx4G") == 1

def test_split_extra_jvm_args_unbalanced_quote(ws_tmp):
    from launcher.launch.command import _split_extra_jvm_args

    # unbalanced quotes: no exception, degrades to splitting on whitespace
    args = _split_extra_jvm_args('-XX:+UseG1GC -Dfile.encoding="UTF-8')
    assert "-XX:+UseG1GC" in args
    assert any("UTF-8" in a for a in args)

