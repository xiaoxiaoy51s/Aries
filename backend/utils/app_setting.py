"""全局应用偏好：读写 ~/.Aries/config/setting.json。

仅存储跨会话的全局偏好（目前仅 approval_mode）。
不入 SQLite，使用 JSON 文件，原子写入，损坏自动备份回退。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from threading import RLock
from typing import Any

CONFIG_DIR = Path.home() / ".Aries" / "config"
CONFIG_PATH = CONFIG_DIR / "setting.json"

# 三档批准模式
APPROVAL_MODES = ("request", "review", "full")
DEFAULT_APPROVAL_MODE = "request"

DEFAULTS: dict[str, Any] = {
    "approval_mode": DEFAULT_APPROVAL_MODE,
}

_lock = RLock()
_cache: dict[str, Any] | None = None
_cache_mtime: float = 0.0


def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write(data: dict[str, Any]) -> None:
    _ensure_dir()
    fd, tmp = tempfile.mkstemp(prefix="setting.", suffix=".tmp", dir=str(CONFIG_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, CONFIG_PATH)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _read_file() -> dict[str, Any]:
    """从磁盘读取并用 DEFAULTS 兜底；解析失败时备份脏文件。"""
    if not CONFIG_PATH.exists():
        return dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("setting.json 顶层必须是 object")
        merged = dict(DEFAULTS)
        merged.update(raw)
        return merged
    except Exception:
        # 损坏文件备份，避免再次解析失败导致功能不可用
        try:
            ts = time.strftime("%Y%m%d_%H%M%S")
            shutil.copy2(CONFIG_PATH, CONFIG_PATH.with_suffix(f".bad.{ts}.json"))
        except OSError:
            pass
        return dict(DEFAULTS)


def _load_with_cache() -> dict[str, Any]:
    global _cache, _cache_mtime
    with _lock:
        try:
            mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else 0.0
        except OSError:
            mtime = 0.0
        if _cache is None or mtime != _cache_mtime:
            _cache = _read_file()
            _cache_mtime = mtime
        return dict(_cache)


def load_setting() -> dict[str, Any]:
    """获取全部偏好（带 DEFAULTS 兜底）。"""
    return _load_with_cache()


def update_setting(patch: dict[str, Any]) -> dict[str, Any]:
    """合并写入；返回最新偏好。"""
    global _cache, _cache_mtime
    with _lock:
        current = _read_file()
        current.update(patch)
        _atomic_write(current)
        try:
            _cache_mtime = CONFIG_PATH.stat().st_mtime
        except OSError:
            _cache_mtime = 0.0
        _cache = dict(current)
        return dict(current)


# ---- approval_mode 专用便捷 API ---------------------------------------------

def get_approval_mode() -> str:
    mode = load_setting().get("approval_mode", DEFAULT_APPROVAL_MODE)
    return mode if mode in APPROVAL_MODES else DEFAULT_APPROVAL_MODE


def set_approval_mode(mode: str) -> dict[str, Any]:
    if mode not in APPROVAL_MODES:
        return {
            "success": False,
            "error": f"approval_mode 必须是 {APPROVAL_MODES} 之一",
        }
    update_setting({"approval_mode": mode})
    return {"success": True, "approval_mode": mode}


# ---- 批准策略：与 danger_types 配合决定是否还需要弹确认 ---------------------

# 高风险标签：即使在 review 模式下也必须用户确认。
# 与 cli_executor._check_dangerous_command / file_manager 现有 danger_types 对齐。
_HIGH_RISK_TAGS = (
    "删除",
    "格式化",
    "系统目录",
    "系统命令",
    "rm -rf",
    "format",
    "shutdown",
    "reboot",
    "mkfs",
    "dd ",
    "路径在黑名单中",
)


def _is_high_risk(danger_types: list[str] | None) -> bool:
    if not danger_types:
        return False
    joined = "|".join(danger_types)
    return any(tag in joined for tag in _HIGH_RISK_TAGS)


def should_skip_confirmation(danger_types: list[str] | None) -> bool:
    """根据当前 approval_mode 与风险等级，判断能否跳过确认。

    返回 True 表示无需弹确认，直接放行。
    黑白名单的硬规则不经过此函数（在调用前已处理）。
    """
    mode = get_approval_mode()
    if mode == "full":
        return True
    if mode == "review":
        return not _is_high_risk(danger_types)
    return False  # 'request' 与未知值一律保持原行为

