"""开发 / PyInstaller 打包后统一的资源路径解析。"""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_executable_dir() -> Path:
    """当前后端可执行文件所在目录（打包后为 resources/）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_backend_root() -> Path:
    """Python 代码与内嵌资源根目录（打包后为 _MEIPASS）。"""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return get_executable_dir()
    return Path(__file__).resolve().parent.parent


def get_bin_dir() -> Path:
    """ripgrep 等内置二进制目录。优先 exe 同级的 resources/bin。"""
    external = get_executable_dir() / "bin"
    if external.is_dir():
        return external
    return get_backend_root() / "bin"


def get_cli_dir() -> Path:
    """Node.js CLI 服务目录。打包后位于 exe 同级的 resources/cli。"""
    candidates = [
        get_executable_dir() / "cli",
        get_backend_root() / "cli",
        Path(__file__).resolve().parent.parent / "cli",
        Path.cwd() / "cli",
    ]
    seen: set[Path] = set()
    for raw in candidates:
        path = raw.resolve()
        if path in seen or not path.is_dir():
            continue
        seen.add(path)
        if (path / "dist" / "index.js").is_file() or (path / "src" / "index.ts").is_file():
            return path
    raise FileNotFoundError(
        "找不到 backend/cli 目录（需 npm run build，打包时复制到 resources/cli）"
    )
