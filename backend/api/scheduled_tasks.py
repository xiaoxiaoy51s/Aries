from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.scheduled_task import (
    cancel_task,
    create_task,
    delete_task,
    get_task_by_id,
    list_tasks,
)

router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])


class CreateTaskRequest(BaseModel):
    title: str
    scheduled_at: str
    task_content: str | None = None
    session_id: str | None = None
    task_type: str = "once"
    interval_seconds: int | None = None


@router.post("/")
def create_scheduled_task(body: CreateTaskRequest):
    task_id = create_task(
        title=body.title,
        scheduled_at=body.scheduled_at,
        task_content=body.task_content,
        session_id=body.session_id,
        task_type=body.task_type,
        interval_seconds=body.interval_seconds,
    )
    return {"success": True, "task_id": task_id}


@router.get("/")
def list_scheduled_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return list_tasks(page=page, page_size=page_size)


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
