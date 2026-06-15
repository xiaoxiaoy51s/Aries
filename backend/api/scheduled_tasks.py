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
    normalize_task_create_payload,
)
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
    return normalize_task_create_payload(
        title=body.title,
        task_content=body.task_content,
        scheduled_at=body.scheduled_at,
        session_id=body.session_id,
        session_mode=body.session_mode,
        schedule_type=body.schedule_type,
        interval_minutes=body.interval_minutes,
        notify_type=body.notify_type,
    )


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
