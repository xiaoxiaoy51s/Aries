import json
from datetime import timedelta

from utils.time_utils import (
    local_now,
    local_now_iso,
    local_now_minus,
    normalize_local_iso,
    parse_local_iso,
)

from .database import get_connection

SCHEDULE_ONCE = "once"
SCHEDULE_DAILY = "daily"
SCHEDULE_INTERVAL = "interval"
SCHEDULE_TYPES = (SCHEDULE_ONCE, SCHEDULE_DAILY, SCHEDULE_INTERVAL)

PLATFORM_SESSION_MAP = {
    "__wechat__": "wechat",
    "__qq__": "qq",
    "__feishu__": "feishu",
}

_TASK_COLUMNS = (
    "id, title, task_content, scheduled_at, session_id, status, "
    "task_type, interval_seconds, interval_minutes, schedule_type, schedule_config, "
    "notify_type, notify_config, created_at, updated_at, executed_at"
)


def _load_json(value) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def infer_platform(session_id: str | None) -> str | None:
    return PLATFORM_SESSION_MAP.get((session_id or "").strip())


def infer_notify_type(session_id: str | None, legacy_notify: str | None = None) -> str:
    platform = infer_platform(session_id)
    if platform:
        return platform
    legacy = (legacy_notify or "none").strip()
    if legacy in ("wechat", "qq", "feishu"):
        return legacy
    return "none"


def is_recurring(schedule_type: str | None) -> bool:
    st = (schedule_type or SCHEDULE_ONCE).strip()
    return st in (SCHEDULE_DAILY, SCHEDULE_INTERVAL)


def _resolve_interval_minutes(task: dict) -> int:
    minutes = task.get("interval_minutes")
    if minutes is not None and int(minutes) > 0:
        return int(minutes)
    config = _load_json(task.get("schedule_config"))
    legacy_mins = int(config.get("minutes") or 0)
    if legacy_mins > 0:
        return legacy_mins
    legacy_secs = task.get("interval_seconds")
    if legacy_secs:
        return max(1, int(legacy_secs) // 60)
    return 0


def compute_next_scheduled_at(task: dict, *, base_time=None) -> str:
    """基于实际完成时刻计算下次 scheduled_at（本地时间）。"""
    now = base_time if base_time is not None else local_now()
    if isinstance(now, str):
        now = parse_local_iso(now)

    schedule_type = (task.get("schedule_type") or SCHEDULE_ONCE).strip()

    if schedule_type == SCHEDULE_INTERVAL:
        minutes = _resolve_interval_minutes(task)
        if minutes <= 0:
            raise ValueError("间隔任务缺少 interval_minutes")
        return normalize_local_iso((now + timedelta(minutes=minutes)).isoformat())

    if schedule_type == SCHEDULE_DAILY:
        ref_raw = task.get("scheduled_at") or ""
        try:
            ref = parse_local_iso(ref_raw)
            hour, minute = ref.hour, ref.minute
        except ValueError:
            hour, minute = 9, 0
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        return normalize_local_iso(next_run.isoformat())

    raise ValueError("一次性任务无需计算下次执行时间")


def normalize_task_create_payload(
    *,
    title: str = "",
    task_content: str = "",
    scheduled_at: str | None = None,
    session_id: str | None = None,
    session_mode: str | None = None,
    schedule_type: str = SCHEDULE_ONCE,
    interval_minutes: int | None = None,
    notify_type: str | None = None,
    default_session_id: str | None = None,
) -> dict:
    """规范化创建定时任务的字段，供 API 与 agent 工具共用。"""
    schedule_type = (schedule_type or SCHEDULE_ONCE).strip()
    if schedule_type == "recurring":
        schedule_type = SCHEDULE_INTERVAL
    if schedule_type not in SCHEDULE_TYPES:
        raise ValueError(f"schedule_type 必须是 {SCHEDULE_TYPES} 之一")

    session_id = (session_id or "").strip() or None
    if session_mode == "new":
        session_id = None

    notify = (notify_type or "none").strip()
    if notify in PLATFORM_SESSION_MAP.values() and not session_id:
        session_id = f"__{notify}__"
    elif not session_id and default_session_id:
        session_id = (default_session_id or "").strip() or None

    task_content = (task_content or "").strip()
    if not task_content:
        raise ValueError("要求说明不能为空")

    stored_interval: int | None = None

    if schedule_type == SCHEDULE_INTERVAL:
        stored_interval = int(interval_minutes or 0)
        if stored_interval <= 0:
            raise ValueError("间隔任务必须提供 interval_minutes")
        if not scheduled_at:
            scheduled_at = normalize_local_iso(
                (local_now() + timedelta(minutes=stored_interval)).isoformat()
            )
    elif schedule_type == SCHEDULE_DAILY:
        if not scheduled_at:
            raise ValueError("每天任务必须提供 scheduled_at")
    else:
        if not scheduled_at:
            raise ValueError("单次任务必须提供 scheduled_at")

    return {
        "title": (title or "").strip(),
        "scheduled_at": normalize_local_iso(scheduled_at),
        "task_content": task_content,
        "session_id": session_id,
        "schedule_type": schedule_type,
        "interval_minutes": stored_interval,
    }


def create_task(
    title: str,
    scheduled_at: str,
    task_content: str | None = None,
    session_id: str | None = None,
    *,
    schedule_type: str = SCHEDULE_ONCE,
    interval_minutes: int | None = None,
    notify_type: str | None = None,
) -> int:
    if schedule_type not in SCHEDULE_TYPES:
        raise ValueError(f"schedule_type 必须是 {SCHEDULE_TYPES} 之一")

    title = (title or "").strip()
    task_content = (task_content or "").strip()
    if not task_content:
        raise ValueError("要求说明不能为空")

    scheduled_at = normalize_local_iso(scheduled_at)
    session_id = (session_id or "").strip() or None

    legacy_notify = (notify_type or "none").strip()
    if not session_id and legacy_notify in PLATFORM_SESSION_MAP.values():
        for sid, plat in PLATFORM_SESSION_MAP.items():
            if plat == legacy_notify:
                session_id = sid
                break

    stored_interval: int | None = None
    if schedule_type == SCHEDULE_INTERVAL:
        stored_interval = int(interval_minutes or 0)
        if stored_interval <= 0:
            raise ValueError("间隔任务必须提供 interval_minutes")

    conn = get_connection()
    now = local_now_iso()
    cursor = conn.execute(
        """
        INSERT INTO scheduled_tasks
            (title, task_content, scheduled_at, session_id, status,
             interval_minutes, schedule_type, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
        """,
        (
            title,
            task_content,
            scheduled_at,
            session_id,
            stored_interval,
            schedule_type,
            now,
            now,
        ),
    )
    conn.commit()
    task_id = int(cursor.lastrowid)
    conn.close()
    return task_id


def insert_next_recurring_task(task: dict, executed_at: str, session_id: str | None = None) -> int:
    """执行完成后插入下一条循环任务，字段与原任务一致，仅 scheduled_at 重新计算。"""
    effective_session = (session_id if session_id is not None else task.get("session_id") or "").strip() or None
    payload = {
        **task,
        "session_id": effective_session,
    }
    next_at = compute_next_scheduled_at(payload, base_time=executed_at)
    return create_task(
        title=task.get("title") or "",
        scheduled_at=next_at,
        task_content=task.get("task_content") or "",
        session_id=effective_session,
        schedule_type=(task.get("schedule_type") or SCHEDULE_ONCE).strip(),
        interval_minutes=task.get("interval_minutes"),
    )


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
    cutoff = local_now_minus(minutes=stale_minutes)
    now = local_now_iso()
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
    now = local_now_iso()
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
    now = local_now_iso()
    conn = get_connection()
    if executed_at:
        executed_at = normalize_local_iso(executed_at)
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


def cancel_task(task_id: int) -> bool:
    conn = get_connection()
    cursor = conn.execute(
        "UPDATE scheduled_tasks SET status = 'cancelled', updated_at = ? WHERE id = ? AND status = 'pending'",
        (local_now_iso(), task_id),
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


def _normalize_schedule_type(row) -> str:
    raw = row["schedule_type"] if "schedule_type" in row.keys() and row["schedule_type"] else ""
    st = (raw or SCHEDULE_ONCE).strip()
    if st == "recurring":
        return SCHEDULE_INTERVAL
    if st in SCHEDULE_TYPES:
        return st
    if (row["task_type"] or "") == "recurring":
        return SCHEDULE_INTERVAL
    return SCHEDULE_ONCE


def _row_to_dict(row) -> dict:
    schedule_type = _normalize_schedule_type(row)
    session_id = row["session_id"] or ""
    legacy_notify = row["notify_type"] if "notify_type" in row.keys() else None

    interval_minutes = None
    if "interval_minutes" in row.keys() and row["interval_minutes"] is not None:
        interval_minutes = int(row["interval_minutes"])
    if schedule_type == SCHEDULE_INTERVAL and (not interval_minutes or interval_minutes <= 0):
        interval_minutes = _resolve_interval_minutes({
            "interval_minutes": None,
            "schedule_config": row["schedule_config"] if "schedule_config" in row.keys() else None,
            "interval_seconds": row["interval_seconds"] if "interval_seconds" in row.keys() else None,
        }) or None

    notify_type = infer_notify_type(session_id, legacy_notify)

    return {
        "id": row["id"],
        "title": row["title"] or "",
        "task_content": row["task_content"] or "",
        "scheduled_at": row["scheduled_at"] or "",
        "session_id": session_id,
        "status": row["status"],
        "schedule_type": schedule_type,
        "interval_minutes": interval_minutes,
        "notify_type": notify_type,
        "created_at": row["created_at"] or "",
        "updated_at": row["updated_at"] or "",
        "executed_at": row["executed_at"] or "",
    }
