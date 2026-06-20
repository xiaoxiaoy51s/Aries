"""上下文记忆加载器。

目标：替换固定 14 轮窗口，改为：
1. session memory 摘要（长期上下文）
2. 最近消息窗口（短期上下文）
3. 最近 reasoning + 工具调用 + 工具结果工作轨迹（执行状态）
4. token 使用统计
"""
from __future__ import annotations

from typing import Any

from utils.token_counter import build_token_usage_info, estimate_message_tokens
from .compaction import DEFAULT_KEEP_TOKENS, split_messages_for_compaction

MAX_RECENT_MESSAGES = 24
MAX_ASSISTANT_CHARS = 4_000
MAX_REASONING_CHARS = 6_000
MAX_MEMORY_CHARS = 12_000


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...(内容已截断)"


def normalize_db_message(msg: dict[str, Any]) -> dict[str, Any] | None:
    """DB 消息转 LLM 消息。"""
    role = msg.get("role", "")
    content = msg.get("content", "") or ""
    if role not in ("user", "assistant"):
        return None
    if not content.strip():
        return None
    if role == "assistant":
        content = _truncate(content, MAX_ASSISTANT_CHARS)
    return {"role": role, "content": content}


def build_memory_system_message(memories: list[dict[str, Any]]) -> dict[str, str] | None:
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


def build_reasoning_system_message(reasoning_list: list[str]) -> dict[str, str] | None:
    if not reasoning_list:
        return None
    parts = []
    for idx, text in enumerate(reasoning_list, 1):
        cleaned = _truncate(text.strip(), MAX_REASONING_CHARS)
        if cleaned:
            parts.append(f"【第{idx}轮工作记录】\n{cleaned}")
    if not parts:
        return None
    return {
        "role": "system",
        "content": (
            "以下是你在本对话中最近两轮工作轨迹（用户不可见，包含深度思考、工具调用、工具结果和阶段回复；供你接续任务时参考，避免重复劳动）：\n\n"
            + "\n\n".join(parts)
        ),
    }


def select_recent_window(messages: list[dict[str, Any]], keep_tokens: int = DEFAULT_KEEP_TOKENS) -> list[dict[str, Any]]:
    """按 token 预算选择最近窗口，不再固定 14 轮。"""
    _, keep = split_messages_for_compaction(messages, keep_tokens=keep_tokens)
    if len(keep) > MAX_RECENT_MESSAGES:
        keep = keep[-MAX_RECENT_MESSAGES:]
    return keep


def build_context_messages(
    *,
    db_messages: list[dict[str, Any]],
    memories: list[dict[str, Any]],
    reasoning_list: list[str],
    current_user_text: str = "",
    model: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """构建 memory-aware 上下文。

    返回 (messages, token_info)。messages 不包含主 system prompt，也不包含当前用户原始图片消息。
    """
    normalized = []
    for msg in db_messages:
        item = normalize_db_message(msg)
        if item:
            normalized.append(item)

    if current_user_text and normalized:
        last = normalized[-1]
        if last.get("role") == "user" and last.get("content") == current_user_text:
            normalized = normalized[:-1]

    recent_messages = select_recent_window(normalized)

    result: list[dict[str, Any]] = []
    summarized_messages: list[dict[str, Any]] = []
    conversation_messages: list[dict[str, Any]] = []

    memory_msg = build_memory_system_message(memories)
    if memory_msg:
        result.append(memory_msg)
        summarized_messages.append(memory_msg)

    reasoning_msg = build_reasoning_system_message(reasoning_list)
    if reasoning_msg:
        result.append(reasoning_msg)
        conversation_messages.append(reasoning_msg)

    result.extend(recent_messages)
    conversation_messages.extend(recent_messages)

    token_info = build_token_usage_info(result, model=model)
    token_info["recent_message_count"] = len(recent_messages)
    token_info["memory_count"] = len(memories)
    token_info["reasoning_count"] = len(reasoning_list)
    token_info["recent_window_tokens"] = sum(estimate_message_tokens(m) for m in recent_messages)
    # 给上层组装 breakdown 用
    token_info["summarized_messages"] = summarized_messages
    token_info["conversation_messages"] = conversation_messages

    return result, token_info
