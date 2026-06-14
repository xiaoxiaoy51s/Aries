"""技能启用状态读写。表结构由 db.database.init_database() 创建。"""

from .database import get_connection


def get_skill_status(folder_name: str) -> bool:
    """读取指定 skill 的启用状态。默认 True。"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT enabled FROM skills WHERE folder_name = ?",
            (folder_name,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return True
    return bool(row["enabled"])


def set_skill_status(folder_name: str, enabled: bool) -> None:
    """设置 skill 启用状态，不存在则插入。"""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO skills (folder_name, enabled, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(folder_name) DO UPDATE SET
                enabled = excluded.enabled,
                updated_at = CURRENT_TIMESTAMP
            """,
            (folder_name, 1 if enabled else 0),
        )
        conn.commit()
    finally:
        conn.close()
