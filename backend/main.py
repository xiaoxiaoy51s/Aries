from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import asyncio
import logging
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
from api import config_router, chat_router, upload_router, skills_router, plugins_router, sessions_router, debug_router, scheduled_tasks_router, platforms_router, system_router, path_permissions_router
from db.database import init_database
from utils.scheduler import run_scheduler

init_database()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from db.scheduled_task import reset_stale_running_tasks
    from utils.mcp_runtime import get_mcp_pool

    stale = reset_stale_running_tasks()
    if stale:
        print(f"[Scheduler] 启动时重置 {stale} 个中断的 running 任务")

    mcp_pool = get_mcp_pool()
    mcp_pool.start()
    try:
        mcp_pool.rebuild()
        print("[MCP] 连接池已初始化")
    except Exception as exc:
        print(f"[MCP] 连接池初始化失败: {exc}")

    scheduler_task = asyncio.create_task(run_scheduler())

    import threading
    from services.bot_manager import start_all_bots

    def _boot_bots():
        try:
            start_all_bots()
        except Exception as e:
            print(f"[BotManager] 启动异常: {e}")

    threading.Thread(target=_boot_bots, daemon=True, name="BotManagerBoot").start()

    yield

    mcp_pool.shutdown()
    print("[MCP] 连接池已关闭")
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="MIMOClaw API",
    description="MIMOClaw AI Agent Backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

uploads_path = (Path.home() / ".MIMOClaw" / "uploads").resolve()
uploads_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")

app.include_router(config_router)
app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(skills_router)
app.include_router(plugins_router)
app.include_router(sessions_router)
app.include_router(debug_router)
app.include_router(scheduled_tasks_router)
app.include_router(platforms_router)
app.include_router(system_router)
app.include_router(path_permissions_router)


@app.get("/")
def root():
    return {"message": "MIMOClaw API", "version": "1.0.0"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("BACKEND_PORT", 30000))
    uvicorn.run(app, host="127.0.0.1", port=port, reload=False)
