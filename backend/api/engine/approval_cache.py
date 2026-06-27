"""会话级审批缓存：已批准的命令在当前会话内不再重复确认。

借鉴 Codex 的 ApprovalStore 设计，按 session_id + 命令指纹缓存审批结果。
命令指纹 = 命令文本的归一化哈希，忽略工作目录等可变参数。
"""
import hashlib
from typing import Optional

# {session_id: {command_fingerprint: True}}
_approval_cache: dict[str, set[str]] = {}


def _make_fingerprint(command: str) -> str:
    """生成命令指纹：去空白、转小写后取 md5 前 16 位。"""
    normalized = " ".join(command.strip().lower().split())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]


def cache_approval(session_id: str, command: str) -> None:
    """记录一条命令已获批准，后续同会话内不再确认。"""
    fp = _make_fingerprint(command)
    if session_id not in _approval_cache:
        _approval_cache[session_id] = set()
    _approval_cache[session_id].add(fp)


def is_approved(session_id: str, command: str) -> bool:
    """检查命令是否已在当前会话中获批准。"""
    fp = _make_fingerprint(command)
    return fp in _approval_cache.get(session_id, set())


def clear_session(session_id: str) -> None:
    """清空指定会话的审批缓存。"""
    _approval_cache.pop(session_id, None)


def clear_all() -> None:
    """清空所有缓存（测试用）。"""
    _approval_cache.clear()


__all__ = [
    "cache_approval",
    "is_approved",
    "clear_session",
    "clear_all",
]
