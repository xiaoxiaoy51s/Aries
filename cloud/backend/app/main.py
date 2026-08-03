import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import settings
from app.controller.auth_controller import router as auth_router
from app.controller.model_controller import router as model_router
from app.controller.chat_controller import router as chat_router
from app.controller.scheduled_task_controller import router as scheduled_task_router
from app.controller.bot_controller import router as bot_router
from app.controller.subagent_controller import router as subagent_router
from app.controller.skills_controller import router as skills_router
from app.controller.workspace_controller import router as workspace_router, upload_router
from app.controller.office_preview_controller import router as office_router
from app.controller.memory_controller import router as memory_router
from app.controller.preview_controller import router as preview_router
from app.controller.kb_controller import router as kb_router
from app.database import init_db
from app.exception.auth_exception import AuthException
from app.tools.sandbox import cleanup_stale_workspaces
from app.utils.scheduler import run_scheduler

# Bot 生命周期（子进程模式，主进程仅负责 spawn/terminate）
from app.services.bot_manager import spawn_all_bot_processes, stop_bot_process
from app.service.kb_worker import kb_worker_loop
from app.service.model_config_service import ModelConfigService

logger = logging.getLogger(__name__)


async def _find_bot_user_email() -> str | None:
    """查找适合启动 bot 的用户邮箱（无 config 扫描结果时的兜底）。

    优先选择有激活模型配置的用户；如果没有，返回注册的第一个用户。
    """
    from sqlalchemy import select
    from app.database import async_session
    from app.model.user import User

    async with async_session() as db:
        result = await db.execute(select(User).limit(100))
        users = result.scalars().all()
        if not users:
            return None
        for user in users:
            model = await ModelConfigService.get_active_model(user.email)
            if model:
                return user.email
        return users[0].email


def _find_users_with_bot_config() -> list[str]:
    """扫描 ~/.Aries/{email}/config.json，返回已启用任一平台的用户邮箱。"""
    emails: list[str] = []
    aries_home = Path.home() / ".Aries"
    if not aries_home.exists():
        return emails
    for user_dir in aries_home.iterdir():
        if not user_dir.is_dir():
            continue
        # 跳过非用户目录
        if user_dir.name in ("plugins",):
            continue
        config_path = user_dir / "config.json"
        if not config_path.exists():
            continue
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for plat in ("qq", "wechat", "feishu"):
            if config.get(plat, {}).get("enabled"):
                emails.append(user_dir.name)
                break
    return emails


async def _workspace_cleanup_loop():
    """后台定时任务：清理超过 TTL 的闲置工作目录（保留 default）。"""
    cleanup_hour = settings.SHELL_CLEANUP_HOUR
    while True:
        now = datetime.now()
        target = now.replace(hour=cleanup_hour, minute=0, second=0, microsecond=0)
        if now >= target:
            target = target + timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        logger.info(f"工作目录 TTL 清理：下次执行于 {target}，等待 {wait_seconds:.0f} 秒")
        await asyncio.sleep(wait_seconds)
        try:
            count = cleanup_stale_workspaces()
            logger.info(f"工作目录 TTL 清理完成：已清理 {count} 个目录")
        except Exception as e:
            logger.error(f"工作目录 TTL 清理失败：{e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # 启动工作区清理定时任务
    cleanup_task = asyncio.create_task(_workspace_cleanup_loop())
    # 启动定时任务调度器
    scheduler_task = asyncio.create_task(run_scheduler())
    # 启动知识库后台 worker（ingest）
    kb_task = asyncio.create_task(kb_worker_loop())

    async def _boot_bots_background() -> None:
        await asyncio.sleep(2)
        bot_emails = _find_users_with_bot_config()
        if not bot_emails:
            fallback = await _find_bot_user_email()
            if fallback:
                bot_emails = [fallback]
        if not bot_emails:
            logger.info("[Lifespan] 无 bot 配置，跳过 bot 启动")
            return
        logger.info("[Lifespan] 为 %s 个用户启动 bot 子进程: %s", len(bot_emails), bot_emails)
        started = spawn_all_bot_processes(bot_emails)
        logger.info("[Lifespan] bot 子进程已启动: %s", started)

    asyncio.create_task(_boot_bots_background())

    yield

    stop_bot_process()
    for task in (cleanup_task, scheduler_task, kb_task):
        task.cancel()
    for task in (cleanup_task, scheduler_task, kb_task):
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    logger.info("[Lifespan] 已关闭")


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常拦截
@app.exception_handler(AuthException)
async def auth_exception_handler(request: Request, exc: AuthException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# 注册路由
app.include_router(auth_router)
app.include_router(model_router)
app.include_router(chat_router)
app.include_router(scheduled_task_router)
app.include_router(bot_router)
app.include_router(subagent_router)
app.include_router(skills_router)
app.include_router(workspace_router)
app.include_router(upload_router)
app.include_router(office_router)
app.include_router(memory_router)
app.include_router(preview_router)
app.include_router(kb_router)


@app.get("/")
async def root():
    return {"name": settings.APP_NAME, "status": "running"}
