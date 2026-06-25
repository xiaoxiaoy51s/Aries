"""Todo 任务清单管理：持久化存储与格式化。"""
from utils.todo_store import (
    get_todos,
    update_todos as _store_update_todos,
    clear_todos as _store_clear_todos,
)

_TODO_PREFIX = "# 当前任务清单"


def update_todos(session_id: str, todos: list[dict], merge: bool = False) -> list[dict]:
    """更新 session 的任务清单并持久化。"""
    return _store_update_todos(session_id, todos, merge=merge)


def clear_todos(session_id: str) -> bool:
    """清空指定 session 的任务清单。"""
    return _store_clear_todos(session_id)


def format_todos_for_context(todos: list[dict]) -> str:
    """将任务清单格式化为 system 消息文本。"""
    if not todos:
        return ""
    # 按状态排序：in_progress > pending > completed
    order = {"in_progress": 0, "pending": 1, "completed": 2}
    sorted_todos = sorted(todos, key=lambda t: (order.get(t.get("status", "pending"), 1), t.get("id", "")))
    lines = ["# 当前任务清单", ""]
    for t in sorted_todos:
        status = t.get("status", "pending")
        icon = {"in_progress": "🔄", "pending": "⬜", "completed": "✅"}.get(status, "⬜")
        priority = t.get("priority", "medium")
        lines.append(f"{icon} [{priority}] {t.get('id', '?')}: {t.get('content', '')}")
    lines.append("")
    return "\n".join(lines)


def purge_todo_messages(messages: list[dict]) -> None:
    """移除已有的任务清单 system 消息，避免累积。"""
    messages[:] = [
        m for m in messages
        if not (m.get("role") == "system" and isinstance(m.get("content"), str) and m["content"].startswith(_TODO_PREFIX))
    ]
