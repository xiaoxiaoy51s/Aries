"""释放内置 computer-use MCP server 到 ~/.Aries/plugins/mcps/computer-use/

逻辑与 bundled_node.py 一致：首次启动时把安装包内的 mcp-server + exe
复制到用户目录，已存在则跳过。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from utils.app_paths import get_executable_dir

# 源：安装包 resources/mcp-server/ 和 resources/codex-computer-use.exe
# 开发模式：项目根目录 frontend/resources/
_STAGED_MCP_DIR = get_executable_dir() / "mcp-server"
_STAGED_EXE = get_executable_dir() / "codex-computer-use.exe"

# 目标：~/.Aries/plugins/mcps/computer-use/
_TARGET_DIR = Path.home() / ".Aries" / "plugins" / "mcps" / "computer-use"


def get_staged_mcp_dir() -> Path | None:
    if _STAGED_MCP_DIR.is_dir():
        return _STAGED_MCP_DIR
    return None


def ensure_bundled_mcp_installed() -> Path | None:
    """首次运行：把 mcp-server + exe 复制到 ~/.Aries/plugins/mcps/computer-use/。

    已存在则跳过。开发模式无 staged 文件时不做任何事。
    """
    staged = get_staged_mcp_dir()
    if not staged:
        return None

    # 标记文件：index.mjs 存在则认为已释放
    if (_TARGET_DIR / "index.mjs").is_file():
        return _TARGET_DIR

    _TARGET_DIR.mkdir(parents=True, exist_ok=True)

    # 复制 mcp-server 内容
    if _TARGET_DIR.exists():
        shutil.rmtree(_TARGET_DIR)
    shutil.copytree(staged, _TARGET_DIR)

    # 复制 exe（放到 computer-use/ 下，sky_client.js 指向 ../codex-computer-use.exe）
    exe_target = _TARGET_DIR / "codex-computer-use.exe"
    if _STAGED_EXE.is_file():
        shutil.copy2(_STAGED_EXE, exe_target)

    print(f"[MCP] 已释放内置 computer-use MCP server 到 {_TARGET_DIR}")
    return _TARGET_DIR
