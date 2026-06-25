"""数据库连接管理。

策略：线程级连接复用（thread-local）+ 健康检查。
- 每个线程维护一个独立连接，首次使用时创建。
- 每次返回前检查连接是否可用，失效则自动重建。
- 开启 WAL 模式，提升并发读写性能。
"""
import sqlite3
import threading
from pathlib import Path

DATABASE_PATH = (Path.home() / ".Aries" / "sqlite" / "agent.db").resolve()

_local = threading.local()


def _create_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def get_connection() -> sqlite3.Connection:
    """返回当前线程的 SQLite 连接（复用，不手动关闭）。

    线程级连接池：每线程一个连接，自动检测失效并重建。
    """
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.Error:
            try:
                conn.close()
            except Exception:
                pass
    conn = _create_connection()
    _local.conn = conn
    return conn


def _column_exists(cursor, table: str, column: str) -> bool:
    """检查表中是否存在某列（仅用于 init_database 迁移）。"""
    cols = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}
    return column in cols


def init_database():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            reasoning_content TEXT,
            image_path TEXT,
            message_snapshot_json TEXT,
            mode TEXT NOT NULL DEFAULT 'agent',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 老库迁移：如果 chat_messages 已存在但缺 mode 列，补上
    if not _column_exists(cursor, "chat_messages", "mode"):
        cursor.execute(
            "ALTER TABLE chat_messages ADD COLUMN mode TEXT NOT NULL DEFAULT 'agent'"
        )

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            source_message_count INTEGER NOT NULL DEFAULT 0,
            source_token_estimate INTEGER NOT NULL DEFAULT 0,
            summary_token_estimate INTEGER NOT NULL DEFAULT 0,
            source_until_message_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_memories_session_id ON session_memories(session_id)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            folder_name TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            task_content TEXT,
            scheduled_at DATETIME NOT NULL,
            session_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            executed_at DATETIME
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_polling ON scheduled_tasks(status, scheduled_at)
    """)

    # 老库补字段：任务类型（once / recurring）与循环间隔秒数
    for col, col_type, default in [
        ("task_type", "TEXT", "'once'"),
        ("interval_seconds", "INTEGER", None),
        ("interval_minutes", "INTEGER", None),
        ("schedule_type", "TEXT", "'once'"),
        ("schedule_config", "TEXT", None),
        ("notify_type", "TEXT", "'none'"),
        ("notify_config", "TEXT", None),
        ("auto_delete", "INTEGER", "0"),
    ]:
        if not _column_exists(cursor, "scheduled_tasks", col):
            default_clause = f" DEFAULT {default}" if default is not None else ""
            cursor.execute(
                f"ALTER TABLE scheduled_tasks ADD COLUMN {col} {col_type}{default_clause}"
            )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL DEFAULT '',
            work_dir TEXT NOT NULL DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS path_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL CHECK(type IN ('whitelist', 'blacklist')),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 工作目录表 —— 独立于 sessions，方便归档/删除/列出历史
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS work_dirs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_dir TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL DEFAULT '',
            archived INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_work_dirs_updated_at ON work_dirs(updated_at)
    """)

    # 新用户默认插入 ~/.Aries/work_dir
    default_wd = str((Path.home() / ".Aries" / "work_dir").resolve())
    cursor.execute(
        """
        INSERT OR IGNORE INTO work_dirs (work_dir, name, archived, created_at, updated_at)
        VALUES (?, 'work_dir', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (default_wd,),
    )

    conn.commit()


init_database()

# 初始化默认白名单（在 init_database 之后调用，避免循环导入）
from db.path_permissions import init_default_whitelist
init_default_whitelist()
