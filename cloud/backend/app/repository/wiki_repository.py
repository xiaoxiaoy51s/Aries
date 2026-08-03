"""知识库任务队列数据访问层（kb_jobs）。

知识库文档不再入库：页面直接存在 ~/.Aries/{email}/wiki/ 文件系统（文件夹由 AI 组织），
列表/详情/检索全部基于文件扫描 + BM25，因此本层只负责异步任务队列。
"""
from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.wiki import KbJob
from app.utils.time_utils import local_now


class WikiRepository:
    # ============ kb_jobs ============

    @staticmethod
    async def create_job(
        db: AsyncSession, user_id: int, type: str, payload: dict | None = None
    ) -> KbJob:
        job = KbJob(user_id=user_id, type=type, payload=payload or {})
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job

    @staticmethod
    async def list_jobs(
        db: AsyncSession, user_id: int, limit: int = 20, offset: int = 0
    ) -> list[KbJob]:
        res = await db.execute(
            select(KbJob).where(KbJob.user_id == user_id)
            .order_by(KbJob.id.desc()).limit(limit).offset(offset)
        )
        return list(res.scalars().all())

    @staticmethod
    async def count_jobs(db: AsyncSession, user_id: int) -> int:
        res = await db.execute(
            select(func.count(KbJob.id)).where(KbJob.user_id == user_id)
        )
        return int(res.scalar() or 0)

    @staticmethod
    async def claim_next_job(db: AsyncSession) -> KbJob | None:
        """原子领取一个 queued 任务（FOR UPDATE SKIP LOCKED）。"""
        res = await db.execute(
            text(
                "SELECT id FROM kb_jobs WHERE status='queued' "
                "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1"
            )
        )
        row = res.fetchone()
        if not row:
            return None
        job_id = row[0]
        await db.execute(
            text("UPDATE kb_jobs SET status='running', started_at=:now WHERE id=:id"),
            {"id": job_id, "now": local_now()},
        )
        await db.commit()
        res = await db.execute(select(KbJob).where(KbJob.id == job_id))
        return res.scalar_one_or_none()

    @staticmethod
    async def finish_job(
        db: AsyncSession, job_id: int, error: str | None = None
    ) -> None:
        await db.execute(
            text(
                "UPDATE kb_jobs SET status=:s, finished_at=:now, error=:e WHERE id=:id"
            ),
            {"s": "failed" if error else "done", "e": error, "id": job_id, "now": local_now()},
        )
        await db.commit()
