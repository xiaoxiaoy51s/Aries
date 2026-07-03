"""Chat WebSocket 广播管理器。

前端连接 /ws/chat 后，当平台消息（飞书/QQ/微信）到达或 AI 回复完成时，
后端通过 WebSocket 实时推送通知，前端收到后自动加载新消息。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from fastapi import WebSocket

_log = logging.getLogger(__name__)


class _Connection:
    """单个 WebSocket 连接，用独立队列串行化发送，避免并发写入导致 assert 错误。"""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.sender_task: asyncio.Task | None = None

    async def _sender_loop(self) -> None:
        """串行从队列取消息并发送，避免并发 write。"""
        try:
            while True:
                msg = await self.queue.get()
                if msg is None:
                    break
                await self.ws.send_text(msg)
        except Exception as e:
            _log.debug("[ChatWS] sender 退出: %s", e)

    def start(self) -> None:
        self.sender_task = asyncio.create_task(self._sender_loop())

    async def stop(self) -> None:
        await self.queue.put(None)
        if self.sender_task and not self.sender_task.done():
            try:
                await asyncio.wait_for(self.sender_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self.sender_task.cancel()

    def send(self, msg: str) -> None:
        """非阻塞地把消息放入队列。"""
        try:
            self.queue.put_nowait(msg)
        except asyncio.QueueFull:
            pass  # 队列满时丢弃，避免阻塞


class ChatWSManager:
    """管理所有前端的 chat WebSocket 连接，支持按 session_id 广播。"""

    def __init__(self) -> None:
        # session_id -> set[_Connection]
        self._connections: dict[str, set[_Connection]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        conn = _Connection(websocket)
        conn.start()
        async with self._lock:
            if session_id not in self._connections:
                self._connections[session_id] = set()
            self._connections[session_id].add(conn)
        _log.info("[ChatWS] 前端连接 session=%s, 当前连接数=%d", session_id, len(self._connections.get(session_id, set())))

    async def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        async with self._lock:
            conns = self._connections.get(session_id)
            if not conns:
                return
            # 找到对应的 _Connection
            target: _Connection | None = None
            for c in conns:
                if c.ws is websocket or c.ws == websocket:
                    target = c
                    break
            if target:
                conns.discard(target)
                if not conns:
                    del self._connections[session_id]
        if target:
            await target.stop()

    async def broadcast(self, session_id: str, event: dict[str, Any]) -> None:
        """向指定 session 的所有前端连接推送事件（通过队列串行发送）。"""
        conns = self._connections.get(session_id, set()).copy()
        if not conns:
            return
        msg = json.dumps(event, ensure_ascii=False)
        dead: list[_Connection] = []
        for conn in conns:
            try:
                conn.send(msg)
            except Exception:
                dead.append(conn)
        if dead:
            async with self._lock:
                conns_set = self._connections.get(session_id)
                if conns_set:
                    for c in dead:
                        conns_set.discard(c)
                    if not conns_set:
                        del self._connections[session_id]


# 全局单例
_manager = ChatWSManager()


def get_chat_ws_manager() -> ChatWSManager:
    return _manager


async def notify_new_message(session_id: str, role: str, content_preview: str = "") -> None:
    """通知前端有新消息到达。"""
    await _manager.broadcast(session_id, {
        "type": "new_message",
        "session_id": session_id,
        "role": role,
        "preview": content_preview[:100],
    })


async def notify_session_update(session_id: str) -> None:
    """通知前端 session 有更新（消息处理完成等）。"""
    await _manager.broadcast(session_id, {
        "type": "session_update",
        "session_id": session_id,
    })


async def broadcast_stream_event(session_id: str, event_data: dict[str, Any]) -> None:
    """向指定 session 的前端连接推送一个流式事件（思考/工具/回复内容等）。"""
    await _manager.broadcast(session_id, {
        "type": "stream_event",
        "session_id": session_id,
        "event": event_data,
    })


async def notify_log_event(
    session_id: str,
    message_id: int | str,
    event: dict[str, Any],
    jsonl_path: str = "",
) -> None:
    """广播一个 JSONL 日志事件给前端。

    每当 SessionLogger 写入一个事件到 JSONL 文件时调用。
    前端收到后将事件应用到 UI（与原来的 SSE 事件处理路径一致）。
    jsonl_path 用于前端断线重连时回放/校验。
    """
    await _manager.broadcast(session_id, {
        "type": "log_event",
        "session_id": session_id,
        "message_id": message_id,
        "event": event,
        "jsonl_path": jsonl_path,
    })


def _schedule_ws_coro(coro: "Any") -> None:
    """从同步 on_event 回调调度异步 WS 广播（须在 running loop 的协程栈内调用）。"""
    try:
        asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        pass


def schedule_log_event_broadcast(
    session_id: str,
    message_id: int | str,
    jsonl_path: str = "",
) -> "Callable[[dict[str, Any]], None]":
    """返回一个同步回调，调用时通过 create_task 调度异步广播。

    用法（典型场景：在同步的 SessionLogger 中作为 on_event 传入）：
        logger = SessionLogger(sid, mid, on_event=schedule_log_event_broadcast(sid, mid, path))
    """
    def _on_event(event: dict[str, Any]) -> None:
        _schedule_ws_coro(
            notify_log_event(session_id, message_id, event, jsonl_path)
        )

    return _on_event


async def notify_log_started(
    session_id: str,
    message_id: int | str,
    jsonl_path: str = "",
) -> None:
    """通知前端：assistant 回复开始（用于前端创建/定位 placeholder 消息）。"""
    await _manager.broadcast(session_id, {
        "type": "log_started",
        "session_id": session_id,
        "message_id": message_id,
        "jsonl_path": jsonl_path,
    })


async def notify_log_complete(
    session_id: str,
    message_id: int | str,
    jsonl_path: str = "",
) -> None:
    """通知前端：assistant 回复结束（用于前端停止 loading 状态）。"""
    await _manager.broadcast(session_id, {
        "type": "log_complete",
        "session_id": session_id,
        "message_id": message_id,
        "jsonl_path": jsonl_path,
    })


async def notify_subagent_log_started(
    session_id: str,
    task_id: str,
    tool_call_id: str,
    jsonl_path: str,
    subagent: str = "",
) -> None:
    """子 Agent JSONL 日志开始：前端绑定 delegate 工具块并准备接收 log_event。"""
    await _manager.broadcast(session_id, {
        "type": "subagent_log_started",
        "session_id": session_id,
        "task_id": task_id,
        "tool_call_id": tool_call_id,
        "jsonl_path": jsonl_path,
        "subagent": subagent,
    })


async def notify_subagent_log_event(
    session_id: str,
    task_id: str,
    jsonl_path: str,
    event: dict[str, Any],
    tool_call_id: str = "",
) -> None:
    """子 Agent JSONL 每写入一行即推送（与主 Agent log_event 机制一致）。"""
    await _manager.broadcast(session_id, {
        "type": "subagent_log_event",
        "session_id": session_id,
        "task_id": task_id,
        "tool_call_id": tool_call_id,
        "jsonl_path": jsonl_path,
        "event": event,
    })


async def notify_subagent_log_complete(
    session_id: str,
    task_id: str,
    jsonl_path: str,
    tool_call_id: str = "",
) -> None:
    """子 Agent JSONL 日志结束。"""
    await _manager.broadcast(session_id, {
        "type": "subagent_log_complete",
        "session_id": session_id,
        "task_id": task_id,
        "tool_call_id": tool_call_id,
        "jsonl_path": jsonl_path,
    })


def schedule_subagent_log_event_broadcast(
    session_id: str,
    task_id: str,
    jsonl_path: str,
    tool_call_id: str = "",
) -> "Callable[[dict[str, Any]], None]":
    """子 Agent SessionLogger.on_event 回调：每写一行 JSONL 即 WebSocket 推送。"""

    def _on_event(event: dict[str, Any]) -> None:
        _schedule_ws_coro(
            notify_subagent_log_event(
                session_id, task_id, jsonl_path, event, tool_call_id
            )
        )

    return _on_event
