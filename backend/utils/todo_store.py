"""Todo 清单内存存储（Reasonix 风格）。

todo 是纯上下文状态，不再持久化到文件。
AI 通过 todo_write 工具每次发送完整清单替换上一次。
"""
from __future__ import annotations

from threading import RLock
from typing import Any

_cache: dict[str, list[dict]] = {}
_lock = RLock()

_VALID_STATUSES = {"pending", "in_progress", "completed"}
_VALID_PRIORITIES = {"high", "medium", "low"}


def _normalize_todo_item(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    content = str(raw.get("content") or "").strip()
    if not content:
        return None
    todo_id = str(raw.get("id") or content).strip()
    if not todo_id:
        return None
    status = str(raw.get("status") or "pending")
    if status not in _VALID_STATUSES:
        status = "pending"
    priority = str(raw.get("priority") or "medium")
    if priority not in _VALID_PRIORITIES:
        priority = "medium"
    return {
        "id": todo_id,
        "content": content,
        "status": status,
        "priority": priority,
    }


def get_todos(session_id: str) -> list[dict]:
    """获取指定 session 的 todo 清单（仅内存缓存，不读文件）。"""
    sid = str(session_id or "").strip()
    if not sid:
        return []
    with _lock:
        return list(_cache.get(sid, []))


def update_todos(session_id: str, todos: list[dict]) -> list[dict]:
    """用 Reasonix 方式更新 todo：每次发送完整清单，整体替换。

    Reasonix 约定：
    - todo_write 每次发送 COMPLETE 清单，替换上一次
    - 只保留一个 in_progress 项
    """
    sid = str(session_id or "").strip()
    if not sid:
        return []
    incoming = _normalize_todo_list(todos)
    with _lock:
        _cache[sid] = incoming
        return list(incoming)


def clear_todos(session_id: str) -> bool:
    """清空指定 session 的 todo 清单。"""
    sid = str(session_id or "").strip()
    if not sid:
        return False
    with _lock:
        _cache.pop(sid, None)
    return True


def _normalize_todo_list(todos: list[Any]) -> list[dict]:
    normalized: list[dict] = []
    for item in todos or []:
        todo = _normalize_todo_item(item)
        if todo:
            normalized.append(todo)
    return normalized
