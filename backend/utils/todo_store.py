"""Todo 清单持久化存储。

文件路径：~/.Aries/todo/{session_id}.json
按 session 隔离，后端重启后仍可恢复。
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

TODO_DIR = Path.home() / ".Aries" / "todo"

_lock = RLock()
_cache: dict[str, list[dict]] = {}


def _ensure_dir() -> None:
    TODO_DIR.mkdir(parents=True, exist_ok=True)


def _todo_path(session_id: str) -> Path:
    # 文件名做简单安全处理，避免路径注入
    safe_id = str(session_id).replace("/", "_").replace("\\", "_")
    return TODO_DIR / f"{safe_id}.json"


def _atomic_write(session_id: str, data: list[dict]) -> None:
    _ensure_dir()
    path = _todo_path(session_id)
    fd, tmp = tempfile.mkstemp(prefix=f"todo.{session_id}.", suffix=".tmp", dir=str(TODO_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _read_file(session_id: str) -> list[dict]:
    path = _todo_path(session_id)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        # 文件损坏，尝试备份并清空
        try:
            backup = path.with_suffix(".json.bak")
            os.replace(path, backup)
        except OSError:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    except OSError:
        pass
    return []


def get_todos(session_id: str) -> list[dict]:
    """获取指定 session 的 todo 清单（带内存缓存）。"""
    sid = str(session_id or "").strip()
    if not sid:
        return []
    with _lock:
        if sid not in _cache:
            _cache[sid] = _read_file(sid)
        return list(_cache[sid])


def update_todos(session_id: str, todos: list[dict], merge: bool = False) -> list[dict]:
    """更新 session 的 todo 清单并持久化。merge=true 时按 id 合并。"""
    sid = str(session_id or "").strip()
    if not sid:
        return []
    with _lock:
        if merge:
            existing = {t["id"]: t for t in get_todos(sid)}
            for t in todos:
                existing[t["id"]] = t
            new_list = list(existing.values())
        else:
            new_list = todos
        _cache[sid] = new_list
        _atomic_write(sid, new_list)
        return list(new_list)


def clear_todos(session_id: str) -> bool:
    """清空指定 session 的 todo 清单。"""
    sid = str(session_id or "").strip()
    if not sid:
        return False
    with _lock:
        _cache.pop(sid, None)
        path = _todo_path(sid)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return False
    return True


def list_session_ids() -> list[str]:
    """列出所有有 todo 文件的 session_id。"""
    _ensure_dir()
    ids: list[str] = []
    for p in TODO_DIR.glob("*.json"):
        if p.suffix == ".json" and p.stem:
            ids.append(p.stem)
    return ids
