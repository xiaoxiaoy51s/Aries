import sqlite3
import json
from pathlib import Path
from typing import Optional, List
from datetime import datetime

DATABASE_PATH = (Path.home() / ".MIMOClaw" / "sqlite" / "agent.db").resolve()


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    return conn


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
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at)
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
    cols = {row[1] for row in cursor.execute("PRAGMA table_info(scheduled_tasks)").fetchall()}
    if "task_type" not in cols:
        cursor.execute(
            "ALTER TABLE scheduled_tasks ADD COLUMN task_type TEXT NOT NULL DEFAULT 'once'"
        )
    if "interval_seconds" not in cols:
        cursor.execute(
            "ALTER TABLE scheduled_tasks ADD COLUMN interval_seconds INTEGER"
        )
    if "interval_minutes" not in cols:
        cursor.execute(
            "ALTER TABLE scheduled_tasks ADD COLUMN interval_minutes INTEGER"
        )
    if "schedule_type" not in cols:
        cursor.execute(
            "ALTER TABLE scheduled_tasks ADD COLUMN schedule_type TEXT NOT NULL DEFAULT 'once'"
        )
    if "schedule_config" not in cols:
        cursor.execute(
            "ALTER TABLE scheduled_tasks ADD COLUMN schedule_config TEXT"
        )
    if "notify_type" not in cols:
        cursor.execute(
            "ALTER TABLE scheduled_tasks ADD COLUMN notify_type TEXT NOT NULL DEFAULT 'none'"
        )
    if "notify_config" not in cols:
        cursor.execute(
            "ALTER TABLE scheduled_tasks ADD COLUMN notify_config TEXT"
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

    conn.commit()
    conn.close()


init_database()

# 初始化默认白名单（在 init_database 之后调用，避免循环导入）
from db.path_permissions import init_default_whitelist
init_default_whitelist()
