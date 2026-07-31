"""定时任务数据访问层（async）。

参照 backend/db/scheduled_task.py 的 CRUD 函数，适配 SQLAlchemy async。
"""
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.scheduled_task import ScheduledTask
from app.utils.time_utils import local_now_iso, local_now_minus, normalize_local_iso


class ScheduledTaskRepository:
    """定时任务数据访问层"""

    @staticmethod
    async def create(db: AsyncSession, **kwargs) -> ScheduledTask:
        task = ScheduledTask(**kwargs)
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task

    @staticmethod
    async def find_by_id(db: AsyncSession, task_id: int) -> ScheduledTask | None:
        result = await db.execute(select(ScheduledTask).where(ScheduledTask.id == task_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_pending_tasks(db: AsyncSession, now_iso: str, limit: int = 50) -> list[ScheduledTask]:
        result = await db.execute(
            select(ScheduledTask)
            .where(ScheduledTask.status == "pending")
            .where(ScheduledTask.scheduled_at <= now_iso)
            .order_by(ScheduledTask.scheduled_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_tasks(
        db: AsyncSession, user_id: int, page: int = 1, page_size: int = 20
    ) -> tuple[list[ScheduledTask], int]:
        offset = (page - 1) * page_size
        result = await db.execute(
            select(ScheduledTask)
            .where(ScheduledTask.user_id == user_id)
            .order_by(ScheduledTask.created_at.desc())
            .limit(page_size)
            .offset(offset)
        )
        tasks = list(result.scalars().all())

        count_result = await db.execute(
            select(func.count()).select_from(ScheduledTask).where(ScheduledTask.user_id == user_id)
        )
        total = count_result.scalar() or 0
        return tasks, total

    @staticmethod
    async def update_status(
        db: AsyncSession, task_id: int, status: str, *, executed_at: str | None = None
    ) -> None:
        now = local_now_iso()
        values: dict = {"status": status, "updated_at": now}
        if executed_at:
            values["executed_at"] = normalize_local_iso(executed_at)
        await db.execute(
            update(ScheduledTask).where(ScheduledTask.id == task_id).values(**values)
        )
        await db.commit()

    @staticmethod
    async def update_session_id(db: AsyncSession, task_id: int, session_id: str) -> None:
        now = local_now_iso()
        await db.execute(
            update(ScheduledTask)
            .where(ScheduledTask.id == task_id)
            .values(session_id=session_id, updated_at=now)
        )
        await db.commit()

    @staticmethod
    async def reset_stale_running_tasks(db: AsyncSession, stale_minutes: int = 10) -> int:
        cutoff = local_now_minus(minutes=stale_minutes)
        now = local_now_iso()
        result = await db.execute(
            update(ScheduledTask)
            .where(ScheduledTask.status == "running")
            .where(ScheduledTask.updated_at < cutoff)
            .values(status="pending", updated_at=now)
        )
        await db.commit()
        return result.rowcount

    @staticmethod
    async def cancel_task(db: AsyncSession, task_id: int) -> bool:
        now = local_now_iso()
        result = await db.execute(
            update(ScheduledTask)
            .where(ScheduledTask.id == task_id)
            .where(ScheduledTask.status == "pending")
            .values(status="cancelled", updated_at=now)
        )
        await db.commit()
        return result.rowcount > 0

    @staticmethod
    async def delete_task(db: AsyncSession, task_id: int) -> bool:
        result = await db.execute(
            delete(ScheduledTask).where(ScheduledTask.id == task_id)
        )
        await db.commit()
        return result.rowcount > 0
