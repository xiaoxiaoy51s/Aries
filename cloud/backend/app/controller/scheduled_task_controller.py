"""定时任务 API 接口。"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.interceptor.auth_interceptor import get_current_user
from app.model.user import User
from app.service.scheduled_task_service import (
    ScheduledTaskService,
    normalize_create_payload,
)

router = APIRouter(prefix="/api/scheduled-tasks", tags=["scheduled-tasks"])


class CreateTaskRequest(BaseModel):
    title: str = ""
    task_content: str
    scheduled_at: Optional[str] = None
    session_id: Optional[str] = None
    session_mode: Optional[str] = None  # "new" 表示新建会话
    schedule_type: str = "once"
    interval_minutes: Optional[int] = None
    notify_type: Optional[str] = None
    auto_delete: bool = False


# ============ 接口 ============

@router.post("")
async def create_task(
    req: CreateTaskRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建定时任务。"""
    try:
        payload = normalize_create_payload(
            title=req.title,
            task_content=req.task_content,
            scheduled_at=req.scheduled_at,
            session_id=req.session_id,
            session_mode=req.session_mode,
            schedule_type=req.schedule_type,
            interval_minutes=req.interval_minutes,
            notify_type=req.notify_type,
            auto_delete=req.auto_delete,
            default_session_id=None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    task_id = await ScheduledTaskService.create_task(
        db,
        user.id,
        title=payload["title"],
        task_content=payload["task_content"],
        scheduled_at=payload["scheduled_at"],
        session_id=payload["session_id"],
        schedule_type=payload["schedule_type"],
        interval_minutes=payload["interval_minutes"],
        auto_delete=payload["auto_delete"],
    )
    return {"id": task_id, "status": "pending"}


@router.get("")
async def list_tasks(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """分页查询当前用户的定时任务列表。"""
    return await ScheduledTaskService.list_tasks(db, user.id, page, page_size)


@router.get("/{task_id}")
async def get_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询单个定时任务详情。"""
    task = await ScheduledTaskService.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["user_id"] != user.id:
        raise HTTPException(status_code=403, detail="无权访问")
    return task


@router.put("/{task_id}/cancel")
async def cancel_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """取消待执行的定时任务。"""
    task = await ScheduledTaskService.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["user_id"] != user.id:
        raise HTTPException(status_code=403, detail="无权操作")
    cancelled = await ScheduledTaskService.cancel_task(db, task_id)
    return {"cancelled": cancelled}


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除定时任务。"""
    task = await ScheduledTaskService.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["user_id"] != user.id:
        raise HTTPException(status_code=403, detail="无权操作")
    deleted = await ScheduledTaskService.delete_task(db, task_id)
    return {"deleted": deleted}
