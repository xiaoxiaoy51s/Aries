"""上下文加载器（Reasonix 风格）。

全量加载完整对话历史（含 tool_calls 和 tool 结果），不上传 reasoning_content。
消息以 append-only 方式增长，不设滑动窗口，仅在接近窗口上限时触发压缩。

参考 DeepSeek-Reasonix 的设计：
- 全量上传所有消息，ModelMessages() 只剥离 LocalOnly 标记
- 不上传 reasoning_content（保存用于显示，但不发送给 API）
- tool_calls 和 tool 结果本身就是完整的执行记录，无需额外 reasoning 注入
- 工具结果在 JSONL 写入时已截断到 100k 字符，重建时不再二次裁剪（保证缓存稳定）
"""
from __future__ import annotations

import json
from typing import Any

from utils.token_counter import build_token_usage_info, estimate_message_tokens

# 保留给 session memory 使用
MAX_MEMORY_CHARS = 12_000


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...(内容已截断)"


def _rebuild_messages_from_jsonl(msg: dict[str, Any]) -> list[dict[str, Any]]:
    """从 assistant 消息的 JSONL 日志重建完整消息序列。

    将 JSONL 中的事件序列重建为符合 API 格式的消息列表：
      assistant{tool_calls:[...]} -> tool{} -> tool{} -> assistant{tool_calls:[...]} -> ...

    关键规则：
    - 连续的 tool_call 事件属于同一个 API 响应，必须合并到一个 assistant 消息
    - tool_result 事件只累积不 flush，等下一轮 tool_call 或 assistant_text 时才 flush
    - 不包含 reasoning_text 事件（不上传 reasoning 给 API）
    - 工具结果不按位置裁剪（保证同一条消息每次重建结果一致，命中缓存）
    """
    snapshot = msg.get("message_snapshot_json")
    if not snapshot:
        return []

    from utils.session_logger import resolve_message_log_events
    try:
        events = resolve_message_log_events(snapshot)
    except Exception:
        return []

    # 过滤掉 reasoning 事件
    events = [e for e in events if isinstance(e, dict) and e.get("type") != "reasoning_text"]
    if not events:
        return []

    messages: list[dict[str, Any]] = []
    round_text = ""
    pending_calls: list[dict[str, Any]] = []
    pending_results: list[dict[str, Any]] = []

    def _flush_round() -> None:
        """将当前累积的 calls + results 输出为消息序列。

        输出格式：
          assistant{tool_calls:[...]} -> tool{} -> tool{} -> ...
        """
        nonlocal round_text, pending_calls, pending_results

        if pending_calls:
            # 构建 assistant 消息（含 tool_calls）
            calls = []
            for c in pending_calls:
                args = c.get("args") or {}
                calls.append({
                    "id": c.get("tool_call_id", ""),
                    "type": "function",
                    "function": {
                        "name": c.get("tool_name", ""),
                        "arguments": json.dumps(args, ensure_ascii=False) if not isinstance(args, str) else args,
                    }
                })
            messages.append({
                "role": "assistant",
                "content": round_text or None,
                "tool_calls": calls,
            })
            round_text = ""

            # 检查未匹配的 tool_calls（中断场景），回填占位符
            call_ids = {c.get("tool_call_id", "") for c in pending_calls}
            result_ids = {r.get("tool_call_id", "") for r in pending_results}
            missing_ids = call_ids - result_ids
            for c in pending_calls:
                cid = c.get("tool_call_id", "")
                if cid in missing_ids:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": cid,
                        "content": "[no result: the previous turn was interrupted before this tool call completed]",
                    })
            pending_calls = []

            # 输出所有 tool 结果
            for r in pending_results:
                content = r.get("result") or r.get("error") or ""
                messages.append({
                    "role": "tool",
                    "tool_call_id": r.get("tool_call_id", ""),
                    "content": content,
                })
            pending_results = []
        else:
            # 没有 pending_calls 但有 pending_results：孤立的 tool 结果
            # 直接丢弃，不能作为 tool 消息发送（API 要求前面必须有 tool_calls）
            pending_results = []

    for evt in events:
        typ = evt.get("type")
        if typ == "assistant_text":
            # 新的 assistant 文本：如果上一轮有结果，先 flush
            if pending_calls or pending_results:
                _flush_round()
            text = (evt.get("text") or "").strip()
            if text:
                round_text = (round_text + "\n" + text).strip() if round_text else text
        elif typ == "tool_call":
            # 新的 tool_call：如果上一轮有结果，先 flush 再开始新轮
            if pending_results:
                _flush_round()
            pending_calls.append(evt)
        elif typ == "tool_result":
            # 只累积，不 flush
            # flush 时机：下一个 tool_call（新轮开始）或 assistant_text 或收尾
            pending_results.append(evt)

    # 收尾
    _flush_round()
    if round_text:
        messages.append({"role": "assistant", "content": round_text})

    return messages


def build_memory_system_message(memories: list[dict[str, Any]]) -> dict[str, str] | None:
    """构建 session memory 摘要的 system 消息。"""
    if not memories:
        return None

    parts = []
    for idx, memory in enumerate(memories, 1):
        summary = _truncate(memory.get("summary", ""), MAX_MEMORY_CHARS)
        if not summary:
            continue
        created_at = memory.get("created_at") or ""
        parts.append(f"<memory index=\"{idx}\" created_at=\"{created_at}\">\n{summary}\n</memory>")

    if not parts:
        return None

    return {
        "role": "system",
        "content": (
            "以下是本会话较早内容的压缩记忆，用于接续长期任务。"
            "记忆可能过时；如果涉及文件或代码状态，必须以当前实际文件为准。\n\n"
            + "\n\n".join(parts)
        ),
    }


def build_context_messages(
    *,
    db_messages: list[dict[str, Any]],
    memories: list[dict[str, Any]],
    current_user_text: str = "",
    model: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """构建上下文消息列表（Reasonix 风格）。

    返回 (messages, token_info)。
    - 全量加载所有非压缩消息
    - assistant 消息从 JSONL 重建完整 tool_calls/result 序列
    - 不上传 reasoning_content，不注入 reasoning system 消息
    - 不设滑动窗口，不截断历史
    - 工具结果不按位置裁剪（保证缓存稳定命中）
    """
    result: list[dict[str, Any]] = []

    # 1. session memory（如有）
    memory_msg = build_memory_system_message(memories)
    if memory_msg:
        result.append(memory_msg)

    # 2. 全量加载历史消息（不含已压缩的）
    total_assistant = 0
    for msg in db_messages:
        if msg.get("compacted"):
            continue
        role = msg.get("role", "")
        if role == "user":
            content = (msg.get("content") or "").strip()
            if content:
                result.append({"role": "user", "content": content})
        elif role == "assistant":
            total_assistant += 1
            # 从 JSONL 重建完整消息序列（含 tool_calls + tool 结果）
            rebuilt = _rebuild_messages_from_jsonl(msg)
            if rebuilt:
                result.extend(rebuilt)
            else:
                # 没有 JSONL 时回退到 DB content
                content = (msg.get("content") or "").strip()
                if content:
                    result.append({"role": "assistant", "content": content})

    # 3. 去掉与当前用户消息重复的最后一条 user 消息
    if current_user_text and result:
        last = result[-1]
        if last.get("role") == "user" and last.get("content") == current_user_text:
            result = result[:-1]

    # 4. token 统计
    token_info = build_token_usage_info(result, model=model)
    token_info["recent_message_count"] = total_assistant
    token_info["memory_count"] = len(memories)

    # 给上层组装 breakdown 用
    token_info["summarized_messages"] = [memory_msg] if memory_msg else []
    token_info["conversation_messages"] = result

    return result, token_info
