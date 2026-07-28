import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import settings
from app.controller.auth_controller import router as auth_router
from app.controller.model_controller import router as model_router
from app.controller.chat_controller import router as chat_router
from app.database import init_db
from app.exception.auth_exception import AuthException
from app.tools.sandbox import cleanup_all_workspaces

logger = logging.getLogger(__name__)


async def _workspace_cleanup_loop():
    """后台定时任务：每天凌晨指定时间清理所有用户工作区。"""
    cleanup_hour = settings.SHELL_CLEANUP_HOUR
    while True:
        now = datetime.now()
        # 计算下一个清理时间（今天或明天的 cleanup_hour:00）
        target = now.replace(hour=cleanup_hour, minute=0, second=0, microsecond=0)
        if now >= target:
            target = target + timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        logger.info(f"工作区清理任务：下次执行于 {target}，等待 {wait_seconds:.0f} 秒")
        await asyncio.sleep(wait_seconds)
        try:
            count = cleanup_all_workspaces()
            logger.info(f"工作区清理完成：已清理 {count} 个用户工作区")
        except Exception as e:
            logger.error(f"工作区清理失败：{e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # 启动工作区清理定时任务
    cleanup_task = asyncio.create_task(_workspace_cleanup_loop())
    yield
    cleanup_task.cancel()


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


@app.get("/")
async def root():
    return {"name": settings.APP_NAME, "status": "running"}
