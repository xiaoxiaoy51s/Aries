"""开发环境配置：读写 ~/.Aries/config/env.json。

用于持久化用户选择的 Node.js / Python / Git 运行时。
调用运行时时优先使用 env.json 中配置的路径。
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from threading import RLock
from typing import Any

CONFIG_DIR = Path.home() / ".Aries" / "config"
ENV_CONFIG_PATH = CONFIG_DIR / "env.json"

_lock = RLock()
_cache: dict[str, Any] | None = None
_cache_mtime: float = 0.0


def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write(data: dict[str, Any]) -> None:
    _ensure_dir()
    fd, tmp = tempfile.mkstemp(prefix="env.", suffix=".tmp", dir=str(CONFIG_DIR))
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            import os
            os.fsync(f.fileno())
        import os
        os.replace(tmp, ENV_CONFIG_PATH)
    finally:
        if Path(tmp).exists():
            try:
                import os
                os.remove(tmp)
            except OSError:
                pass


def _read_file() -> dict[str, Any]:
    """读取 env.json，损坏时备份并返回空配置。"""
    if not ENV_CONFIG_PATH.exists():
        return {}
    try:
        with open(ENV_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("env.json 顶层必须是 object")
        return raw
    except Exception:
        try:
            ts = time.strftime("%Y%m%d_%H%M%S")
            shutil.copy2(ENV_CONFIG_PATH, ENV_CONFIG_PATH.with_suffix(f".bad.{ts}.json"))
        except OSError:
            pass
        return {}


def _load_with_cache() -> dict[str, Any]:
    global _cache, _cache_mtime
    with _lock:
        try:
            mtime = ENV_CONFIG_PATH.stat().st_mtime if ENV_CONFIG_PATH.exists() else 0.0
        except OSError:
            mtime = 0.0
        if _cache is None or mtime != _cache_mtime:
            _cache = _read_file()
            _cache_mtime = mtime
        return dict(_cache)


def load_env_config() -> dict[str, Any]:
    """读取完整的 env.json 配置"""
    return _load_with_cache()


def save_env_config(runtime: str, info: dict[str, Any]) -> dict[str, Any]:
    """保存指定运行时配置到 env.json"""
    global _cache, _cache_mtime
    with _lock:
        current = _read_file()
        current[runtime] = {
            "path": info.get("path", ""),
            "version": info.get("version", ""),
            "source": info.get("source", ""),
        }
        _atomic_write(current)
        try:
            _cache_mtime = ENV_CONFIG_PATH.stat().st_mtime
        except OSError:
            _cache_mtime = 0.0
        _cache = dict(current)
        return dict(current)


def apply_env_to_path() -> dict[str, str]:
    """启动时调用：把 env.json 中配置的运行时路径加到 PATH 最前面。

    这样所有子进程（Node.js CLI Server、cli_executor 执行的命令、MCP 子进程）
    都会自动使用配置的 node/python/git 版本。

    Returns:
        {"node": "path/to/node.exe", "python": "...", "git": "..."} 实际应用的路径
    """
    import os
    config = load_env_config()
    applied: dict[str, str] = {}
    current_path = os.environ.get("PATH", "")

    # 收集要前置的目录（exe 所在目录）
    dirs_to_prepend: list[str] = []
    for runtime in ("node", "python", "git"):
        info = config.get(runtime)
        if not info or not info.get("path"):
            continue
        exe_path = Path(info["path"])
        if not exe_path.exists():
            continue
        exe_dir = str(exe_path.parent)
        if exe_dir not in dirs_to_prepend:
            dirs_to_prepend.append(exe_dir)
        applied[runtime] = info["path"]

    if dirs_to_prepend:
        # 把配置的目录放到 PATH 最前面
        os.environ["PATH"] = os.pathsep.join(dirs_to_prepend) + os.pathsep + current_path
        print(f"[EnvConfig] 已加载 env.json，PATH 前置: {dirs_to_prepend}")

    return applied


def get_env_runtime(runtime: str) -> dict[str, Any] | None:
    """获取指定运行时的已保存配置"""
    config = load_env_config()
    return config.get(runtime)


def clear_env_runtime(runtime: str) -> dict[str, Any]:
    """清除指定运行时的保存配置"""
    global _cache, _cache_mtime
    with _lock:
        current = _read_file()
        if runtime in current:
            del current[runtime]
        _atomic_write(current)
        try:
            _cache_mtime = ENV_CONFIG_PATH.stat().st_mtime
        except OSError:
            _cache_mtime = 0.0
        _cache = dict(current)
        return dict(current)
