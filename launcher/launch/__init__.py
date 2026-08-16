"""M5：启动（natives 解压、命令组装、进程管理、编排）。"""

from launcher.launch.command import LaunchCommand, LaunchProfile, build_argv
from launcher.launch.natives import LaunchError, prepare_natives
from launcher.launch.orchestrate import (
    JavaMissingError,
    OfflineLockedError,
    PreparedLaunch,
    prepare_launch,
    resolve_launch_account,
)
from launcher.launch.runner import find_new_crash_reports, run_process

__all__ = [
    "JavaMissingError",
    "LaunchCommand",
    "LaunchError",
    "LaunchProfile",
    "OfflineLockedError",
    "PreparedLaunch",
    "build_argv",
    "find_new_crash_reports",
    "prepare_launch",
    "prepare_natives",
    "resolve_launch_account",
    "run_process",
]
