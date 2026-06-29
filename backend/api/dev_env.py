"""开发环境运行时管理 API。

提供检测系统已安装的 Node.js / Python / Git，
以及下载内置运行时到 ~/.Aries/runtimes/ 的能力。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from utils.env_config import (
    get_env_runtime,
    save_env_config,
)
from utils.runtime_manager import (
    RUNTIME_DOWNLOAD_INFO,
    detect_system_git,
    detect_system_node,
    detect_system_python,
    download_runtime,
    get_default_install_dir,
    resolve_runtime,
)

router = APIRouter(prefix="/api/dev-env", tags=["dev-env"])


def _build_runtime_info(runtime: str) -> dict[str, Any]:
    """构建单个运行时的完整检测信息"""
    import sys

    info = RUNTIME_DOWNLOAD_INFO[runtime]
    default_version = info["version"]
    resolved = resolve_runtime(runtime)

    if runtime == "node":
        system = detect_system_node()
    elif runtime == "python":
        system = detect_system_python()
        # 打包后端自身即 Python，PATH 里可能没有 python 命令
        if not system.get("installed") and sys.executable:
            ver = sys.version.split("\n")[0].replace("Python ", "").strip()
            system = {"installed": True, "version": ver, "path": sys.executable}
    else:
        system = detect_system_git()

    return {
        "system": system,
        "builtin": _builtin_info(runtime),
        "builtins": _list_builtin_versions(runtime),
        "resolved": resolved,
        "saved": get_env_runtime(runtime),
        "download": {
            "version": default_version,
            "versions": info["versions"],
            "default_install_dir": get_default_install_dir(runtime, default_version),
            "available": True,
        },
    }


@router.get("/detect")
async def detect_env() -> dict[str, Any]:
    """检测系统和 ~/.Aries/runtimes 内置运行时状态"""
    from utils.runtime_manager import get_runtimes_root

    return {
        "runtimes_root": str(get_runtimes_root()),
        "node": _build_runtime_info("node"),
        "python": _build_runtime_info("python"),
        "git": _build_runtime_info("git"),
    }


class DownloadRequest(BaseModel):
    runtime: str  # "node" | "python" | "git"
    version: str | None = None
    install_dir: str | None = None


@router.post("/download")
async def download_env(req: DownloadRequest) -> dict[str, Any]:
    """下载并解压指定运行时"""
    result = download_runtime(req.runtime, req.version, req.install_dir)
    if result["success"]:
        # 下载成功后自动设为当前使用的环境
        save_env_config(req.runtime, {
            "path": result["path"],
            "version": result["version"],
            "source": "builtin",
        })
    return result


class SwitchRequest(BaseModel):
    runtime: str  # "node" | "python" | "git"
    source: str  # "system" | "builtin" | "env"
    version: str | None = None
    path: str | None = None


@router.post("/switch")
async def switch_env(req: SwitchRequest) -> dict[str, Any]:
    """切换当前使用的运行时版本"""
    runtime = req.runtime
    source = req.source

    if source == "system":
        system_info = detect_system_node() if runtime == "node" else detect_system_python() if runtime == "python" else detect_system_git()
        if not system_info["installed"]:
            return {"success": False, "error": "系统未安装该运行时"}
        save_env_config(runtime, {
            "path": system_info["path"],
            "version": system_info.get("version", ""),
            "source": "system",
        })
        return {"success": True, "resolved": resolve_runtime(runtime)}

    if source == "builtin":
        version = req.version
        if not version:
            return {"success": False, "error": "切换内置版本需要提供 version"}
        # 检查内置版本是否存在
        from utils.runtime_manager import get_runtimes_root
        if runtime == "node":
            exe = get_runtimes_root() / runtime / "versions" / version / "node.exe"
        elif runtime == "python":
            exe = get_runtimes_root() / runtime / "versions" / version / "python.exe"
        elif runtime == "git":
            exe = get_runtimes_root() / runtime / "versions" / version / "cmd" / "git.exe"
        else:
            return {"success": False, "error": f"不支持的运行时: {runtime}"}
        if not exe.exists():
            return {"success": False, "error": f"内置版本 {version} 未下载"}
        save_env_config(runtime, {
            "path": str(exe),
            "version": version,
            "source": "builtin",
        })
        return {"success": True, "resolved": resolve_runtime(runtime)}

    if source == "env":
        path = req.path
        if not path or not Path(path).exists():
            return {"success": False, "error": "路径不存在"}
        save_env_config(runtime, {
            "path": path,
            "version": req.version or "",
            "source": "env",
        })
        return {"success": True, "resolved": resolve_runtime(runtime)}

    return {"success": False, "error": f"不支持的 source: {source}"}


def _builtin_info(runtime: str) -> dict[str, Any]:
    """~/.Aries/runtimes 下是否已有内置版本（取最新）"""
    from utils.runtime_manager import _list_builtin_versions as _rt_list

    builtins = _rt_list(runtime)
    if builtins:
        latest = builtins[-1]
        return {"installed": True, "version": latest["version"], "path": latest["path"]}

    if runtime == "node":
        from utils.bundled_node import (
            DEFAULT_BUNDLED_NODE_VERSION,
            get_default_node_exe,
            get_staged_node_root,
        )

        default_exe = get_default_node_exe()
        if default_exe.is_file():
            return {
                "installed": True,
                "version": DEFAULT_BUNDLED_NODE_VERSION,
                "path": str(default_exe),
            }
        staged = get_staged_node_root()
        if staged:
            exe = staged / "node.exe"
            if exe.is_file():
                return {
                    "installed": True,
                    "version": DEFAULT_BUNDLED_NODE_VERSION,
                    "path": str(exe),
                }

    return {"installed": False, "version": "", "path": ""}


def _list_builtin_versions(runtime: str) -> list[dict[str, Any]]:
    """列出所有已下载的内置版本"""
    from utils.runtime_manager import _list_builtin_versions as _rt_list
    return _rt_list(runtime)
