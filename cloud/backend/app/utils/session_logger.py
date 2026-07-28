"""SessionLogger: 将每条消息以 JSONL 格式写入文件。

文件路径：~/.Aries/{user_email}/session/{YYYY-MM-DD}/{session_id}_{message_id}.jsonl

事件类型：
  - user_message   : 用户消息（含 text + image_url 列表）
  - reasoning_text : 思考过程（token 级广播，段落结束写盘）
  - assistant_text : 回复内容（token 级广播，段落结束写盘）
  - tool_call      : 工具调用开始（后续实现）
  - tool_result    : 工具调用结果（后续实现）
  - finalized      : 日志结束标记
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Callable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_jsonl_path(user_email: str, session_id: str, message_id: int | str) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    base = Path.home() / ".Aries" / user_email / "session" / today
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{session_id}_{message_id}.jsonl"


class SessionLogger:
    """单条消息的 JSONL 日志管理器

    token 级写入（reasoning_delta / assistant_content）只累积到内存 + SSE 广播，
    不写盘；在段落结束或 finalize 时一次性写入完整文本。
    结构性事件（tool_call / tool_result / finalized 等）立即写盘。
    """

    def __init__(
        self,
        user_email: str,
        session_id: str,
        message_id: int | str,
        on_event: Optional[Callable[[dict[str, Any]], None]] = None,
    ):
        self.path = _get_jsonl_path(user_email, session_id, message_id)
        self._session_id = session_id
        self._message_id = message_id
        self._on_event = on_event
        self._reasoning_all = ""
        self._reasoning_pending = ""
        self._assistant_all = ""
        self._assistant_pending = ""
        self._model = ""
        self._token_usage: dict[str, Any] = {}
        self._finalized = False
        self._file = open(self.path, "a", encoding="utf-8")

    def _write_event(self, event: dict[str, Any]) -> None:
        if self._file.closed:
            return
        line = json.dumps(event, ensure_ascii=False)
        self._file.write(line + "\n")
        self._file.flush()

    def _emit(self, event: dict[str, Any]) -> None:
        if self._on_event:
            try:
                self._on_event(event)
            except Exception:
                pass

    # ============ 用户消息 ============

    def write_user_message(self, text: str, image_urls: list[str] | None = None) -> None:
        event: dict[str, Any] = {
            "type": "user_message",
            "text": text,
            "image_urls": image_urls or [],
            "timestamp": _utc_now(),
        }
        self._write_event(event)
        self._emit(event)

    # ============ reasoning ============

    def append_reasoning_delta(self, text: str) -> None:
        """reasoning token 累积到内存 + SSE 广播，不写盘"""
        if not text:
            return
        self._reasoning_all += text
        self._reasoning_pending += text
        event = {
            "type": "reasoning_text",
            "text": text,
            "timestamp": _utc_now(),
        }
        self._emit(event)

    def flush_reasoning_segment(self) -> str:
        """将累积的 reasoning 一次性写入 JSONL"""
        if self._reasoning_pending:
            self._write_event({
                "type": "reasoning_text",
                "text": self._reasoning_pending,
                "timestamp": _utc_now(),
            })
            self._reasoning_pending = ""
        return self._reasoning_all

    # ============ assistant content ============

    def record_assistant_content(self, text: str) -> None:
        """assistant token 累积到内存 + SSE 广播，不写盘"""
        if not text:
            return
        self._assistant_all += text
        self._assistant_pending += text
        event = {
            "type": "assistant_text",
            "text": text,
            "timestamp": _utc_now(),
        }
        self._emit(event)

    def flush_assistant_segment(self) -> str:
        """将累积的 assistant text 一次性写入 JSONL"""
        self.flush_reasoning_segment()
        if self._assistant_pending:
            self._write_event({
                "type": "assistant_text",
                "text": self._assistant_pending,
                "timestamp": _utc_now(),
            })
            self._assistant_pending = ""
        return self._assistant_all

    # ============ tool 调用 ============

    def write_tool_call(self, tool_call_id: str, tool_name: str, args: dict) -> None:
        """记录工具调用开始"""
        self.flush_assistant_segment()
        event = {
            "type": "tool_call",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "args": args,
            "timestamp": _utc_now(),
        }
        self._write_event(event)
        self._emit(event)

    def write_tool_result(self, tool_call_id: str, tool_name: str, result: str, error: str = "") -> None:
        """记录工具调用结果"""
        # 截断过长的结果
        if len(result) > 100_000:
            result = result[:100_000] + "\n...(结果已截断)"
        event = {
            "type": "tool_result",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "result": result,
            "error": error,
            "timestamp": _utc_now(),
        }
        self._write_event(event)
        self._emit(event)

    # ============ token 使用 ============

    def set_model(self, model: str) -> None:
        self._model = model or ""

    def set_token_usage(self, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        self._token_usage.update(usage)

    def add_token_usage(self, usage: dict[str, Any] | None) -> None:
        """从 API 响应中累加 token 使用量"""
        if not usage:
            return
        api_usage = self._token_usage.setdefault("api_usage", {})
        # prompt_tokens 代表上下文大小，多轮中取最后一次值（覆盖）
        for key in ("prompt_tokens", "cached_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            val = int(usage.get(key) or 0)
            if val:
                api_usage[key] = val
        # completion_tokens 是每轮生成量，累加
        for key in ("completion_tokens", "reasoning_tokens"):
            val = int(usage.get(key) or 0)
            if val:
                api_usage[key] = int(api_usage.get(key, 0)) + val
        if any(usage.get(k) for k in ("prompt_tokens", "completion_tokens", "reasoning_tokens")):
            api_usage["total_tokens"] = int(api_usage.get("prompt_tokens", 0)) + int(api_usage.get("completion_tokens", 0))
            api_usage["from_api"] = True

    def write_token_usage(self) -> None:
        """将 token 使用信息写入 JSONL"""
        if self._token_usage:
            event = {
                "type": "token_usage",
                "model": self._model,
                "token_usage": self._token_usage,
                "timestamp": _utc_now(),
            }
            self._write_event(event)
            self._emit(event)

    # ============ finalize ============

    def finalize(self, duration_ms: int | None = None) -> None:
        if self._finalized:
            return
        self.flush_reasoning_segment()
        self.flush_assistant_segment()
        self.write_token_usage()
        event: dict[str, Any] = {
            "type": "finalized",
            "timestamp": _utc_now(),
        }
        if duration_ms is not None:
            event["duration_ms"] = duration_ms
        self._write_event(event)
        self._emit(event)
        try:
            self._file.close()
        except Exception:
            pass
        self._finalized = True

    @property
    def jsonl_path_str(self) -> str:
        return str(self.path)

    def __del__(self):
        if not self._finalized:
            try:
                self._file.close()
            except Exception:
                pass


def read_jsonl_events(log_path: str) -> list[dict[str, Any]]:
    """读取 JSONL 文件，返回事件列表"""
    path = Path(log_path)
    if not path.exists():
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def reconstruct_from_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """从事件列表重建消息内容"""
    result = {
        "user_content": "",
        "image_urls": [],
        "reasoning_content": "",
        "assistant_content": "",
        "tool_calls": [],
        "token_usage": {},
        "model": "",
        "duration_ms": 0,
    }
    for ev in events:
        ev_type = ev.get("type")
        if ev_type == "user_message":
            result["user_content"] = ev.get("text", "")
            result["image_urls"] = ev.get("image_urls", [])
        elif ev_type == "reasoning_text":
            result["reasoning_content"] += ev.get("text", "")
        elif ev_type == "assistant_text":
            result["assistant_content"] += ev.get("text", "")
        elif ev_type == "tool_call":
            result["tool_calls"].append(ev)
        elif ev_type == "tool_result":
            result["tool_calls"].append(ev)
        elif ev_type == "token_usage":
            result["token_usage"] = ev.get("token_usage", {})
            result["model"] = ev.get("model", "")
        elif ev_type == "finalized":
            result["duration_ms"] = ev.get("duration_ms", 0)
    return result
