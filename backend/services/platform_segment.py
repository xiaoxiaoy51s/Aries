"""平台消息分段推送（仅 assistant 回复内容）。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Optional

from services.platform_push import _split_text

SendFn = Callable[[str], Awaitable[None]]


class PlatformStreamSink:
    """将 agent 流式事件格式化为平台消息并分段发送。

    微信 / QQ / 飞书等平台只推送 assistant_text，不推送思考过程与工具状态。
    """

    def __init__(self, send_fn: SendFn, *, max_len: int = 2000):
        self._send_fn = send_fn
        self._max_len = max_len
        self._pushed_assistant = ""

    @property
    def pushed_any(self) -> bool:
        return bool(self._pushed_assistant)

    def unpushed_suffix(self, final: str) -> str:
        """返回 final 中尚未推送的尾部（用于兜底，避免重复发送）。"""
        final = (final or "").strip()
        pushed = self._pushed_assistant
        if not final:
            return ""
        if not pushed:
            return final
        if final.startswith(pushed):
            return final[len(pushed):].strip()
        if final.replace("\r\n", "\n") == pushed.replace("\r\n", "\n"):
            return ""
        return ""

    async def _send(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        for seg in _split_text(text, self._max_len):
            await self._send_fn(seg)

    async def on_reasoning(self, text: str) -> None:
        return

    async def on_assistant(self, text: str) -> None:
        body = (text or "").strip()
        if not body:
            return
        self._pushed_assistant += body
        for seg in _split_text(body, self._max_len):
            await self._send_fn(seg)

    async def on_tool_start(self, tool_name: str) -> None:
        return

    async def on_tool_done(self, tool_name: str, status: str, output: str = "") -> None:
        return


async def emit_logger_segments(
    sink: Optional[PlatformStreamSink],
    *,
    reasoning: str = "",
    assistant: str = "",
) -> None:
    if not sink:
        return
    if assistant:
        await sink.on_assistant(assistant)


async def push_final_reply(send_fn: SendSegmentFn, text: str) -> None:
    """Agent 完成后，将最终 assistant 回复分段推送到微信 / QQ / 飞书。"""
    body = (text or "").strip()
    if not body:
        return
    sink = PlatformStreamSink(send_fn)
    await sink.on_assistant(body)
