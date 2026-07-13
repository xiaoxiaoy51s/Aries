"""computer_use 技能生命周期：与 Agent SSE 流对齐，关闭 codex-computer-use.exe 控制层。

computer_use 作为用户插件安装在 ``~/.Aries/plugins/skills/computer_use/``，运行时由
``plugin_manager`` 以 ``importlib.util.spec_from_file_location`` 加载（模块名为
``_plugin_skill_computer_use``），而**不是** ``plugins.skills.computer_use`` 子模块。

因此这里不能依赖 ``from plugins.skills.computer_use import ...``：``backend/plugins``
是带 ``__init__.py`` 的普通包，import 时会锁定到内置的 ``backend/plugins/skills/``，
找不到用户额外安装的 computer_use，抛 ``ModuleNotFoundError``。该异常若被上层静默吞掉，
会导致 release / ESC 监听永不生效，``codex-computer-use.exe`` 残留，屏幕蓝色控制闪光
在任务结束后不消失。

本模块改为直接定位 skill 目录并注入 ``sys.path`` 后 ``import sky_client`` / ``import
win_backend``：二者均为模块级单例，与工具执行时加载的是同一个模块对象，故
``close_client()`` 关闭的就是工具启动的那个 exe 进程。
"""
from __future__ import annotations

import logging
import platform
import sys
from pathlib import Path
from typing import Callable

_log = logging.getLogger(__name__)

# computer_use skill 的候选安装位置（优先 plugins/skills，即用户实际安装路径）
_CU_CANDIDATES = (
    Path.home() / ".Aries" / "plugins" / "skills" / "computer_use",
    Path.home() / ".Aries" / "skills" / "computer_use",
)


def _computer_use_dir() -> Path | None:
    """定位 computer_use skill 目录，找不到返回 None。"""
    for c in _CU_CANDIDATES:
        if c.is_dir() and (c / "__init__.py").is_file():
            return c
    return None


def _ensure_computer_use_import_paths() -> bool:
    """把 computer_use 目录及其 scripts 目录加入 sys.path。

    返回 True 表示已就绪；False 表示找不到 skill 目录，调用方应跳过。幂等。
    """
    cu = _computer_use_dir()
    if cu is None:
        return False
    for p in (cu / "scripts", cu):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)
    return True


def release_computer_use_client() -> bool:
    """关闭 codex-computer-use.exe 及其屏幕控制层。幂等，失败时返回 False。"""
    try:
        if platform.system() != "Windows":
            return False
        if not _ensure_computer_use_import_paths():
            return False
        # sky_client 是模块级单例：close_client() 关闭的就是工具执行时启动的 exe。
        from sky_client import close_client
        close_client()
        return True
    except Exception as exc:
        _log.debug("release_computer_use_client failed: %s", exc)
        return False


def stop_computer_use_esc_listener() -> None:
    """停止 computer_use 的 ESC 全局热键监听。"""
    try:
        if platform.system() != "Windows":
            return
        if not _ensure_computer_use_import_paths():
            return
        import win_backend as _cu_win
        _cu_win.stop_esc_listener()
    except Exception as exc:
        _log.debug("stop_computer_use_esc_listener failed: %s", exc)


def start_computer_use_esc_listener(on_esc: Callable[[], None]) -> bool:
    """启动 computer_use 的 ESC 全局热键监听。成功返回 True，否则 False。"""
    try:
        if platform.system() != "Windows":
            return False
        if not _ensure_computer_use_import_paths():
            return False
        import win_backend as _cu_win
        _cu_win.start_esc_listener(on_esc)
        return True
    except Exception as exc:
        _log.debug("start_computer_use_esc_listener failed: %s", exc)
        return False
