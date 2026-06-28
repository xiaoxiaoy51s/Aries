"""
SessionLogger: 将 agent 每轮工作过程以 JSONL 格式写入文件（一条逻辑事件一行）。

文件路径：~/.Aries/session/{YYYY-MM-DD}/{session_id}_{message_id}.jsonl

事件类型（按时间顺序）：
  - reasoning_text  : 一轮思考/工作说明（整段 flush，非逐 token 写盘）
  - tool_call       : 工具调用开始
  - tool_result     : 工具调用结束
  - assistant_text  : 每轮工作说明或最终回复（整段）

设计要点：
  - 每个 token 通过 record_assistant_content 立即写入 JSONL，无缓冲
  - 写入后通过 on_event 回调广播给前端（WebSocket）
  - JSONL 文件是唯一数据源：前端通过重读文件恢复内容
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

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
    """单次 assistant 回复的 JSONL 日志；流式阶段实时写入文件，每个 token 立即落盘。"""

    def __init__(
        self,
        session_id: str,
        message_id: int | str,
        on_event: Optional[Callable[[dict[str, Any]], None]] = None,
    ):
        """
        Args:
            session_id: 会话 ID
            message_id: 消息 ID
            on_event: 每次写入事件后的回调（参数为事件 dict），
                      用于通过 WebSocket 实时推送给前端。
        """
        self.path = _get_jsonl_path(session_id, message_id)
        self._session_id = session_id
        self._message_id = message_id
        self._on_event = on_event
        self._tool_log: list[dict[str, Any]] = []
        self._reasoning_all = ""
        self._assistant_all = ""
        self._assistant_round = ""
        self._started_perf = time.perf_counter()
        self._model = ""
        self._token_usage: dict[str, Any] = {}
        self._metadata_written = False

    def _emit(self, event: dict[str, Any]) -> None:
        """触发事件回调（异常吞掉，避免推送失败影响主流程）。"""
        if self._on_event is None:
            return
        try:
            self._on_event(event)
        except Exception:
            pass

    def append_reasoning_delta(self, text: str) -> None:
        """每个 reasoning token 立即写入 JSONL（无缓冲），和 assistant_text 一样实时落盘。"""
        if not text:
            return
        self._reasoning_all += text
        event: dict[str, Any] = {
            "type": "reasoning_text",
            "text": text,
            "timestamp": _utc_now(),
        }
        _append_event(self.path, event)
        self._emit(event)

    def flush_reasoning_segment(self) -> str:
        """兼容保留：当前实现已无缓冲，本方法不再写盘，只返回累积文本供 DB 使用。"""
        return self._reasoning_all

    def write_tool_call(
        self,
        tool_call_id: str,
        tool_name: str,
        args: dict[str, Any],
        started_at: str | None = None,
        session_id: str = "",
    ) -> str:
        # 先把当前累积的 reasoning 写出
        reasoning = self.flush_reasoning_segment()
        ts = started_at or _utc_now()
        self._tool_log.append({
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "status": "running",
            "started_at": ts,
        })
        event: dict[str, Any] = {
            "type": "tool_call",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "args": args,
            "status": "running",
            "started_at": ts,
        }
        if session_id:
            event["session_id"] = session_id
        _append_event(self.path, event)
        self._emit(event)
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
        self._emit(event)

    def record_assistant_content(self, text: str) -> None:
        """每个 token 立即写入 JSONL（无缓冲），保证日志实时落盘。"""
        if not text:
            return
        self._assistant_all += text
        self._assistant_round += text
        event: dict[str, Any] = {
            "type": "assistant_text",
            "text": text,
            "timestamp": _utc_now(),
        }
        _append_event(self.path, event)
        self._emit(event)

    def flush_assistant_round(self) -> tuple[str, str]:
        """结束当前 LLM 轮次：返回本轮 reasoning 与 assistant 全文，并清空 assistant 轮缓冲。"""
        reasoning = self.flush_reasoning_segment()
        assistant = self._assistant_round
        self._assistant_round = ""
        return reasoning, assistant

    def write_assistant_segment(self, text: str) -> None:
        if not text:
            return
        self.flush_reasoning_segment()
        self._assistant_all += text
        self._assistant_round += text
        event: dict[str, Any] = {
            "type": "assistant_text",
            "text": text,
            "timestamp": _utc_now(),
        }
        _append_event(self.path, event)
        self._emit(event)

    def set_model(self, model: str) -> None:
        self._model = model or ""

    def set_token_usage(self, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        for key, value in usage.items():
            if key == "api_usage" and isinstance(value, dict):
                api = self._token_usage.setdefault("api_usage", {})
                for uk, uv in value.items():
                    api[uk] = uv
            elif isinstance(value, dict) and key in self._token_usage and isinstance(self._token_usage[key], dict):
                self._token_usage[key].update(value)
            else:
                self._token_usage[key] = value

    def add_token_usage(self, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        api_usage = self._token_usage.setdefault("api_usage", {})
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cached_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ):
            val = int(usage.get(key) or 0)
            if val:
                api_usage[key] = int(api_usage.get(key, 0) or 0) + val

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
        self._emit(event)

    def get_run_metadata(self) -> dict[str, Any]:
        """返回当前运行元数据（不写盘），供流式推送使用。"""
        return {
            "model": self._model,
            "duration_ms": self.duration_ms(),
            "token_usage": self._token_usage,
        }

    def finalize(self) -> None:
        self.flush_reasoning_segment()
        self.apply_api_usage_estimate()
        # write_run_metadata 内部已 self._emit
        self.write_run_metadata()
        # 广播 log_complete 事件，告知前端本次回复结束
        self._emit({
            "type": "log_complete",
            "timestamp": _utc_now(),
        })

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
        event = {
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
        }
        _append_event(self.path, event)
        self._emit(event)

    def write_error_event(
        self,
        error_type: str,
        error_msg: str,
        details: str = "",
    ) -> None:
        """记录错误事件（如 API 错误、超时等）。"""
        self.flush_reasoning_segment()
        event = {
            "type": "error_event",
            "error_type": error_type,
            "error_msg": error_msg,
            "details": details,
            "timestamp": _utc_now(),
        }
        _append_event(self.path, event)
        self._emit(event)

    def write_info_event(
        self,
        info_type: str,
        info_msg: str,
        details: str = "",
    ) -> None:
        """记录信息事件（如上下文压缩、轮次提醒等），非错误。"""
        event = {
            "type": "info_event",
            "info_type": info_type,
            "info_msg": info_msg,
            "details": details,
            "timestamp": _utc_now(),
        }
        _append_event(self.path, event)
        self._emit(event)

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

    def apply_api_usage_estimate(self) -> None:
        """API 未返回 usage 时，用 context 估算输入、用已生成文本估算输出。"""
        from utils.token_counter import estimate_tokens

        api = dict(self._token_usage.get("api_usage") or {})
        context = self._token_usage.get("context") or {}
        if not isinstance(context, dict):
            context = {}

        had_api_prompt = bool(api.get("prompt_tokens"))
        had_api_completion = bool(api.get("completion_tokens"))

        prompt = int(api.get("prompt_tokens") or 0)
        completion = int(api.get("completion_tokens") or 0)

        if not prompt:
            prompt = int(context.get("estimated_tokens") or 0)

        if not completion:
            completion = estimate_tokens(self._assistant_all) + estimate_tokens(self._reasoning_all)

        if not prompt and not completion:
            return

        merged = {**api}
        if prompt:
            merged["prompt_tokens"] = prompt
        if completion:
            merged["completion_tokens"] = completion
        merged["total_tokens"] = int(merged.get("prompt_tokens") or 0) + int(merged.get("completion_tokens") or 0)
        if not had_api_prompt or not had_api_completion:
            merged["estimated"] = True
        else:
            merged.pop("estimated", None)

        self._token_usage["api_usage"] = merged

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


def _snapshot_payload_for_message(msg: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """解析单条 assistant 消息的 JSONL / 内联 snapshot。"""
    if msg.get("role") != "assistant":
        return None
    mid = msg.get("id")
    if not mid:
        return None
    snapshot_field = msg.get("message_snapshot_json")
    events = resolve_message_log_events(snapshot_field)
    jsonl_path = (
        snapshot_field
        if snapshot_field and str(snapshot_field).endswith(".jsonl")
        else None
    )
    return str(mid), {"events": events, "jsonl_path": jsonl_path}


def load_messages_snapshots_batch(
    messages: list[dict[str, Any]],
    max_workers: int = 8,
) -> dict[str, dict[str, Any]]:
    """并行读取 session 内所有 assistant 消息的快照事件（一次 bootstrap 用）。"""
    assistant_msgs = [
        m for m in messages
        if m.get("role") == "assistant" and m.get("id")
    ]
    if not assistant_msgs:
        return {}

    result: dict[str, dict[str, Any]] = {}
    workers = min(max_workers, max(1, len(assistant_msgs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_snapshot_payload_for_message, m) for m in assistant_msgs]
        for fut in as_completed(futures):
            payload = fut.result()
            if payload:
                mid, data = payload
                result[mid] = data
    return result
