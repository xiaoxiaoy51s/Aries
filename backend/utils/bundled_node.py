"""安装包内置 Node.js：首次启动释放到 ~/.Aries/runtimes/node/versions/<version>/"""
from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

from utils.app_paths import get_executable_dir
from utils.runtime_manager import get_runtimes_root

logger = logging.getLogger(__name__)

# 与 RUNTIME_DOWNLOAD_INFO["node"]["version"] 保持一致
DEFAULT_BUNDLED_NODE_VERSION = "v20.17.0"


def _node_exe_name() -> str:
    return "node.exe" if sys.platform == "win32" else "bin/node"


def get_staged_node_root() -> Path | None:
    """安装包 resources/node/（与 aries_backend.exe 同级）。"""
    root = get_executable_dir() / "node"
    exe = root / _node_exe_name() if sys.platform != "win32" else root / "node.exe"
    if exe.is_file():
        return root
    return None


def get_default_node_install_dir() -> Path:
    return get_runtimes_root() / "node" / "versions" / DEFAULT_BUNDLED_NODE_VERSION


def get_default_node_exe() -> Path:
    return get_default_node_install_dir() / ("node.exe" if sys.platform == "win32" else "bin/node")


def ensure_bundled_node_installed() -> Path | None:
    """首次运行：把安装包内的 Node 复制到 ~/.Aries/runtimes/node/versions/v20.17.0/。

    已存在则跳过。开发模式无 staged node 时不做任何事。
    """
    target_dir = get_default_node_install_dir()
    target_exe = get_default_node_exe()
    if target_exe.is_file():
        return target_dir

    staged = get_staged_node_root()
    if not staged:
        return None

    logger.info("释放内置 Node.js 到 %s", target_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(staged, target_dir)
    print(f"[Node] 已释放内置 Node.js 到 {target_dir}")
    return target_dir


def resolve_bundled_node_path() -> str:
    """返回应优先使用的 Node 路径（~/.Aries 内置 > 安装包 staging）。"""
    ensure_bundled_node_installed()
    if get_default_node_exe().is_file():
        return str(get_default_node_exe())
    staged = get_staged_node_root()
    if staged:
        exe = staged / ("node.exe" if sys.platform == "win32" else "bin/node")
        if exe.is_file():
            return str(exe)
    return ""
