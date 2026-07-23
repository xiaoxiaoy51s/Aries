"""全局应用偏好：读写 ~/.Aries/config/setting.json。

仅存储跨会话的全局偏好（目前仅 approval_mode）。
不入 SQLite，使用 JSON 文件，原子写入，损坏自动备份回退。
带修复日志（Reasonix repair-log.jsonl 风格）和配置快照。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from threading import RLock
from typing import Any

_log = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".Aries" / "config"
CONFIG_PATH = CONFIG_DIR / "setting.json"

# 修复日志（Reasonix 风格：记录每次配置变更和损坏恢复）
REPAIR_LOG_PATH = CONFIG_DIR / "repair-log.jsonl"

# 快照保留数
SNAPSHOT_DIR = CONFIG_DIR / "snapshots"
SNAPSHOT_KEEP = 5

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
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _write_repair_log(event: str, detail: str = "") -> None:
    """写入修复日志（REPAIR_LOG_PATH）。"""
    try:
        _ensure_dir()
        record = {
            "event": event,
            "detail": detail,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with open(REPAIR_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        _log.warning("写入修复日志失败: %s", exc)


def _take_config_snapshot() -> None:
    """每次成功更改配置时保留一份快照。"""
    if not CONFIG_PATH.exists():
        return
    try:
        _ensure_dir()
        ts = time.strftime("%Y%m%d_%H%M%S")
        snapshot = SNAPSHOT_DIR / f"setting.{ts}.json"
        shutil.copy2(CONFIG_PATH, snapshot)

        # 清理旧快照，只保留 SNAPSHOT_KEEP 份
        snapshots = sorted(SNAPSHOT_DIR.glob("setting.*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        for old in snapshots[SNAPSHOT_KEEP:]:
            try:
                old.unlink()
            except OSError:
                pass
    except Exception as exc:
        _log.warning("配置快照失败: %s", exc)


def _atomic_write(data: dict[str, Any]) -> None:
    _ensure_dir()
    fd, tmp = tempfile.mkstemp(prefix="setting.", suffix=".tmp", dir=str(CONFIG_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, CONFIG_PATH)
        # 写入成功后拍快照
        _take_config_snapshot()
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _read_file() -> dict[str, Any]:
    """从磁盘读取并用 DEFAULTS 兜底；解析失败时备份脏文件并记录修复日志。"""
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
    except Exception as exc:
        # 损坏文件备份，避免再次解析失败导致功能不可用
        detail = ""
        try:
            ts = time.strftime("%Y%m%d_%H%M%S")
            backup = CONFIG_PATH.with_suffix(f".bad.{ts}.json")
            shutil.copy2(CONFIG_PATH, backup)
            detail = str(backup)
        except OSError:
            pass
        _write_repair_log("config_corrupted", f"{exc} → backup: {detail}")
        _log.warning("配置文件损坏，已备份到 %s，使用默认值: %s", detail, exc)
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
        _write_repair_log("config_updated", f"keys={list(patch.keys())}")
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


# ---- 批准策略：deny > ask/review > auto/full 优先级（符合 Reasonix 设计） ----

# 高风险标签：即使在 review 模式下也必须用户确认。
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

    优先级（Reasonix 风格）：deny(硬拒绝) > ask/request(弹确认) > auto/review(有条件跳过) > full(全放行)

    返回 True 表示无需弹确认，直接放行。
    黑白名单的硬规则不经过此函数（在调用前已处理）。
    """
    mode = get_approval_mode()
    if mode == "full":
        return True
    if mode == "review":
        return not _is_high_risk(danger_types)
    return False  # 'request' 与未知值一律保持原行为
