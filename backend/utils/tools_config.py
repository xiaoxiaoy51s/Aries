"""CLI 工具配置持久化：读写 ~/.Aries/config/tools.json。

存储用户手动连接的 CLI 路径信息，与 env_config.py 模式一致。
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
TOOLS_CONFIG_PATH = CONFIG_DIR / "tools.json"

_lock = RLock()
_cache: dict[str, Any] | None = None
_cache_mtime: float = 0.0


def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write(data: dict[str, Any]) -> None:
    _ensure_dir()
    fd, tmp = tempfile.mkstemp(prefix="tools.", suffix=".tmp", dir=str(CONFIG_DIR))
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            import os
            os.fsync(f.fileno())
        import os
        os.replace(tmp, TOOLS_CONFIG_PATH)
    finally:
        if Path(tmp).exists():
            try:
                import os
                os.remove(tmp)
            except OSError:
                pass


def _read_file() -> dict[str, Any]:
    """读取 tools.json，损坏时备份并返回空配置。"""
    if not TOOLS_CONFIG_PATH.exists():
        return {}
    try:
        with open(TOOLS_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("tools.json 顶层必须是 object")
        return raw
    except Exception:
        try:
            ts = time.strftime("%Y%m%d_%H%M%S")
            shutil.copy2(TOOLS_CONFIG_PATH, TOOLS_CONFIG_PATH.with_suffix(f".bad.{ts}.json"))
        except OSError:
            pass
        return {}


def _load_with_cache() -> dict[str, Any]:
    global _cache, _cache_mtime
    with _lock:
        try:
            mtime = TOOLS_CONFIG_PATH.stat().st_mtime if TOOLS_CONFIG_PATH.exists() else 0.0
        except OSError:
            mtime = 0.0
        if _cache is None or mtime != _cache_mtime:
            _cache = _read_file()
            _cache_mtime = mtime
        return dict(_cache)


def load_tools_config() -> dict[str, Any]:
    """读取完整的 tools.json 配置"""
    return _load_with_cache()


def get_tool_config(cli_id: str) -> dict[str, Any] | None:
    """获取指定 CLI 的已保存配置"""
    config = load_tools_config()
    return config.get(cli_id)


def save_tool_config(cli_id: str, info: dict[str, Any]) -> dict[str, Any]:
    """保存指定 CLI 工具的连接状态到 tools.json"""
    global _cache, _cache_mtime
    with _lock:
        current = _read_file()
        current[cli_id] = {
            "path": info.get("path", ""),
            "source": info.get("source", "system"),  # system / manual
            "connected": info.get("connected", True),
        }
        _atomic_write(current)
        try:
            _cache_mtime = TOOLS_CONFIG_PATH.stat().st_mtime
        except OSError:
            _cache_mtime = 0.0
        _cache = dict(current)
        return dict(current)


def remove_tool_config(cli_id: str) -> dict[str, Any]:
    """移除指定 CLI 工具的配置"""
    global _cache, _cache_mtime
    with _lock:
        current = _read_file()
        if cli_id in current:
            del current[cli_id]
        _atomic_write(current)
        try:
            _cache_mtime = TOOLS_CONFIG_PATH.stat().st_mtime
        except OSError:
            _cache_mtime = 0.0
        _cache = dict(current)
        return dict(current)


def get_custom_clis() -> list[dict[str, Any]]:
    """获取用户自定义的 CLI 定义列表"""
    config = load_tools_config()
    return config.get("custom_clis", [])


def add_custom_cli(spec: dict[str, Any]) -> dict[str, Any]:
    """添加一个自定义 CLI 定义"""
    global _cache, _cache_mtime
    with _lock:
        current = _read_file()
        custom_list: list[dict[str, Any]] = current.get("custom_clis", [])
        # 检查 id 是否已存在
        for existing in custom_list:
            if existing["id"] == spec["id"]:
                existing.clear()
                existing.update(spec)
                _atomic_write(current)
                _invalidate_cache()
                return spec
        custom_list.append(spec)
        current["custom_clis"] = custom_list
        _atomic_write(current)
        _invalidate_cache()
        return spec


def remove_custom_cli(custom_id: str) -> bool:
    """移除一个自定义 CLI 定义，同时清理它的连接状态"""
    global _cache, _cache_mtime
    with _lock:
        current = _read_file()
        custom_list: list[dict[str, Any]] = current.get("custom_clis", [])
        before = len(custom_list)
        current["custom_clis"] = [c for c in custom_list if c["id"] != custom_id]
        # 也清理连接状态
        if custom_id in current:
            del current[custom_id]
        _atomic_write(current)
        _invalidate_cache()
        return len(current["custom_clis"]) < before


def _invalidate_cache() -> None:
    global _cache, _cache_mtime
    _cache = None
    _cache_mtime = 0.0
