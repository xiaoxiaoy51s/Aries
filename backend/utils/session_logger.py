"""
SessionLogger: 将 agent 每轮工作过程以 JSONL 格式写入文件（一条逻辑事件一行）。

文件路径：~/.Aries/session/{YYYY-MM-DD}/{session_id}_{message_id}.jsonl

事件类型（按时间顺序）：
  - reasoning_text  : 一轮思考/工作说明（整段 flush，非逐 token 写盘）
  - tool_call       : 工具调用开始
  - tool_result     : 工具调用结束
  - assistant_text  : 每轮工作说明或最终回复（整段）
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SESSION_LOG_ROOT = Path.home() / ".Aries" / "session"
SUBAGENT_LOG_ROOT = SESSION_LOG_ROOT / "sub_agent"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_jsonl_path(session_id: str, message_id: int | str) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    base = SESSION_LOG_ROOT / today
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{session_id}_{message_id}.jsonl"


def get_subagent_jsonl_path(task_id: str) -> Path:
    """子 Agent 独立日志路径：~/.Aries/session/sub_agent/<YYYY-MM-DD>/<task_id>.jsonl"""
    today = datetime.now().strftime("%Y-%m-%d")
    base = SUBAGENT_LOG_ROOT / today
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{task_id}.jsonl"


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
        self._started_perf = time.perf_counter()
        self._model = ""
        self._token_usage: dict[str, Any] = {}
        self._metadata_written = False

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
        session_id: str = "",
        file_change: dict[str, Any] | None = None,
    ) -> None:
        ts = ended_at or _utc_now()
        for entry in self._tool_log:
            if entry["tool_call_id"] == tool_call_id:
                entry["status"] = status
                entry["ended_at"] = ts
                break
        event: dict[str, Any] = {
            "type": "tool_result",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": status,
            "result": result,
            "error": error,
            "ended_at": ts,
        }
        if session_id:
            event["session_id"] = session_id
        if file_change:
            event["file_change"] = file_change
        _append_event(self.path, event)

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

    def set_model(self, model: str) -> None:
        self._model = model or ""

    def set_token_usage(self, usage: dict[str, Any] | None) -> None:
        if usage:
            self._token_usage = usage

    def add_token_usage(self, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        api_usage = self._token_usage.setdefault("api_usage", {})
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            api_usage[key] = int(api_usage.get(key, 0) or 0) + int(usage.get(key, 0) or 0)

    def duration_ms(self) -> int:
        return int((time.perf_counter() - self._started_perf) * 1000)

    def write_run_metadata(self) -> None:
        if self._metadata_written:
            return
        self._metadata_written = True
        event = {
            "type": "run_metadata",
            "model": self._model,
            "duration_ms": self.duration_ms(),
            "token_usage": self._token_usage,
            "timestamp": _utc_now(),
        }
        _append_event(self.path, event)

    def get_run_metadata(self) -> dict[str, Any]:
        """返回当前运行元数据（不写盘），供流式推送使用。"""
        return {
            "model": self._model,
            "duration_ms": self.duration_ms(),
            "token_usage": self._token_usage,
        }

    def finalize(self) -> None:
        self.flush_reasoning_segment()
        self.write_run_metadata()

    def write_subagent_block(
        self,
        tool_call_id: str,
        subagent_name: str,
        task: str,
        status: str,
        log_path: str = "",
        final_output: str = "",
        error: str = "",
        rounds: int = 0,
        duration_ms: int = 0,
    ) -> None:
        """记录主 Agent 委派子 Agent 的事件块。

        status: running / success / failed / timeout / cancelled / stalled
        log_path: 子 Agent 独立 JSONL 文件路径（前端可点击跳转）
        """
        self.flush_reasoning_segment()
        _append_event(self.path, {
            "type": "sub_agent",
            "tool_call_id": tool_call_id,
            "subagent": subagent_name,
            "task": task,
            "status": status,
            "log_path": log_path,
            "final_output": final_output,
            "error": error,
            "rounds": rounds,
            "duration_ms": duration_ms,
            "timestamp": _utc_now(),
        })

    def write_error_event(
        self,
        error_type: str,
        error_msg: str,
        details: str = "",
    ) -> None:
        """记录错误事件（如 API 错误、超时等）。"""
        self.flush_reasoning_segment()
        _append_event(self.path, {
            "type": "error_event",
            "error_type": error_type,
            "error_msg": error_msg,
            "details": details,
            "timestamp": _utc_now(),
        })

    def write_info_event(
        self,
        info_type: str,
        info_msg: str,
        details: str = "",
    ) -> None:
        """记录信息事件（如上下文压缩、轮次提醒等），非错误。

        info_type 示例：
        - context_compacted: 上下文已压缩
        - step_reminder: 工具调用即将达到上限提醒
        - repeat_detected: 检测到重复工具调用
        """
        _append_event(self.path, {
            "type": "info_event",
            "info_type": info_type,
            "info_msg": info_msg,
            "details": details,
            "timestamp": _utc_now(),
        })

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
