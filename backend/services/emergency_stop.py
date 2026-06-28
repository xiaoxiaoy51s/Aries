"""会话级紧急停止：终止 AI 流、CLI 命令、子 Agent、终端进程。"""
from __future__ import annotations

import logging
from typing import Any

import httpx

_log = logging.getLogger(__name__)


def interrupt_agent_terminal_sync(work_dir: str | None) -> bool:
    """向 agent 终端发送 Ctrl+C（等同 ConsolePanel 无选中时按 Ctrl+C）。"""
    if not work_dir:
        return False
    try:
        from services.terminal_manager import TerminalManager
        from utils.cli_executor import get_server_url

        server_url = get_server_url()
        if not server_url:
            return False
        sid = TerminalManager.get_instance().resolve_agent_session_id(work_dir)
        with httpx.Client(timeout=5) as client:
            client.post(f"{server_url}/sessions/{sid}/interrupt")
        return True
    except Exception as exc:
        _log.debug("interrupt_agent_terminal failed: %s", exc)
        return False


def _interrupt_invocation_sync(invocation_id: str) -> None:
    try:
        from utils.cli_executor import get_server_url
        from services.terminal_manager import TerminalManager

        server_url = get_server_url()
        if not server_url:
            return
        with httpx.Client(timeout=5) as client:
            client.post(f"{server_url}/sessions/{invocation_id}/interrupt")
            mapped = TerminalManager.resolve_invocation_session(invocation_id)
            if mapped and mapped != invocation_id:
                client.post(f"{server_url}/sessions/{mapped}/interrupt")
    except Exception:
        pass


def emergency_stop_session_sync(
    session_id: str,
    work_dir: str | None = None,
) -> dict[str, Any]:
    """同步紧急停止：供 ESC 热键线程、/chat/stop 等调用。"""
    from services.chat_stream_manager import request_cancel
    from utils.cli_executor import CLIExecutor
    from engine.subagent_runtime import list_running_subagents, cancel_subagent

    result: dict[str, Any] = {
        "session_id": session_id,
        "chat_cancelled": request_cancel(session_id),
        "invocations": [],
        "subagents": [],
        "terminal_interrupted": False,
    }

    for inv_id in CLIExecutor.cancel_session_invocations(session_id):
        result["invocations"].append(inv_id)
        _interrupt_invocation_sync(inv_id)

    for task_id in list(list_running_subagents()):
        if cancel_subagent(task_id):
            result["subagents"].append(task_id)

    result["terminal_interrupted"] = interrupt_agent_terminal_sync(work_dir)
    return result


async def emergency_stop_session(
    session_id: str,
    work_dir: str | None = None,
) -> dict[str, Any]:
    return emergency_stop_session_sync(session_id, work_dir)
