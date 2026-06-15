"""
SessionLogger: 将 agent 每轮工作过程以 JSONL 格式写入文件（一条逻辑事件一行）。

文件路径：~/.MIMOClaw/session/{YYYY-MM-DD}/{session_id}_{message_id}.jsonl

事件类型（按时间顺序）：
  - reasoning_text  : 一轮思考/工作说明（整段 flush，非逐 token 写盘）
  - tool_call       : 工具调用开始
  - tool_result     : 工具调用结束
  - assistant_text  : 每轮工作说明或最终回复（整段）
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SESSION_LOG_ROOT = Path.home() / ".MIMOClaw" / "session"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_jsonl_path(session_id: str, message_id: int | str) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    base = SESSION_LOG_ROOT / today
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{session_id}_{message_id}.jsonl"


def _append_event(path: Path, event: dict[str, Any]) -> None:
    line = json.dumps(event, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


class SessionLogger:
    """单次 assistant 回复的 JSONL 日志；流式阶段缓冲，在段落边界写入文件。"""

    def __init__(self, session_id: str, message_id: int | str):
        self.path = _get_jsonl_path(session_id, message_id)
        self._tool_log: list[dict[str, Any]] = []
        self._reasoning_all = ""
        self._assistant_all = ""
        self._assistant_flushed_len = 0
        self._reasoning_buffer = ""

    def append_reasoning_delta(self, text: str) -> None:
        if not text:
            return
        self._reasoning_buffer += text
        self._reasoning_all += text

    def flush_reasoning_segment(self) -> str:
        if not self._reasoning_buffer:
            return ""
        text = self._reasoning_buffer
        _append_event(self.path, {
            "type": "reasoning_text",
            "text": text,
            "timestamp": _utc_now(),
        })
        self._reasoning_buffer = ""
        return text

    def write_tool_call(
        self,
        tool_call_id: str,
        tool_name: str,
        args: dict[str, Any],
        started_at: str | None = None,
    ) -> str:
        reasoning = self.flush_reasoning_segment()
        ts = started_at or _utc_now()
        self._tool_log.append({
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": "running",
            "started_at": ts,
        })
        _append_event(self.path, {
            "type": "tool_call",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "args": args,
            "status": "running",
            "started_at": ts,
        })
        return reasoning

    def write_tool_result(
        self,
        tool_call_id: str,
        tool_name: str,
        status: str,
        result: str = "",
        error: str = "",
        ended_at: str | None = None,
    ) -> None:
        ts = ended_at or _utc_now()
        for entry in self._tool_log:
            if entry["tool_call_id"] == tool_call_id:
                entry["status"] = status
                entry["ended_at"] = ts
                break
        _append_event(self.path, {
            "type": "tool_result",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": status,
            "result": result,
            "error": error,
            "ended_at": ts,
        })

    def record_assistant_content(self, text: str) -> None:
        if text:
            self._assistant_all += text

    def flush_assistant_round(self) -> tuple[str, str]:
        """将本轮新增的 assistant 文本写入 JSONL（多轮工具调用时每轮调用一次）。"""
        reasoning = self.flush_reasoning_segment()
        new_text = self._assistant_all[self._assistant_flushed_len:]
        if not new_text:
            return reasoning, ""
        _append_event(self.path, {
            "type": "assistant_text",
            "text": new_text,
            "timestamp": _utc_now(),
        })
        self._assistant_flushed_len = len(self._assistant_all)
        return reasoning, new_text

    def write_assistant_segment(self, text: str) -> None:
        if not text:
            return
        self.flush_reasoning_segment()
        if len(self._assistant_all) < self._assistant_flushed_len + len(text):
            self._assistant_all += text
        _append_event(self.path, {
            "type": "assistant_text",
            "text": text,
            "timestamp": _utc_now(),
        })
        self._assistant_flushed_len = len(self._assistant_all)

    def finalize(self) -> None:
        self.flush_reasoning_segment()

    def _tool_summary(self) -> str:
        if not self._tool_log:
            return ""
        lines = ["\n\n---工具调用摘要---"]
        for t in self._tool_log:
            icon = "✅" if t["status"] == "completed" else "❌"
            lines.append(f"{icon} {t['tool_name']}")
        return "\n".join(lines)

    def build_db_content(self) -> str:
        return self._assistant_all

    def build_db_reasoning(self) -> str | None:
        if not self._reasoning_all and not self._tool_log:
            return None
        return self._reasoning_all + self._tool_summary()

    def jsonl_path_str(self) -> str:
        return str(self.path)


def read_jsonl_events(jsonl_path: str) -> list[dict[str, Any]]:
    path = Path(jsonl_path)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return events


def resolve_message_log_events(snapshot_field: str | None) -> list[dict[str, Any]]:
    """从 message_snapshot_json 解析事件：新格式为 JSONL 路径，旧格式为内联 snapshot JSON。"""
    if not snapshot_field or not str(snapshot_field).strip():
        return []

    raw = str(snapshot_field).strip()
    path = Path(raw)
    if path.suffix.lower() == ".jsonl" or (path.exists() and path.is_file()):
        return read_jsonl_events(raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, dict):
        return []

    events: list[dict[str, Any]] = []
    for block in parsed.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type in ("text", "summary"):
            text = block.get("text") or block.get("content") or ""
            if text:
                events.append({"type": "assistant_text", "text": text})
        elif block_type == "reasoning":
            text = block.get("text") or block.get("content") or ""
            if text:
                events.append({"type": "reasoning_text", "text": text})
        elif block_type == "tool":
            events.append({
                "type": "tool_call",
                "tool_call_id": block.get("tool_call_id", ""),
                "tool_name": block.get("tool_name") or block.get("title", ""),
                "args": block.get("args") or {},
                "status": block.get("status", "running"),
            })
            if block.get("status") in ("completed", "failed", "error"):
                events.append({
                    "type": "tool_result",
                    "tool_call_id": block.get("tool_call_id", ""),
                    "tool_name": block.get("tool_name") or block.get("title", ""),
                    "status": block.get("status"),
                    "result": block.get("result", ""),
                    "error": block.get("error", ""),
                })
    return events
