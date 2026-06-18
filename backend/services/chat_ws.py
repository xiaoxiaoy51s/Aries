"""Chat WebSocket 广播管理器。

前端连接 /ws/chat 后，当平台消息（飞书/QQ/微信）到达或 AI 回复完成时，
后端通过 WebSocket 实时推送通知，前端收到后自动加载新消息。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

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
