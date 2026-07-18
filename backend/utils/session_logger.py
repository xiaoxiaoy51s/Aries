"""
SessionLogger: 将 agent 每轮工作过程以 JSONL 格式写入文件（一条逻辑事件一行）。

文件路径：~/.Aries/session/{YYYY-MM-DD}/{session_id}_{message_id}.jsonl

事件类型（按时间顺序）：
  - reasoning_text  : 一轮思考/工作说明（整段 flush，非逐 token 写盘）
  - tool_call       : 工具调用开始
  - tool_result     : 工具调用结束
  - assistant_text  : 每轮工作说明或最终回复（整段）

设计要点：
  - token 级写入（reasoning_delta / assistant_content）只累积到内存 + SSE 广播，
    不写盘；在段落结束（tool_call / tool_result / round 结束）时一次性写入完整文本。
  - 结构性事件（tool_call / tool_result / error 等）立即写盘。
  - JSONL 文件是唯一数据源：前端通过重读文件恢复内容。
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

# 单条工具结果写入 JSONL 的字符上限。超过则截断，避免个别巨型输出
# （如 search_file / read_file / 终端输出）撑爆 JSONL，导致切换会话时
# bootstrap 读取+前端解析卡死。JSONL 仅用于展示/恢复，LLM 上下文另行按
# token 窗口从 DB 重建，故此截断不影响模型能力。
MAX_TOOL_RESULT_CHARS = 100_000


def _cap_tool_text(text: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    """截断过长的工具结果文本，保留头部并附提示。非字符串或未超限时原样返回。"""
    if not isinstance(text, str) or len(text) <= limit:
        return text
    omitted = len(text) - limit
    return (
        text[:limit]
        + f"\n\n...(内容过长，已截断 {omitted} 字符；完整结果见任务执行时的实时输出)"
    )


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
    """单次 assistant 回复的 JSONL 日志；token 级累积，段落结束时一次性写盘。"""

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
                      用于通过 SSE 实时推送给前端。
        """
        self.path = _get_jsonl_path(session_id, message_id)
        self._session_id = session_id
        self._message_id = message_id
        self._on_event = on_event
        self._tool_log: list[dict[str, Any]] = []
        self._reasoning_all = ""
        self._reasoning_pending = ""   # 自上次 flush 后新增的 reasoning，未写盘
        self._assistant_all = ""
        self._assistant_round = ""
        self._assistant_pending = ""   # 自上次 flush 后新增的 assistant text，未写盘
        self._started_perf = time.perf_counter()
        self._model = ""
        self._token_usage: dict[str, Any] = {}
        self._metadata_written = False
        self._finalized = False
        # 持久文件句柄：避免每次写事件都 open/close
        self._file = open(self.path, "a", encoding="utf-8")

    def _write_event(self, event: dict[str, Any]) -> None:
        """写入事件到文件并 flush。"""
        if self._file.closed:
            return
        line = json.dumps(event, ensure_ascii=False)
        self._file.write(line + "\n")
        self._file.flush()

    def _close_file(self) -> None:
        """关闭文件句柄。"""
        try:
            self._file.close()
        except Exception:
            pass

    def __del__(self):
        """安全网：finalize 未调用时确保文件句柄被关闭。"""
        if not self._finalized:
            try:
                self._close_file()
            except Exception:
                pass

    def is_finalized(self) -> bool:
        return self._finalized

    def _emit(self, event: dict[str, Any]) -> None:
        """触发事件回调（异常吞掉，避免推送失败影响主流程）。"""
        if self._on_event is None:
            return
        try:
            self._on_event(event)
        except Exception:
            pass

    def append_reasoning_delta(self, text: str) -> None:
        """每个 reasoning token 只累积到内存 + SSE 广播，不写盘。"""
        if not text:
            return
        self._reasoning_all += text
        self._reasoning_pending += text
        self._emit({
            "type": "reasoning_text",
            "text": text,
            "timestamp": _utc_now(),
        })

    def flush_reasoning_segment(self) -> str:
        """将累积的 reasoning_pending 一次性写入 JSONL，返回完整 reasoning 全文。"""
        if self._reasoning_pending:
            self._write_event({
                "type": "reasoning_text",
                "text": self._reasoning_pending,
                "timestamp": _utc_now(),
            })
            self._reasoning_pending = ""
        return self._reasoning_all

    def _flush_pending_assistant(self) -> None:
        """将累积的 assistant_pending 一次性写入 JSONL。"""
        if self._assistant_pending:
            self._write_event({
                "type": "assistant_text",
                "text": self._assistant_pending,
                "timestamp": _utc_now(),
            })
            self._assistant_pending = ""

    def write_tool_call(
        self,
        tool_call_id: str,
        tool_name: str,
        args: dict[str, Any],
        started_at: str | None = None,
        session_id: str = "",
    ) -> str:
        # 先把当前累积的 reasoning 和 assistant text 一次性写盘
        reasoning = self.flush_reasoning_segment()
        self._flush_pending_assistant()
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
        self._write_event(event)
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
        cached: bool = False,
    ) -> None:
        self._flush_pending_assistant()
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
            "result": _cap_tool_text(result),
            "error": _cap_tool_text(error),
            "ended_at": ts,
        }
        if cached:
            event["cached"] = True
        if session_id:
            event["session_id"] = session_id
        if file_change:
            event["file_change"] = file_change
        self._write_event(event)
        self._emit(event)

    def write_confirmation_required(
        self,
        tool_call_id: str,
        tool_name: str,
        *,
        command: str = "",
        danger_info: str = "",
        danger_types: list[str] | None = None,
        args: dict[str, Any] | None = None,
    ) -> None:
        """工具需用户确认：写入 JSONL 并实时推送给前端（在等待用户操作之前）。"""
        event: dict[str, Any] = {
            "type": "confirmation_required",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "command": command,
            "danger_info": danger_info,
            "danger_types": danger_types or [],
            "args": args or {},
            "timestamp": _utc_now(),
        }
        self._write_event(event)
        self._emit(event)

    def record_assistant_content(self, text: str) -> None:
        """每个 assistant token 只累积到内存 + SSE 广播，不写盘。"""
        if not text:
            return
        self._assistant_all += text
        self._assistant_round += text
        self._assistant_pending += text
        self._emit({
            "type": "assistant_text",
            "text": text,
            "timestamp": _utc_now(),
        })

    def flush_assistant_round(self) -> tuple[str, str]:
        """结束当前 LLM 轮次：flush 剩余 pending 文本，返回本轮 reasoning 与 assistant 全文。"""
        reasoning = self.flush_reasoning_segment()
        self._flush_pending_assistant()
        assistant = self._assistant_round
        self._assistant_round = ""
        return reasoning, assistant

    def write_assistant_segment(self, text: str) -> None:
        """写入一段完整的 assistant 文本（非流式场景），立即写盘 + SSE 广播。"""
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
        self._write_event(event)
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
        from utils.token_counter import recalc_api_usage_totals, get_model_context_window

        api_usage = self._token_usage.setdefault("api_usage", {})

        # prompt_tokens / cached_tokens 代表"当前上下文大小"，多轮工具调用中每轮
        # 的 prompt_tokens 已含之前所有轮次，应取最后一次的值（覆盖），不能累加。
        # completion_tokens / reasoning_tokens 是每轮生成量，需要累加。
        snapshot_keys = ("prompt_tokens", "cached_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
        accumulate_keys = ("completion_tokens", "reasoning_tokens")

        for key in snapshot_keys:
            val = int(usage.get(key) or 0)
            if val:
                api_usage[key] = val  # 覆盖

        for key in accumulate_keys:
            val = int(usage.get(key) or 0)
            if val:
                api_usage[key] = int(api_usage.get(key, 0) or 0) + val  # 累加

        if any(usage.get(k) for k in snapshot_keys + accumulate_keys):
            recalc_api_usage_totals(api_usage)
            api_usage["from_api"] = True
            api_usage.pop("estimated", None)

        # 用 API 返回的真实 prompt_tokens 更新上下文占用百分比
        last_prompt = int(usage.get("prompt_tokens") or 0)
        if last_prompt:
            context = self._token_usage.setdefault("context", {})
            context_window = int(context.get("context_window") or 0) or get_model_context_window(self._model)
            context["estimated_tokens"] = last_prompt
            context["usage_percent"] = round((last_prompt / context_window) * 100, 1) if context_window > 0 else 0.0

    def emit_run_metadata_snapshot(self) -> None:
        """流式过程中推送累计 API usage（可多次，finalize 前不写盘标记）。"""
        event = {
            "type": "run_metadata",
            "model": self._model,
            "duration_ms": self.duration_ms(),
            "token_usage": self._token_usage,
            "timestamp": _utc_now(),
        }
        self._emit(event)

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
            "final": True,
        }
        self._write_event(event)
        self._emit(event)

    def get_run_metadata(self) -> dict[str, Any]:
        """返回当前运行元数据（不写盘），供流式推送使用。"""
        return {
            "model": self._model,
            "duration_ms": self.duration_ms(),
            "token_usage": self._token_usage,
        }

    def finalize(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        self.flush_reasoning_segment()
        self._flush_pending_assistant()
        self.apply_api_usage_estimate()
        # write_run_metadata 内部已 self._emit
        self.write_run_metadata()
        # 广播 log_complete 事件，告知前端本次回复结束
        self._emit({
            "type": "log_complete",
            "timestamp": _utc_now(),
        })
        # 关闭文件句柄
        self._close_file()

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
        self._write_event(event)
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
        self._write_event(event)
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
        self._write_event(event)
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
        """API 未返回 usage 时，用 context 估算输入、用已生成文本估算输出。

        MiMo / DeepSeek 等 OpenAI 兼容接口在流式最后一包会返回 usage；
        completion_tokens 已包含 reasoning，无需单独累加 reasoning_tokens。
        """
        from utils.token_counter import estimate_tokens, get_model_context_window

        api = dict(self._token_usage.get("api_usage") or {})
        context = dict(self._token_usage.get("context") or {})
        if not isinstance(context, dict):
            context = {}

        had_api_prompt = bool(api.get("prompt_tokens"))
        had_api_completion = bool(api.get("completion_tokens"))
        if api.get("from_api") or (had_api_prompt and had_api_completion):
            api.pop("estimated", None)
            self._token_usage["api_usage"] = api
            # 已在 add_token_usage 中用真实 prompt_tokens 更新过 context，无需再估算
            return

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
        merged["estimated"] = True

        self._token_usage["api_usage"] = merged

        # 用最终的 prompt_tokens 更新上下文占用百分比（兜底：API 未返回 usage 时）
        if prompt:
            context_window = int(context.get("context_window") or 0) or get_model_context_window(self._model)
            context["estimated_tokens"] = prompt
            context["usage_percent"] = round((prompt / context_window) * 100, 1) if context_window > 0 else 0.0
            self._token_usage["context"] = context

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
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # 兼容历史遗留的超大 tool_result：读取时截断，避免旧会话
                # 切换时把几 MB 单条结果塞给前端导致卡顿。
                if isinstance(evt, dict) and evt.get("type") == "tool_result":
                    if isinstance(evt.get("result"), str):
                        evt["result"] = _cap_tool_text(evt["result"])
                    if isinstance(evt.get("error"), str):
                        evt["error"] = _cap_tool_text(evt["error"])
                events.append(evt)
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
