"""后台 Agent 任务管理

流式输出已切换为 SSE 直接推送：
  - stream_chat_sse() 在 chat.py 中直接返回 StreamingResponse
  - 实时数据通过 stream_agent_mode() 的 yield 以 SSE 事件流推送
  - JSONL 日志仍写入磁盘，供断线恢复和历史记录使用
  - 此处保留旧的后台任务管理（stream_chat_with_background），供非流式兼容使用
"""
import asyncio
import logging

from services.chat_stream_manager import (
    register as register_chat_stream,
    unregister as unregister_chat_stream,
    register_bg_session,
    mark_bg_done,
    is_bg_running,
    cleanup_bg_session,
)

from api.engine import stream_agent_mode

_log = logging.getLogger(__name__)

# 后台 agent 任务追踪：防止被 GC 回收
_background_tasks: set[asyncio.Task] = set()


async def stream_chat_with_background(
    request,
    messages: list,
    headers: dict,
    payload: dict,
    session_id: str,
    work_dir,
    cancel_event,
    agent_mode: str | None = None,
    override_model: str | None = None,
    override_system_prompt: str | None = None,
    override_tools: list | None = None,
    override_agent_mode_label: str | None = None,
) -> None:
    """启动后台 agent 任务（旧版，SSE 路径改用 stream_chat_sse）。

    调用方应在调用前完成 setup（保存 user 消息、注册 cancel_event 等）。
    本函数返回时任务仍在运行；不需要返回值。
    """
    register_bg_session(session_id)

    async def background_runner():
        try:
            async for event in stream_agent_mode(
                request,
                messages,
                headers,
                payload,
                session_id,
                work_dir=work_dir,
                cancel_event=cancel_event,
                disconnect_check=None,
                agent_mode=agent_mode,
                override_model=override_model,
                override_system_prompt=override_system_prompt,
                override_tools=override_tools,
                override_agent_mode_label=override_agent_mode_label,
            ):
                # SSE 字符串此处丢弃：所有数据已通过 SessionLogger.on_event 经 SSE 广播
                _ = event
            mark_bg_done(session_id)
        except Exception as e:
            _log.exception("background_runner error: %s", e)
            mark_bg_done(session_id)
        finally:
            unregister_chat_stream(session_id)
            # 延迟清理 bg_session
            await asyncio.sleep(30)
            cleanup_bg_session(session_id)

    task = asyncio.create_task(background_runner())
    from services.chat_stream_manager import set_bg_task
    set_bg_task(session_id, task)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def stop_chat_handler(session_id: str, work_dir: str | None = None) -> dict:
    """停止聊天并紧急终止所有关联任务（CLI、子 Agent、终端）。"""
    from services.emergency_stop import emergency_stop_session

    result = await emergency_stop_session(session_id, work_dir)
    if result.get("chat_cancelled") or result.get("invocations") or result.get("subagents"):
        return {"status": "stopping", "message": "已请求停止并终止所有进行中的任务", **result}
    return {"status": "idle", "message": "当前没有运行中的对话", **result}


async def chat_status_handler(session_id: str) -> dict:
    """检查该 session 是否有正在运行的后台任务"""
    running = is_bg_running(session_id)
    return {"running": running, "session_id": session_id}

