"""工作目录表 —— 独立于 sessions，方便归档/删除/列出历史。

每个 work_dir 作为独立实体，有自己的 created_at/updated_at 时间戳，
可被归档（archived=1）或删除，不依赖 sessions 表。
"""

from pathlib import Path
from typing import Optional

from .database import get_connection

DEFAULT_WORK_DIR = str((Path.home() / ".Aries" / "work_dir").resolve())


def upsert_work_dir(work_dir: str, name: Optional[str] = None) -> None:
    """插入或更新一条 work_dir 记录，同时刷新 updated_at。"""
    if not work_dir or not work_dir.strip():
        return
    work_dir = work_dir.strip()
    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM work_dirs WHERE work_dir = ?", (work_dir,)
    ).fetchone()
    if existing is None:
        # 从路径提取 name
        display_name = name or _derive_name(work_dir)
        conn.execute(
            """
            INSERT INTO work_dirs (work_dir, name, archived, created_at, updated_at)
            VALUES (?, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (work_dir, display_name),
        )
    else:
        updates = ["updated_at = CURRENT_TIMESTAMP"]
        values: list = []
        if name is not None:
            updates.append("name = ?")
            values.append(name)
        values.append(work_dir)
        conn.execute(
            f"UPDATE work_dirs SET {', '.join(updates)} WHERE work_dir = ?",
            values,
        )
    conn.commit()
def list_work_dirs(include_archived: bool = False, limit: int = 100) -> list[dict]:
    """列出所有工作目录，按 updated_at 倒序。"""
    conn = get_connection()
    where = "" if include_archived else "WHERE archived = 0"
    rows = conn.execute(
        f"""
        SELECT work_dir, name, archived, created_at, updated_at
        FROM work_dirs
        {where}
        ORDER BY datetime(updated_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "work_dir": r[0],
            "name": r[1] or "",
            "archived": bool(r[2]),
            "created_at": r[3] or "",
            "updated_at": r[4] or "",
        }
        for r in rows
    ]
def get_work_dir(work_dir: str) -> Optional[dict]:
    """获取单个 work_dir 记录。"""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT work_dir, name, archived, created_at, updated_at
        FROM work_dirs WHERE work_dir = ?
        """,
        (work_dir,),
    ).fetchone()
    if row is None:
        return None
    return {
        "work_dir": row[0],
        "name": row[1] or "",
        "archived": bool(row[2]),
        "created_at": row[3] or "",
        "updated_at": row[4] or "",
    }
def get_latest_work_dir() -> str:
    """获取最近更新的工作目录，用于新会话默认值。"""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT work_dir FROM work_dirs
        WHERE archived = 0
        ORDER BY datetime(updated_at) DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return DEFAULT_WORK_DIR
    return row[0]
def delete_work_dir(work_dir: str) -> None:
    """删除一条 work_dir 记录（不影响 sessions 表）。"""
    conn = get_connection()
    conn.execute("DELETE FROM work_dirs WHERE work_dir = ?", (work_dir,))
    conn.commit()
def archive_work_dir(work_dir: str, archived: bool = True) -> None:
    """归档/取消归档一条 work_dir。"""
    conn = get_connection()
    conn.execute(
        "UPDATE work_dirs SET archived = ?, updated_at = CURRENT_TIMESTAMP WHERE work_dir = ?",
        (1 if archived else 0, work_dir),
    )
    conn.commit()
def rename_work_dir(work_dir: str, name: str) -> None:
    """重命名工作目录的显示名称。"""
    conn = get_connection()
    conn.execute(
        "UPDATE work_dirs SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE work_dir = ?",
        (name, work_dir),
    )
    conn.commit()
def _derive_name(work_dir: str) -> str:
    """从路径提取最后一段作为显示名。"""
    normalized = work_dir.replace("\\", "/").rstrip("/")
    parts = normalized.split("/")
    return parts[-1] if parts and parts[-1] else normalized
