"""后台 Agent 任务管理

流式输出已切换为基于 JSONL 日志 + WebSocket 推送：
  - 每次写入 JSONL 后通过 SessionLogger.on_event 回调经 services.chat_ws 广播
  - 前端通过 /ws/chat?session_id=xxx 订阅；切换页面时直接读取 JSONL 文件
  - 此处只负责启动后台任务并清理 cancel_event / bg_session
"""
import asyncio
import logging

from services.chat_stream_manager import (
    register as register_chat_stream,
    unregister as unregister_chat_stream,
    request_cancel as request_chat_cancel,
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
    """启动后台 agent 任务，实时数据通过 WebSocket + JSONL 推送。

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
                # SSE 字符串此处丢弃：所有数据已通过 SessionLogger.on_event 经 WebSocket 广播
                _ = event
            mark_bg_done(session_id)
        except Exception as e:
            _log.exception("background_runner error: %s", e)
            # 错误也写入 JSONL 日志（通过当前 logger 不可用，所以仅通知前端）
            try:
                from services.chat_ws import notify_log_event
                from datetime import datetime, timezone
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(
                        notify_log_event(
                            session_id,
                            0,
                            {
                                "type": "error_event",
                                "error_type": "backend_error",
                                "error_msg": str(e),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            },
                            jsonl_path="",
                        )
                    )
            except Exception:
                pass
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


async def stop_chat_handler(session_id: str) -> dict:
    """停止聊天处理"""
    if request_chat_cancel(session_id):
        return {"status": "stopping", "message": "已请求停止生成"}
    return {"status": "idle", "message": "当前没有运行中的对话"}


async def chat_status_handler(session_id: str) -> dict:
    """检查该 session 是否有正在运行的后台任务"""
    running = is_bg_running(session_id)
    return {"running": running, "session_id": session_id}

