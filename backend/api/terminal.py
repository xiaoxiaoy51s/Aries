"""WebSocket terminal and REST helpers."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from services.terminal_manager import TerminalManager

router = APIRouter(tags=["terminal"])


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
    await websocket.accept()
    manager = TerminalManager.get_instance()
    manager.set_event_loop(asyncio.get_running_loop())
    raw_sid = (session_id or "default").strip() or "default"
    # 前端用 "__agent__" 标记想订阅 agent session，绑定到 work_dir 对应的会话
    if raw_sid == "__agent__":
        sid = manager.resolve_agent_session_id(work_dir)
    else:
        sid = raw_sid
    session, queue, callback = manager.subscribe_ws(sid, work_dir)
    attached = False

    async def pump_output() -> None:
        try:
            while True:
                data = await queue.get()
                await websocket.send_text(json.dumps({"type": "output", "data": data}, ensure_ascii=False))
        except asyncio.CancelledError:
            raise

    pump_task = asyncio.create_task(pump_output())
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                if attached:
                    session.write(raw)
                continue
            msg_type = msg.get("type", "input")
            if msg_type == "attach":
                rows = int(msg.get("rows", 30))
                cols = int(msg.get("cols", 120))
                reset = bool(msg.get("reset", True))
                replay = bool(msg.get("replay", False))
                session = manager.get_session(sid, work_dir)
                if attached:
                    session.resize(rows, cols)
                else:
                    session = manager.attach_interactive(
                        sid, work_dir, rows=rows, cols=cols, reset=reset
                    )
                    attached = True
                    if replay and not reset:
                        replay_data = session.get_replay_buffer()
                        if replay_data:
                            await websocket.send_text(
                                json.dumps({"type": "output", "data": replay_data}, ensure_ascii=False)
                            )
                await websocket.send_text(
                    json.dumps(
                        {"type": "ready", "shell": session.shell_kind},
                        ensure_ascii=False,
                    )
                )
            elif msg_type == "input":
                if not attached:
                    continue
                data = msg.get("data", "")
                session.write(data)
            elif msg_type == "resize":
                rows = int(msg.get("rows", 30))
                cols = int(msg.get("cols", 120))
                if attached:
                    session.resize(rows, cols)
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
        try:
            await pump_task
        except asyncio.CancelledError:
            pass
        manager.unsubscribe_ws(sid, queue, callback)


@router.post("/terminal/reset-agent")
async def reset_agent_terminal(req: ResetAgentTerminalRequest) -> dict[str, Any]:
    """强制清理 agent 侧遗留 PTY 会话（shared 命令已改为独立子进程）。"""
    manager = TerminalManager.get_instance()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: manager.reset_agent_session(req.work_dir))
    return {"status": "ok", "message": "agent 终端已重置"}


@router.post("/terminal/run")
async def run_command(req: RunCommandRequest) -> dict[str, Any]:
    manager = TerminalManager.get_instance()
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: manager.run_command_and_wait(
            command=req.command,
            work_dir=req.work_dir,
            timeout=req.timeout,
        ),
    )
    return result
