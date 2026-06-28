"""WebSocket terminal and REST helpers.

前端 WebSocket → Python（透明的代理转发）→ Node.js CLI Server
REST 命令执行 → Python HTTP 客户端 → Node.js CLI Server
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from services.terminal_manager import get_cli_port
from utils.cli_executor import CLIExecutor, get_server_url

import httpx
import websockets

router = APIRouter(tags=["terminal"])


async def _safe_send_text(websocket: WebSocket, text: str) -> bool:
    """向客户端发送文本；若连接已断开则静默失败。"""
    try:
        if websocket.client_state.name == "DISCONNECTED":
            return False
        await websocket.send_text(text)
        return True
    except WebSocketDisconnect:
        return False
    except RuntimeError:
        # Starlette: "Cannot call send once a close message has been sent."
        return False


async def _safe_close(websocket: WebSocket) -> None:
    try:
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close()
    except (WebSocketDisconnect, RuntimeError):
        pass


@router.get("/terminal/cli-status")
async def cli_status() -> dict[str, Any]:
    """检查 Node.js CLI Server 状态"""
    server_url = get_server_url()
    port = get_cli_port()
    if not server_url:
        return {"running": False, "port": 0, "error": "CLI Server 未启动"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{server_url}/health", timeout=3)
            data = resp.json()
            return {"running": True, "port": port, "pid": data.get("pid")}
    except Exception as e:
        return {"running": False, "port": port, "error": str(e)}


class RunCommandRequest(BaseModel):
    work_dir: str | None = None
    command: str
    timeout: int = 300


class ResetAgentTerminalRequest(BaseModel):
    work_dir: str | None = None


@router.websocket("/ws/terminal")
async def terminal_websocket(
    websocket: WebSocket,
    work_dir: str | None = None,
    session_id: str | None = None,
) -> None:
    """WebSocket 代理：前端 → Python → Node.js CLI

    前端保持现有协议不变，Python 层透明转发到 Node.js CLI 的 WebSocket。
    """
    await websocket.accept()
    server_url = get_server_url()
    if not server_url:
        await _safe_send_text(websocket, json.dumps({"type": "error", "data": "CLI Server 未启动"}))
        await _safe_close(websocket)
        return

    port = get_cli_port()
    sid = session_id or "default"
    # 关键：必须把 work_dir 也传给 Node.js CLI，否则不知道在哪个目录创建终端
    wd = work_dir or ""
    ws_url = f"ws://127.0.0.1:{port}/ws/terminal?session_id={sid}&work_dir={wd}"

    try:
        async with websockets.connect(ws_url) as cli_ws:
            # 双向转发
            async def forward_to_frontend():
                try:
                    async for msg in cli_ws:
                        if isinstance(msg, bytes):
                            msg = msg.decode("utf-8", errors="replace")
                        if not await _safe_send_text(websocket, msg):
                            break
                except WebSocketDisconnect:
                    pass
                except Exception:
                    pass

            fwd_task = asyncio.create_task(forward_to_frontend())

            try:
                while True:
                    raw = await websocket.receive_text()
                    await cli_ws.send(raw)
            except WebSocketDisconnect:
                pass
            finally:
                fwd_task.cancel()
                try:
                    await asyncio.wait_for(fwd_task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
    except asyncio.CancelledError:
        # 连接阶段或清理阶段被正常取消（页面刷新/关闭），无需报错
        pass
    except WebSocketDisconnect:
        # 客户端在 CLI 握手/转发期间已断开
        pass
    except Exception as e:
        await _safe_send_text(
            websocket,
            json.dumps({"type": "error", "data": f"CLI 连接失败: {e}"}),
        )


@router.post("/terminal/reset-agent")
async def reset_agent_terminal(req: ResetAgentTerminalRequest) -> dict[str, Any]:
    """重置 agent 终端"""
    import httpx
    server_url = get_server_url()
    if server_url:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(f"{server_url}/reset-agent", json={"work_dir": req.work_dir})
        except Exception:
            pass
    return {"status": "ok"}


@router.post("/terminal/run")
async def run_command(req: RunCommandRequest) -> dict[str, Any]:
    """运行命令（前端手动执行）"""
    executor = CLIExecutor(work_dir=req.work_dir)
    result = executor.execute(
        command=req.command,
        working_dir=req.work_dir,
        timeout=req.timeout,
    )
    return result


@router.get("/terminal/session/{invocation_id}")
async def get_terminal_session(invocation_id: str) -> dict[str, Any]:
    """通过 invocation_id 查找对应的终端 session_id。

    优先查 Python 端内存表（自身 register_invocation_session 注册的），
    再 fallback 到 CLI server 的 invocationToSession 映射。
    """
    # 1) Python 端映射（精确匹配）
    try:
        from services.terminal_manager import TerminalManager
        resolved = TerminalManager.resolve_invocation_session(invocation_id)
        if resolved:
            return {"session_id": resolved}
    except Exception:
        pass

    # 2) Fallback：尝试 CLI server 自身的 mapping
    server_url = get_server_url()
    if server_url:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{server_url}/sessions/{invocation_id}", timeout=3)
                data = resp.json()
                if data.get("session_id"):
                    return data
        except Exception:
            pass

    return {"session_id": None}


@router.post("/terminal/session/{session_id}/close")
async def close_terminal_session(session_id: str) -> dict[str, Any]:
    """关闭指定终端会话"""
    server_url = get_server_url()
    if server_url:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(f"{server_url}/sessions/{session_id}")
                return resp.json()
        except Exception:
            pass
    return {"status": "ok", "closed": False}


@router.post("/terminal/{invocation_id}/background")
async def background_command(invocation_id: str) -> dict[str, Any]:
    """将命令转入后台运行（手动 detach）。

    通知 Python 执行层和 Node.js CLI 让正在执行的命令立即返回 auto_detached=true，
    命令本身继续在终端中运行，AI 拿到"已转入后台"的结果继续工作。
    """
    # 先通知 Python CLIExecutor 的异步执行层
    try:
        from utils.cli_executor import CLIExecutor
        CLIExecutor.signal_detach(invocation_id)
    except Exception:
        pass

    server_url = get_server_url()
    if not server_url:
        return {"status": "ok", "detached": True, "note": "已通知执行层"}

    try:
        async with httpx.AsyncClient() as client:
            # 先尝试用 invocation_id 直接 detach（Node.js 会同时尝试作为 session_id 和 invocation_id）
            resp = await client.post(
                f"{server_url}/sessions/{invocation_id}/detach",
                timeout=5,
            )
            data = resp.json()
            if data.get("detached"):
                return {"status": "ok", "detached": True}

            # 如果失败，尝试通过 /sessions/{invocation_id} 查 session_id
            resp2 = await client.get(f"{server_url}/sessions/{invocation_id}", timeout=3)
            sess_data = resp2.json()
            session_id = sess_data.get("session_id")
            if session_id and session_id != invocation_id:
                resp3 = await client.post(
                    f"{server_url}/sessions/{session_id}/detach",
                    timeout=5,
                )
                data3 = resp3.json()
                return {"status": "ok", "detached": data3.get("detached", False)}

            return {"status": "ok", "detached": False}
    except Exception as e:
        return {"status": "error", "detached": False, "error": str(e)}


@router.post("/terminal/{invocation_id}/stop")
async def stop_command(invocation_id: str) -> dict[str, Any]:
    """终止命令（彻底杀掉 dev server 等长运行进程）。

    关键：不能只发 Ctrl+C（interrupt），那只能让 vite 优雅关闭，
    npm 进程和 vite worker 还会继续占端口。必须用 taskkill /T /F 杀进程树。
    """
    # 1) 先通知 Python CLIExecutor 的异步执行层（如果在执行中，让 await 立即返回）
    try:
        from utils.cli_executor import CLIExecutor
        CLIExecutor.signal_cancel(invocation_id)
    except Exception:
        pass

    # 2) 解析 invocation_id → session_id（先查 Python 端映射，再查 CLI server）
    session_id = ""
    try:
        from services.terminal_manager import TerminalManager
        session_id = TerminalManager.resolve_invocation_session(invocation_id) or ""
    except Exception:
        pass
    if not session_id:
        server_url = get_server_url()
        if server_url:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{server_url}/sessions/{invocation_id}", timeout=3)
                    data = resp.json()
                    session_id = data.get("session_id") or ""
            except Exception:
                pass

    # 3) 关闭 session（Node.js 端 closeSession 用 taskkill /T /F 杀进程树）
    server_url = get_server_url()
    if server_url and session_id:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(f"{server_url}/sessions/{session_id}")
                return resp.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # 4) 兜底：仅发 Ctrl+C interrupt（杀不干净但至少打断当前命令）
    if server_url:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{server_url}/sessions/{invocation_id}/interrupt")
                return resp.json()
        except Exception:
            pass
    return {"status": "ok"}