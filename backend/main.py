from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import asyncio
import logging
import signal
import sys
import threading
from contextlib import asynccontextmanager

# Windows: 主事件循环使用 SelectorEventLoop，避免 ProactorEventLoop 的 IOCP accept
# 在 MCP 子进程启动时冲突导致 WinError 64（accept 循环崩溃后服务器无法接收新连接）。
# MCP 线程会显式创建 ProactorEventLoop 以支持 stdio 子进程。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
from api import config_router, chat_router, upload_router, skills_router, plugins_router, subagents_router, sessions_router, work_dirs_router, debug_router, scheduled_tasks_router, platforms_router, system_router, path_permissions_router, terminal_router, git_router, files_router, chat_ws_router, memory_router, pets_router, network_router, main_agent_router
from db.database import init_database
from utils.scheduler import run_scheduler

init_database()


_PROXY_ENV_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
)


def _check_and_cleanup_proxy():
    """启动时检测系统代理端口是否可达，不可达则全局清除代理环境变量。

    清除后整个进程（含 MCP 子进程、httpx 等）都不会走死掉的代理，
    避免子进程卡在连接代理端口。network_manager 的按域名/命令注入不受影响。
    """
    import socket
    from urllib.parse import urlparse

    proxy_urls: list[str] = []
    for key in _PROXY_ENV_KEYS:
        val = (os.environ.get(key) or "").strip()
        if val:
            proxy_urls.append(val)

    if not proxy_urls:
        print("[Proxy] 系统未设置代理环境变量")
        return

    proxy_reachable = False
    for url in proxy_urls:
        try:
            parsed = urlparse(url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 8080
            with socket.create_connection((host, port), timeout=2):
                proxy_reachable = True
                break
        except (OSError, ValueError):
            continue

    if proxy_reachable:
        print(f"[Proxy] 代理可用，保持环境变量（{proxy_urls[0]}）")
    else:
        for key in _PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["NO_PROXY"] = "*"
        print(f"[Proxy] 代理端口不可达，已清除全部代理环境变量（原: {proxy_urls[0]}）")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from db.scheduled_task import reset_stale_running_tasks
    from utils.mcp_runtime import get_mcp_pool

    _check_and_cleanup_proxy()

    stale = reset_stale_running_tasks()
    if stale:
        print(f"[Scheduler] 启动时重置 {stale} 个中断的 running 任务")

    mcp_pool = get_mcp_pool()
    mcp_pool.start()

    # MCP 连接池在后台初始化，不阻塞 FastAPI 启动
    # 某个 MCP 服务器连不上（如 npx 下载慢、代理未开）时不会卡住整个应用
    def _init_mcp():
        try:
            mcp_pool.rebuild()
            print("[MCP] 连接池已初始化")
        except Exception as exc:
            print(f"[MCP] 连接池初始化失败: {exc}")

    threading.Thread(target=_init_mcp, daemon=True, name="McpInit").start()

    scheduler_task = asyncio.create_task(run_scheduler())

    from services.bot_manager import start_all_bots

    def _boot_bots():
        try:
            start_all_bots()
        except Exception as e:
            print(f"[BotManager] 启动异常: {e}")

    threading.Thread(target=_boot_bots, daemon=True, name="BotManagerBoot").start()

    # ---- 启动 Node.js CLI Server（VS Code 风格 CLI） ----
    # 放到线程中执行，避免阻塞 FastAPI 事件循环
    def _boot_cli():
        try:
            from services.terminal_manager import start_cli_server
            cli_port = start_cli_server()
            print(f"[CLI] Node.js CLI Server 已启动 (port={cli_port})")
        except Exception as exc:
            print(f"[CLI] 启动 Node.js CLI Server 失败: {exc}")

    cli_thread = threading.Thread(target=_boot_cli, daemon=True, name="CLIBoot")
    cli_thread.start()
    # 等待 CLI Server 就绪（最多 10 秒）
    cli_thread.join(timeout=10)

    yield

    # 先停 bots（它们各自跑在子线程的事件循环里）
    try:
        from services.bot_manager import stop_all_bots
        stop_all_bots()
        print("[BotManager] 全部 bots 已停止")
    except Exception as exc:
        print(f"[Shutdown] 关闭 bots 异常: {exc}")

    mcp_pool.shutdown()
    print("[MCP] 连接池已关闭")

    # ---- 停止 Node.js CLI Server ----
    try:
        from services.terminal_manager import stop_cli_server
        stop_cli_server()
        print("[CLI] Node.js CLI Server 已停止")
    except Exception as exc:
        print(f"[Shutdown] 停止 CLI Server 异常: {exc}")

    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Aries API",
    description="Aries AI Agent Backend",
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

uploads_path = (Path.home() / ".Aries" / "uploads").resolve()
uploads_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")

# 挂载宠物资源目录：~/.Aries/pets（Codex 兼容格式：spritesheet.webp + pet.json）
pet_gifs_path = (Path.home() / ".Aries" / "pets").resolve()
pet_gifs_path.mkdir(parents=True, exist_ok=True)
app.mount("/pets/static", StaticFiles(directory=str(pet_gifs_path)), name="pets-static")

app.include_router(config_router)
app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(skills_router)
app.include_router(plugins_router)
app.include_router(subagents_router)
app.include_router(sessions_router)
app.include_router(work_dirs_router)
app.include_router(debug_router)
app.include_router(scheduled_tasks_router)
app.include_router(platforms_router)
app.include_router(system_router)
app.include_router(path_permissions_router)
app.include_router(terminal_router)
app.include_router(git_router)
app.include_router(files_router)
app.include_router(chat_ws_router)
app.include_router(memory_router)
app.include_router(pets_router)
app.include_router(network_router)
app.include_router(main_agent_router)


@app.get("/")
def root():
    return {"message": "Aries API", "version": "1.0.0"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("BACKEND_PORT", 30000))

    # 兜底：lifespan 退出 + bots 关闭后，如果进程还卡在子线程上，
    # 超过 FORCE_EXIT_TIMEOUT 秒就 os._exit，避免 Ctrl+C 后一直挂着。
    FORCE_EXIT_TIMEOUT = float(os.environ.get("ARIES_FORCE_EXIT_TIMEOUT", "8"))

    def _force_exit():
        print(f"[Shutdown] 超时 {FORCE_EXIT_TIMEOUT}s，强制退出")
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)

    def _install_force_exit_timer():
        # 只在收到退出信号后才启动计时器
        def _handler(signum, frame):
            timer = threading.Timer(FORCE_EXIT_TIMEOUT, _force_exit)
            timer.daemon = True
            timer.start()
            # 默认行为交回：抛 KeyboardInterrupt，让 uvicorn 走优雅退出
        try:
            signal.signal(signal.SIGINT, _handler)
            signal.signal(signal.SIGTERM, _handler)
        except (ValueError, OSError):
            pass  # 非主线程调用时可能会失败，忽略

    _install_force_exit_timer()
    uvicorn.run(app, host="127.0.0.1", port=port, reload=False)
