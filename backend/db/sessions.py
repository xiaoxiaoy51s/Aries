"""会话元数据表（标题、工作目录、创建/更新时间等）。"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .database import get_connection


def _ensure_session_row(session_id: str, title: str = "", work_dir: str = "") -> None:
    """若 sessions 表中不存在该 session_id 则插入一条。"""
    from .work_dirs import upsert_work_dir

    conn = get_connection()
    conn.execute(
        """
        INSERT OR IGNORE INTO sessions (session_id, title, work_dir, created_at, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (session_id, title, work_dir),
    )
    conn.commit()
    if work_dir and work_dir.strip():
        upsert_work_dir(work_dir)


def upsert_session(session_id: str, title: Optional[str] = None, work_dir: Optional[str] = None) -> None:
    from .work_dirs import upsert_work_dir

    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if existing is None:
        conn.execute(
            """
            INSERT INTO sessions (session_id, title, work_dir, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (session_id, title or "", work_dir or ""),
        )
    else:
        updates = ["updated_at = CURRENT_TIMESTAMP"]
        values: list = []
        if title is not None:
            updates.append("title = ?")
            values.append(title)
        if work_dir is not None:
            updates.append("work_dir = ?")
            values.append(work_dir)
        values.append(session_id)
        conn.execute(
            f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?",
            values,
        )
    conn.commit()
    # 同步 work_dirs 表（刷新 updated_at，方便后续按工作目录列出/归档）
    if work_dir and work_dir.strip():
        upsert_work_dir(work_dir)


def get_session(session_id: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT session_id, title, work_dir, created_at, updated_at
        FROM sessions WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "session_id": row[0],
        "title": row[1] or "",
        "work_dir": row[2] or "",
        "created_at": row[3] or "",
        "updated_at": row[4] or "",
    }
def list_sessions(limit: int = 100) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT s.session_id, s.title, s.work_dir, s.created_at, s.updated_at
        FROM sessions s
        ORDER BY datetime(COALESCE(s.updated_at, s.created_at)) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "session_id": r[0],
            "title": r[1] or "",
            "work_dir": r[2] or "",
            "created_at": r[3] or "",
            "updated_at": r[4] or "",
        }
        for r in rows
    ]
def delete_session_meta(session_id: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
