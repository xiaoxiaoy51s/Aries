"""后台 Agent 任务管理"""
import asyncio
import json
from typing import AsyncGenerator

from fastapi import Request
from fastapi.responses import StreamingResponse

from services.chat_stream_manager import (
    register as register_chat_stream,
    unregister as unregister_chat_stream,
    request_cancel as request_chat_cancel,
    register_bg_session,
    get_bg_queue,
    get_bg_history,
    has_bg_event_file,
    append_bg_history,
    set_bg_task,
    mark_bg_done,
    is_bg_running,
    cleanup_bg_session,
)

from api.engine import stream_agent_mode

# 后台 agent 任务追踪：SSE 断开后任务继续运行，避免被 GC 回收
_background_tasks: set[asyncio.Task] = set()


async def stream_chat_with_background(
    request,
    messages: list,
    headers: dict,
    payload: dict,
    session_id: str,
    work_dir,
    cancel_event,
    http_request: Request,
) -> AsyncGenerator[str, None]:
    """带后台任务管理的流式聊天"""
    bg_queue = register_bg_session(session_id)
    consumer_alive = True

    async def background_runner():
        nonlocal consumer_alive
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
            ):
                await bg_queue.put(event)
                append_bg_history(session_id, event)
            mark_bg_done(session_id)
        except Exception as e:
            print(f"[background_runner] error: {e}")
            error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
            error_event = f"data: {error_data}\n\n"
            await bg_queue.put(error_event)
            append_bg_history(session_id, error_event)
            mark_bg_done(session_id)
        finally:
            unregister_chat_stream(session_id)
            # 延迟清理 bg_session，给 resume 端点时间读取 sentinel
            await asyncio.sleep(30)
            cleanup_bg_session(session_id)

    task = asyncio.create_task(background_runner())
    set_bg_task(session_id, task)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    try:
        # 仅下发轻量摘要，避免把消息分组泄露到前端 SSE
        _ctx_info = payload.get("context_token_info") or {}
        _ctx_summary = {
            "estimated_tokens": _ctx_info.get("estimated_tokens"),
            "context_window": _ctx_info.get("context_window"),
            "usage_percent": _ctx_info.get("usage_percent"),
        }
        yield f"data: {json.dumps({'context_token_usage': _ctx_summary}, ensure_ascii=False)}\n\n"

        while True:
            if await http_request.is_disconnected():
                consumer_alive = False
                break
            try:
                event = await asyncio.wait_for(bg_queue.get(), timeout=1.0)
                if event is None:
                    break
                yield event
            except asyncio.TimeoutError:
                continue
    finally:
        consumer_alive = False
        # 不取消后台任务，不反注册 stream（background_runner 的 finally 会处理）


async def stop_chat_handler(session_id: str) -> dict:
    """停止聊天处理"""
    if request_chat_cancel(session_id):
        return {"status": "stopping", "message": "已请求停止生成"}
    return {"status": "idle", "message": "当前没有运行中的对话"}


async def chat_status_handler(session_id: str) -> dict:
    """检查该 session 是否有正在运行的后台任务"""
    running = is_bg_running(session_id)
    return {"running": running, "session_id": session_id}


async def empty_stream():
    """空流"""
    yield 'data: {"resumed": false}\n\n'


async def resume_stream(session_id: str, bg_queue: asyncio.Queue, http_request: Request):
    """从 session queue 中读取剩余事件并推送给前端。先重播历史事件，再读取新事件。"""
    try:
        # 1. 先一次性推送所有已累计的历史事件（避免前端逐条闪动）
        history = get_bg_history(session_id)
        if history:
            for event in history:
                yield event
        # 2. 继续从 queue 读取新事件
        while True:
            if await http_request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(bg_queue.get(), timeout=1.0)
                if event is None:
                    yield 'data: {"resumed_done": true}\n\n'
                    break
                yield event
            except asyncio.TimeoutError:
                if not is_bg_running(session_id):
                    while not bg_queue.empty():
                        event = bg_queue.get_nowait()
                        if event is None:
                            break
                        yield event
                    yield 'data: {"resumed_done": true}\n\n'
                    break
    finally:
        pass


async def resume_chat_handler(session_id: str, http_request: Request):
    """前端切回对话时恢复 SSE 流"""
    bg_queue = get_bg_queue(session_id)
    if bg_queue is None:
        # 内存中无活跃后台 session，但可能有事件文件残留
        # （浏览器关闭后重新打开、或 task 刚结束文件尚未清理）
        if has_bg_event_file(session_id):
            return StreamingResponse(
                _file_resume_stream(session_id),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )
        # 没有后台任务，返回空流
        return StreamingResponse(
            empty_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    return StreamingResponse(
        resume_stream(session_id, bg_queue, http_request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


async def _file_resume_stream(session_id: str):
    """仅从文件恢复事件（内存队列已丢失时兜底）。"""
    history = get_bg_history(session_id)
    if history:
        for event in history:
            yield event
    yield 'data: {"resumed_done": true}\n\n'