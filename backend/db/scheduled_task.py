from datetime import datetime, timedelta

from .database import get_connection

TASK_TYPE_ONCE = "once"
TASK_TYPE_RECURRING = "recurring"
TASK_TYPES = (TASK_TYPE_ONCE, TASK_TYPE_RECURRING)

_TASK_COLUMNS = (
    "id, title, task_content, scheduled_at, session_id, status, "
    "task_type, interval_seconds, created_at, updated_at, executed_at"
)


def create_task(
    title: str,
    scheduled_at: str,
    task_content: str | None = None,
    session_id: str | None = None,
    *,
    task_type: str = TASK_TYPE_ONCE,
    interval_seconds: int | None = None,
) -> int:
    if task_type not in TASK_TYPES:
        raise ValueError(f"task_type 必须是 {TASK_TYPES} 之一")
    if task_type == TASK_TYPE_RECURRING and (
        interval_seconds is None or interval_seconds <= 0
    ):
        raise ValueError("循环任务必须提供大于 0 的 interval_seconds")
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    cursor = conn.execute(
        f"""
        INSERT INTO scheduled_tasks
            (title, task_content, scheduled_at, session_id, status,
             task_type, interval_seconds, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
        """,
        (
            title,
            task_content,
            scheduled_at,
            session_id,
            task_type,
            interval_seconds,
            now,
            now,
        ),
    )
    conn.commit()
    task_id = int(cursor.lastrowid)
    conn.close()
    return task_id


def get_pending_tasks(now: str, limit: int = 50) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT {_TASK_COLUMNS}
        FROM scheduled_tasks
        WHERE status = 'pending'
          AND scheduled_at <= ?
        ORDER BY scheduled_at ASC
        LIMIT ?
        """,
        (now, limit),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_task_by_id(task_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        f"SELECT {_TASK_COLUMNS} FROM scheduled_tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def list_tasks(page: int = 1, page_size: int = 20) -> dict:
    conn = get_connection()
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"""
        SELECT {_TASK_COLUMNS}
        FROM scheduled_tasks
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (page_size, offset),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM scheduled_tasks",
    ).fetchone()[0]
    conn.close()
    return {
        "tasks": [_row_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def reset_stale_running_tasks(stale_minutes: int = 10) -> int:
    """将长时间未完成的 running 任务重置为 pending（应对服务重启/热重载中断）。"""
    cutoff = (datetime.utcnow() - timedelta(minutes=stale_minutes)).isoformat()
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cursor = conn.execute(
        """
        UPDATE scheduled_tasks
        SET status = 'pending', updated_at = ?
        WHERE status = 'running' AND updated_at < ?
        """,
        (now, cutoff),
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected


def update_task_session_id(task_id: int, session_id: str) -> None:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    conn.execute(
        "UPDATE scheduled_tasks SET session_id = ?, updated_at = ? WHERE id = ?",
        (session_id, now, task_id),
    )
    conn.commit()
    conn.close()


def update_task_status(
    task_id: int,
    status: str,
    *,
    executed_at: str | None = None,
) -> None:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    if executed_at:
        conn.execute(
            "UPDATE scheduled_tasks SET status = ?, executed_at = ?, updated_at = ? WHERE id = ?",
            (status, executed_at, now, task_id),
        )
    else:
        conn.execute(
            "UPDATE scheduled_tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, task_id),
        )
    conn.commit()
    conn.close()


def reschedule_recurring_task(task_id: int, next_scheduled_at: str) -> None:
    """循环任务执行完毕后，将状态重置为 pending 并写入下次执行时间。"""
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    conn.execute(
        """
        UPDATE scheduled_tasks
        SET status = 'pending',
            scheduled_at = ?,
            executed_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (next_scheduled_at, now, now, task_id),
    )
    conn.commit()
    conn.close()


def cancel_task(task_id: int) -> bool:
    conn = get_connection()
    cursor = conn.execute(
        "UPDATE scheduled_tasks SET status = 'cancelled', updated_at = ? WHERE id = ? AND status = 'pending'",
        (datetime.utcnow().isoformat(), task_id),
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


def delete_task(task_id: int) -> bool:
    conn = get_connection()
    cursor = conn.execute(
        "DELETE FROM scheduled_tasks WHERE id = ?",
        (task_id,),
    )
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"] or "",
        "task_content": row["task_content"] or "",
        "scheduled_at": row["scheduled_at"] or "",
        "session_id": row["session_id"] or "",
        "status": row["status"],
        "task_type": row["task_type"] or TASK_TYPE_ONCE,
        "interval_seconds": row["interval_seconds"],
        "created_at": row["created_at"] or "",
        "updated_at": row["updated_at"] or "",
        "executed_at": row["executed_at"] or "",
    }
