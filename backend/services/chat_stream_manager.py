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
        # 注意：用户点 Stop 时不再调用 _cancel_cli_invocations()。
        # 控制台会话（PTY / ps1 调度进程）保持运行，方便回放。
        # 软件关闭时的兜底清理由 backend/main.py 的 lifespan 处理。
        return True
    return False
