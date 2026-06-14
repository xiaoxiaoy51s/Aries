from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.scheduled_task import (
    SCHEDULE_DAILY,
    SCHEDULE_INTERVAL,
    SCHEDULE_ONCE,
    cancel_task,
    create_task,
    delete_task,
    get_task_by_id,
    list_tasks,
)
from utils.time_utils import local_now, normalize_local_iso
from datetime import timedelta
from db.chat import list_recent_sessions
from db.sessions import list_sessions as list_session_meta

router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])


class CreateTaskRequest(BaseModel):
    title: str
    scheduled_at: str | None = None
    task_content: str | None = None
    session_id: str | None = None
    session_mode: str | None = None
    schedule_type: str = SCHEDULE_ONCE
    interval_minutes: int | None = None
    notify_type: str | None = None


def _normalize_create_request(body: CreateTaskRequest) -> dict:
    schedule_type = (body.schedule_type or SCHEDULE_ONCE).strip()
    if schedule_type == "recurring":
        schedule_type = SCHEDULE_INTERVAL

    session_id = (body.session_id or "").strip() or None
    if body.session_mode == "new":
        session_id = None

    notify_type = (body.notify_type or "none").strip()
    if notify_type in ("wechat", "qq", "feishu") and not session_id:
        session_id = f"__{notify_type}__"

    task_content = (body.task_content or "").strip()
    if not task_content:
        raise ValueError("要求说明不能为空")

    interval_minutes: int | None = None
    scheduled_at = body.scheduled_at

    if schedule_type == SCHEDULE_INTERVAL:
        interval_minutes = int(body.interval_minutes or 0)
        if interval_minutes <= 0:
            raise ValueError("间隔任务必须提供 interval_minutes")
        if not scheduled_at:
            scheduled_at = normalize_local_iso(
                (local_now() + timedelta(minutes=interval_minutes)).isoformat()
            )
    elif schedule_type == SCHEDULE_DAILY:
        if not scheduled_at:
            raise ValueError("每天任务必须提供 scheduled_at")
    else:
        if not scheduled_at:
            raise ValueError("单次任务必须提供 scheduled_at")

    return {
        "title": (body.title or "").strip(),
        "scheduled_at": normalize_local_iso(scheduled_at),
        "task_content": task_content,
        "session_id": session_id,
        "schedule_type": schedule_type,
        "interval_minutes": interval_minutes,
    }


@router.post("/")
def create_scheduled_task(body: CreateTaskRequest):
    payload = _normalize_create_request(body)
    try:
        task_id = create_task(**payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, "task_id": task_id}


@router.get("/")
def list_scheduled_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return list_tasks(page=page, page_size=page_size)


@router.get("/sessions/list")
def list_task_sessions(limit: int = Query(50, ge=1, le=200)):
    """供定时任务绑定已有会话使用。"""
    meta_map = {m["session_id"]: m for m in list_session_meta(limit=limit * 2)}
    recent = list_recent_sessions(limit=limit)
    seen: set[str] = set()
    items: list[dict] = []

    for s in recent:
        sid = s["session_id"]
        if sid.startswith("__") and sid.endswith("__"):
            continue
        seen.add(sid)
        meta = meta_map.get(sid, {})
        items.append({
            "session_id": sid,
            "title": meta.get("title") or s.get("last_user_message") or "",
            "work_dir": meta.get("work_dir", ""),
            "created_at": meta.get("created_at") or s.get("created_at") or "",
            "updated_at": meta.get("updated_at") or s.get("created_at") or "",
            "last_user_message": s.get("last_user_message") or "",
        })

    for sid, meta in meta_map.items():
        if sid in seen or (sid.startswith("__") and sid.endswith("__")):
            continue
        items.append({
            "session_id": sid,
            "title": meta.get("title", ""),
            "work_dir": meta.get("work_dir", ""),
            "created_at": meta.get("created_at", ""),
            "updated_at": meta.get("updated_at", ""),
            "last_user_message": "",
        })

    items.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)
    return {"sessions": items[:limit]}


@router.get("/{task_id}")
def get_task(task_id: int):
    task = get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/{task_id}/cancel")
def cancel_scheduled_task(task_id: int):
    ok = cancel_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在或无法取消")
    return {"success": True}


@router.delete("/{task_id}")
def delete_scheduled_task(task_id: int):
    ok = delete_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True}
