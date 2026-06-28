"""会话级审批缓存：已批准的命令在当前会话内不再重复确认。

按 session_id + 命令指纹缓存；带 TTL 与单会话条目上限。
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Any

# {session_id: {command_fingerprint: expires_at_monotonic}}
_approval_cache: dict[str, dict[str, float]] = {}

APPROVAL_TTL_SECONDS = 3600
MAX_APPROVALS_PER_SESSION = 64

# 统计
_stats = {"hits": 0, "misses": 0, "stores": 0, "expired": 0}


def _normalize_command(command: str) -> str:
    text = " ".join(command.strip().lower().split())
    # 路径末尾斜杠归一：ls /tmp/ → ls /tmp
    text = re.sub(r"(\S)/+(?=\s|$)", r"\1", text)
    return text


def _make_fingerprint(command: str) -> str:
    normalized = _normalize_command(command)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _prune_session(session_id: str, now: float | None = None) -> None:
    entries = _approval_cache.get(session_id)
    if not entries:
        return
    ts = now if now is not None else time.monotonic()
    expired_keys = [fp for fp, exp in entries.items() if exp <= ts]
    for fp in expired_keys:
        entries.pop(fp, None)
        _stats["expired"] += 1
    if not entries:
        _approval_cache.pop(session_id, None)


def cache_approval(session_id: str, command: str) -> None:
    """记录一条命令已获批准，后续同会话内不再确认（TTL 内）。"""
    fp = _make_fingerprint(command)
    now = time.monotonic()
    _prune_session(session_id, now)
    entries = _approval_cache.setdefault(session_id, {})
    if len(entries) >= MAX_APPROVALS_PER_SESSION:
        oldest_fp = min(entries, key=entries.get)
        entries.pop(oldest_fp, None)
    entries[fp] = now + APPROVAL_TTL_SECONDS
    _stats["stores"] += 1


def is_approved(session_id: str, command: str) -> bool:
    """检查命令是否已在当前会话中获批准且未过期。"""
    fp = _make_fingerprint(command)
    entries = _approval_cache.get(session_id)
    if not entries:
        _stats["misses"] += 1
        return False
    exp = entries.get(fp)
    now = time.monotonic()
    if exp is None or exp <= now:
        if exp is not None:
            entries.pop(fp, None)
            _stats["expired"] += 1
        _stats["misses"] += 1
        return False
    _stats["hits"] += 1
    return True


def clear_session(session_id: str) -> None:
    """清空指定会话的审批缓存。"""
    _approval_cache.pop(session_id, None)


def clear_all() -> None:
    """清空所有缓存（测试用）。"""
    _approval_cache.clear()


def approval_stats() -> dict[str, Any]:
    now = time.monotonic()
    alive = sum(
        1
        for entries in _approval_cache.values()
        for exp in entries.values()
        if exp > now
    )
    total = _stats["hits"] + _stats["misses"]
    hit_rate = round(_stats["hits"] / total * 100, 1) if total else 0.0
    return {
        "sessions": len(_approval_cache),
        "entries_alive": alive,
        "ttl_seconds": APPROVAL_TTL_SECONDS,
        "max_per_session": MAX_APPROVALS_PER_SESSION,
        "hits": _stats["hits"],
        "misses": _stats["misses"],
        "stores": _stats["stores"],
        "expired": _stats["expired"],
        "hit_rate_percent": hit_rate,
    }


__all__ = [
    "cache_approval",
    "is_approved",
    "clear_session",
    "clear_all",
    "approval_stats",
    "APPROVAL_TTL_SECONDS",
]
