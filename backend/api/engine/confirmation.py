"""工具调用确认流程：危险命令的用户确认等待与解析。"""
import asyncio
from typing import Optional

CONFIRMATION_TIMEOUT_SECONDS = 120.0

_pending_confirmations: dict[str, asyncio.Event] = {}
_pending_confirmation_results: dict[str, bool] = {}


def register_confirmation_wait(tool_call_id: str) -> asyncio.Event:
    event = asyncio.Event()
    _pending_confirmations[tool_call_id] = event
    return event


def resolve_confirmation(tool_call_id: str, confirmed: bool) -> bool:
    tid = str(tool_call_id or "").strip()
    if not tid:
        return False
    event = _pending_confirmations.get(tid)
    if event is None:
        return False
    _pending_confirmation_results[tid] = confirmed
    event.set()
    return True


async def wait_for_confirmation(tool_call_id: str, timeout: float = 600.0) -> bool:
    event = _pending_confirmations.get(tool_call_id)
    if not event:
        return False
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        _pending_confirmations.pop(tool_call_id, None)
        _pending_confirmation_results.pop(tool_call_id, None)
        return False
    return _pending_confirmation_results.pop(tool_call_id, False)


async def wait_for_confirmation_with_cancel(
    tool_call_id: str,
    cancel_event: Optional[asyncio.Event] = None,
    timeout: float = 600.0,
) -> bool:
    """Wait for user tool confirmation, but abort if the chat stream is cancelled."""
    event = _pending_confirmations.get(tool_call_id)
    if not event:
        return False

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while loop.time() < deadline:
        if cancel_event and cancel_event.is_set():
            resolve_confirmation(tool_call_id, False)
            return False
        if tool_call_id in _pending_confirmation_results:
            confirmed = _pending_confirmation_results.pop(tool_call_id, False)
            _pending_confirmations.pop(tool_call_id, None)
            return confirmed
        if event.is_set():
            _pending_confirmations.pop(tool_call_id, None)
            return _pending_confirmation_results.pop(tool_call_id, False)
        try:
            await asyncio.wait_for(event.wait(), timeout=min(0.2, deadline - loop.time()))
        except asyncio.TimeoutError:
            continue

    _pending_confirmations.pop(tool_call_id, None)
    _pending_confirmation_results.pop(tool_call_id, None)
    return False
