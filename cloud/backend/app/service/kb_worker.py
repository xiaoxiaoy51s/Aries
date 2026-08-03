"""知识库后台任务 worker：轮询 kb_jobs 并执行（ingest）。

在 main.py lifespan 中作为后台任务启动。ingest 涉及 LLM 调用（10-30s），
不能阻塞 HTTP 请求线程，故走任务队列。
"""
from __future__ import annotations

import asyncio
import logging
import traceback

from app.config.settings import settings
from app.database import async_session
from app.repository.user_repository import UserRepository
from app.repository.wiki_repository import WikiRepository
from app.service.kb_service import KbService
from app.service.model_config_service import ModelConfigService
from app.service.wiki.templates import SourceMeta

logger = logging.getLogger(__name__)


async def _run_job(job) -> None:
    async with async_session() as db:
        user = await UserRepository.find_by_id(db, job.user_id)
        if not user:
            await WikiRepository.finish_job(db, job.id, error="用户不存在")
            return
        email = user.email
        try:
            # 摄取类任务依赖对话模型生成 md 文档：未配置时直接失败并给出明确指引
            if job.type in ("ingest_text", "ingest_file", "ingest_zip", "ingest_link"):
                model = await ModelConfigService.get_active_model(email)
                if not model:
                    raise RuntimeError(
                        "尚未配置对话模型，请在「设置 → 模型管理」中配置后再导入。"
                    )
            if job.type == "ingest_text":
                p = job.payload or {}
                meta = SourceMeta(**(p.get("meta") or {}))
                await KbService.ingest_text(email, p.get("text", ""), meta)
            elif job.type == "ingest_file":
                p = job.payload or {}
                await KbService.ingest_file(
                    email,
                    p.get("file_path", ""),
                    p.get("file_name", ""),
                    p.get("file_type", ""),
                    p.get("file_digest", ""),
                    p.get("source_label", ""),
                )
            elif job.type == "ingest_zip":
                p = job.payload or {}
                await KbService.ingest_zip(
                    email,
                    p.get("zip_path", ""),
                    p.get("source_label", ""),
                )
            elif job.type == "ingest_link":
                p = job.payload or {}
                await KbService.ingest_link(
                    email, p.get("url", ""), p.get("platform", "")
                )
            else:
                raise ValueError(f"未知任务类型: {job.type}")

            await WikiRepository.finish_job(db, job.id)
            logger.info("[KB Worker] job %s done (%s)", job.id, job.type)
        except Exception as e:
            err = f"{e}\n{traceback.format_exc()[:800]}"
            await WikiRepository.finish_job(db, job.id, error=err)
            logger.exception("[KB Worker] job %s failed", job.id)


async def kb_worker_loop() -> None:
    """并发拉取并执行任务。"""
    sem = asyncio.Semaphore(settings.KB_WORKER_CONCURRENCY)
    logger.info("[KB Worker] 启动，并发=%d", settings.KB_WORKER_CONCURRENCY)
    while True:
        try:
            async with async_session() as db:
                job = await WikiRepository.claim_next_job(db)
            if not job:
                await asyncio.sleep(settings.KB_WORKER_INTERVAL)
                continue

            async def _guarded(j):
                async with sem:
                    await _run_job(j)

            asyncio.create_task(_guarded(job))
        except Exception:
            logger.exception("[KB Worker] 轮询异常")
            await asyncio.sleep(settings.KB_WORKER_INTERVAL)
