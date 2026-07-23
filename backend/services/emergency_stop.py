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
            resp = client.post(f"{server_url}/sessions/{sid}/interrupt")
        _log.info("中断 agent 终端 %s: 状态=%d", sid, resp.status_code if 'resp' in dir() else -1)
        return True
    except Exception as exc:
        _log.warning("中断 agent 终端失败: %s", exc)
        return False


def _interrupt_invocation_sync(invocation_id: str) -> None:
    try:
        from utils.cli_executor import get_server_url
        from services.terminal_manager import TerminalManager

        server_url = get_server_url()
        if not server_url:
            return
        with httpx.Client(timeout=5) as client:
            resp = client.post(f"{server_url}/sessions/{invocation_id}/interrupt")
            mapped = TerminalManager.resolve_invocation_session(invocation_id)
            if mapped and mapped != invocation_id:
                resp2 = client.post(f"{server_url}/sessions/{mapped}/interrupt")
                _log.info("中断调用 %s(映射 %s): 状态=%d/%d", invocation_id, mapped, resp.status_code, resp2.status_code)
            else:
                _log.info("中断调用 %s: 状态=%d", invocation_id, resp.status_code)
    except Exception as exc:
        _log.warning("中断调用 %s 失败: %s", invocation_id, exc)


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
        "chat_cancelled": False,
        "invocations": [],
        "subagents": [],
        "terminal_interrupted": False,
        "computer_use_released": False,
    }

    result["chat_cancelled"] = request_cancel(session_id)

    inv_ids = CLIExecutor.cancel_session_invocations(session_id)
    for inv_id in inv_ids:
        result["invocations"].append(inv_id)
        _interrupt_invocation_sync(inv_id)

    for task_id in list(list_running_subagents()):
        if cancel_subagent(task_id):
            result["subagents"].append(task_id)

    result["terminal_interrupted"] = interrupt_agent_terminal_sync(work_dir)

    # 立即停止 codex-computer-use 屏幕控制层，不必等 stream finally
    from utils.computer_use_lifecycle import release_computer_use_client, stop_computer_use_esc_listener
    stop_computer_use_esc_listener()
    result["computer_use_released"] = release_computer_use_client()

    _log.info(
        "紧急停止 会话=%s chat=%s invocations=%d subagents=%d terminal=%s computer_use=%s",
        session_id,
        result["chat_cancelled"],
        len(result["invocations"]),
        len(result["subagents"]),
        result["terminal_interrupted"],
        result["computer_use_released"],
    )

    return result


async def emergency_stop_session(
    session_id: str,
    work_dir: str | None = None,
) -> dict[str, Any]:
    return emergency_stop_session_sync(session_id, work_dir)
