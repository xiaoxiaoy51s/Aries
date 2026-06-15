"""平台消息分段推送（思考 / 工具状态 / 回复内容）。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Optional

from services.platform_push import _split_text

SendFn = Callable[[str], Awaitable[None]]


class PlatformStreamSink:
    """将 agent 流式事件格式化为平台消息并分段发送。"""

    def __init__(self, send_fn: SendFn, *, max_len: int = 2000):
        self._send_fn = send_fn
        self._max_len = max_len

    async def _send(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        for seg in _split_text(text, self._max_len):
            await self._send_fn(seg)

    async def on_reasoning(self, text: str) -> None:
        await self._send(f"【思考】\n{text.strip()}")

    async def on_assistant(self, text: str) -> None:
        await self._send(text.strip())

    async def on_tool_start(self, tool_name: str) -> None:
        name = (tool_name or "tool").strip()
        await self._send(f"🔧 {name} 执行中…")

    async def on_tool_done(self, tool_name: str, status: str, output: str = "") -> None:
        name = (tool_name or "tool").strip()
        ok = status == "completed"
        msg = f"{'✅' if ok else '❌'} {name} {'完成' if ok else '失败'}"
        preview = (output or "").strip()
        if preview and not ok:
            if len(preview) > 300:
                preview = preview[:300] + "…"
            msg = f"{msg}\n{preview}"
        await self._send(msg)


async def emit_logger_segments(
    sink: Optional[PlatformStreamSink],
    *,
    reasoning: str = "",
    assistant: str = "",
) -> None:
    if not sink:
        return
    if reasoning:
        await sink.on_reasoning(reasoning)
    if assistant:
        await sink.on_assistant(assistant)
