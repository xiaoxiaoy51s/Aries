"""开发运行时管理器：检测、下载、解压 Node.js / Python / Git 运行时。

运行时存储结构（与 Trae/Codex 风格一致）：
    ~/.Aries/runtimes/
    ├── node/versions/<version>/node.exe, npm.cmd, npx.cmd ...
    ├── python/versions/<version>/python.exe, ...
    └── git/versions/<version>/cmd/git.exe, ...

优先级：
    1. 系统已安装（PATH 中能找到）→ 直接用系统的
    2. 内置运行时（~/.Aries/runtimes/ 下已下载）→ 用内置的
    3. 都没有 → 返回空，前端提示下载
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import httpx


# ---- 运行时根目录 ----

def get_runtimes_root() -> Path:
    """~/.Aries/runtimes/"""
    root = Path.home() / ".Aries" / "runtimes"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_default_install_dir(runtime: str, version: str) -> str:
    """获取默认安装目录"""
    return str(get_runtimes_root() / runtime / "versions" / version)


# ---- 检测系统已安装的运行时 ----

def _detect_command(command: str, version_args: list[str] | None = None) -> dict[str, Any]:
    """直接执行命令检测版本，类似 `node -v` / `python --version` / `git --version`"""
    try:
        result = subprocess.run(
            [command] + (version_args or ["--version"]),
            capture_output=True, text=True, timeout=5,
        )
        version = (result.stdout or result.stderr).strip()
        if not version or result.returncode != 0:
            return {"installed": False}
        path = shutil.which(command) or command
        return {"installed": True, "version": version, "path": path}
    except Exception:
        return {"installed": False}


def detect_system_node() -> dict[str, Any]:
    """检测系统 Node.js（node --version）"""
    return _detect_command("node", ["-v"])


def detect_system_python() -> dict[str, Any]:
    """检测系统 Python（python --version）"""
    return _detect_command("python", ["--version"]) or _detect_command("python3", ["--version"])


def detect_system_git() -> dict[str, Any]:
    """检测系统 Git（git --version）"""
    return _detect_command("git")


# ---- 检测内置运行时 ----

def _list_builtin_versions(runtime: str) -> list[dict[str, Any]]:
    """列出 ~/.Aries/runtimes/<runtime>/versions/ 下已下载的版本"""
    versions_dir = get_runtimes_root() / runtime / "versions"
    if not versions_dir.exists():
        return []
    result = []
    for d in sorted(versions_dir.iterdir()):
        if not d.is_dir():
            continue
        version = d.name
        if runtime == "node":
            exe = d / "node.exe"
        elif runtime == "python":
            exe = d / "python.exe"
        elif runtime == "git":
            exe = d / "cmd" / "git.exe"
        else:
            continue
        if exe.exists():
            result.append({"version": version, "path": str(exe)})
    return result


# ---- 下载与解压 ----

# 各运行时的推荐版本和下载 URL 模板（Windows x64）
RUNTIME_DOWNLOAD_INFO = {
    "node": {
        "version": "v20.17.0",
        "versions": [
            {"version": "v24.18.0", "label": "Node.js 24.18.0"},
            {"version": "v22.23.1", "label": "Node.js 22.23.1"},
            {"version": "v20.20.2", "label": "Node.js 20.20.2"},
            {"version": "v20.17.0", "label": "Node.js 20.17.0 (LTS)"},
            {"version": "v18.20.8", "label": "Node.js 18.20.8"},
            {"version": "v16.20.2", "label": "Node.js 16.20.2"},
            {"version": "v14.21.3", "label": "Node.js 14.21.3"},
            {"version": "v12.22.12", "label": "Node.js 12.22.12"},
            {"version": "v10.24.1", "label": "Node.js 10.24.1"},
            {"version": "v8.17.0", "label": "Node.js 8.17.0"},
            {"version": "v6.17.1", "label": "Node.js 6.17.1"},
            {"version": "v4.9.1", "label": "Node.js 4.9.1"},
        ],
        "url_template": "https://nodejs.org/dist/{version}/node-{version}-win-x64.zip",
        # zip 解压后是 node-v20.17.0-win-x64/ 目录，内部就是标准 node 结构
        "strip_root": True,
    },
    "python": {
        "version": "3.12.7",
        "versions": [
            {"version": "3.13.2", "label": "Python 3.13.2"},
            {"version": "3.12.9", "label": "Python 3.12.9"},
            {"version": "3.12.7", "label": "Python 3.12.7"},
            {"version": "3.11.11", "label": "Python 3.11.11"},
            {"version": "3.10.16", "label": "Python 3.10.16"},
            {"version": "3.9.21", "label": "Python 3.9.21"},
        ],
        "url_template": "https://www.python.org/ftp/python/{version}/python-{version}-embed-win-amd64.zip",
        # embed 包解压后直接是 python.exe 等文件，无外层目录
        "strip_root": False,
    },
    "git": {
        "version": "2.47.1",
        "versions": [
            {"version": "2.47.1", "label": "Git 2.47.1"},
            {"version": "2.46.2", "label": "Git 2.46.2"},
            {"version": "2.45.2", "label": "Git 2.45.2"},
        ],
        "url_template": "https://github.com/git-for-windows/git/releases/download/v{version}.windows.1/PortableGit-{version}-64-bit.7z.exe",
        # PortableGit 是 7z 自解压，需要特殊处理，暂用 zip 版本
        "strip_root": False,
    },
}


def download_runtime(runtime: str, version: str | None = None, install_dir: str | None = None) -> dict[str, Any]:
    """下载并解压运行时。

    默认安装到 ~/.Aries/runtimes/<runtime>/versions/<version>/
    如果传入 install_dir，则安装到指定目录。

    Returns:
        {"success": bool, "version": str, "path": str, "error": str}
    """
    info = RUNTIME_DOWNLOAD_INFO.get(runtime)
    if not info:
        return {"success": False, "error": f"不支持的运行时: {runtime}"}

    target_version = version or info["version"]
    version_str = target_version if target_version.startswith("v") else f"v{target_version}"
    if runtime == "python":
        version_str = target_version  # python 不加 v 前缀
    if runtime == "git":
        version_str = target_version

    # 目标目录
    if install_dir:
        target_dir = Path(install_dir)
    else:
        target_dir = get_runtimes_root() / runtime / "versions" / target_version
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    # 构建下载 URL
    url = info["url_template"].format(version=version_str)

    try:
        # 下载到临时文件
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = tmp.name

        with httpx.stream("GET", url, follow_redirects=True, timeout=300) as resp:
            resp.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)

        # 解压
        if runtime == "git":
            # PortableGit-*.7z.exe 是自解压格式，用 7z 解压
            result = subprocess.run(
                [str(tmp_path), f"-o{target_dir}", "-y"],
                capture_output=True, timeout=120,
            )
            if result.returncode != 0:
                return {"success": False, "error": f"PortableGit 自解压失败: {result.stderr.decode('utf-8', errors='replace')}"}
        else:
            with zipfile.ZipFile(tmp_path, "r") as zf:
                if info["strip_root"]:
                    # Node.js zip 有外层目录 node-vXX-win-x64/，需要去掉
                    names = zf.namelist()
                    if names:
                        root_folder = names[0].split("/")[0]
                        for name in names:
                            if name.endswith("/"):
                                continue
                            # 去掉外层目录
                            rel = name[len(root_folder) + 1:]
                            if not rel:
                                continue
                            target_file = target_dir / rel
                            target_file.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(name) as src, open(target_file, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                else:
                    # Python embed 包直接解压
                    zf.extractall(target_dir)

        # 验证解压结果
        if runtime == "node":
            exe = target_dir / "node.exe"
        elif runtime == "python":
            exe = target_dir / "python.exe"
        elif runtime == "git":
            exe = target_dir / "cmd" / "git.exe"
        else:
            exe = target_dir

        if not exe.exists():
            return {"success": False, "error": f"解压后未找到 {exe.name}"}

        return {
            "success": True,
            "version": target_version,
            "path": str(exe),
        }

    except Exception as exc:
        return {"success": False, "error": str(exc)}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ---- 获取最终使用的运行时路径 ----

def resolve_runtime(runtime: str) -> dict[str, Any]:
    """获取指定运行时的最终使用路径。

    优先级：
        1. env.json 中用户手动指定的版本
        2. 系统已安装
        3. 内置运行时（取最新版本）
        4. 都没有

    Returns:
        {"source": "env" | "system" | "builtin" | "none", "version": str, "path": str}
    """
    from utils.env_config import get_env_runtime

    # 1. 用户手动指定（env.json）
    saved = get_env_runtime(runtime)
    if saved and saved.get("path") and Path(saved["path"]).exists():
        return {
            "source": "env",
            "version": saved.get("version", ""),
            "path": saved["path"],
        }

    # 2. 系统已安装
    if runtime == "node":
        system = detect_system_node()
        if system["installed"]:
            return {"source": "system", "version": system.get("version", ""), "path": system["path"]}
    elif runtime == "python":
        # Python 优先用当前后端进程的解释器
        return {"source": "system", "version": sys.version, "path": sys.executable}
    elif runtime == "git":
        system = detect_system_git()
        if system["installed"]:
            return {"source": "system", "version": system.get("version", ""), "path": system["path"]}

    # 3. 内置运行时
    builtins = _list_builtin_versions(runtime)
    if builtins:
        latest = builtins[-1]  # 排序后最后一个是最新的
        return {"source": "builtin", "version": latest["version"], "path": latest["path"]}

    return {"source": "none", "version": "", "path": ""}


def get_runtime_exe(runtime: str) -> str:
    """获取运行时可执行文件路径，找不到返回空字符串。

    用于 MCP 启动时替换 node/npx/python 命令。
    """
    info = resolve_runtime(runtime)
    return info.get("path", "")
