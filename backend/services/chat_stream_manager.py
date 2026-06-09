"""聊天流管理器 - stub"""
import asyncio
from typing import Callable


_streams: dict[str, asyncio.Event] = {}


def register(session_id: str, cancel_event: asyncio.Event):
    _streams[session_id] = cancel_event


def unregister(session_id: str):
    _streams.pop(session_id, None)


def request_cancel(session_id: str) -> bool:
    cancel_event = _streams.get(session_id)
    if cancel_event:
        cancel_event.set()
        return True
    return False
