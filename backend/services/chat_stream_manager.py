"""聊天流管理器"""
import asyncio

_streams: dict[str, asyncio.Event] = {}


def register(session_id: str, cancel_event: asyncio.Event | None = None) -> asyncio.Event:
    """注册一个会话的 cancel_event，若未传入则自动创建。返回 cancel_event。"""
    if cancel_event is None:
        cancel_event = asyncio.Event()
    _streams[session_id] = cancel_event
    return cancel_event


def unregister(session_id: str):
    _streams.pop(session_id, None)


def request_cancel(session_id: str) -> bool:
    cancel_event = _streams.get(session_id)
    if cancel_event:
        cancel_event.set()
        return True
    return False
