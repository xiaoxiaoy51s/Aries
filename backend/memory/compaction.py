"""会话记忆压缩。

借鉴 Claude Code 的 CompactBoundary 思路和 OpenCode 的结构化摘要模板：
- 将旧消息压缩为一条 session memory，不再固定加载最近 14 轮；
- 保留最近窗口，避免 tool_call / tool_result 被硬切断；
- 压缩摘要不调用模型，先用确定性规则从历史记录生成结构化记忆。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from utils.token_counter import estimate_tokens, estimate_message_tokens

SUMMARY_TEMPLATE = """## Goal
{goal}

## Progress
### Done
{done}

### In Progress
{in_progress}

## Key Decisions
{decisions}

## Next Steps
{next_steps}

## Critical Context
{critical_context}

## Relevant Files
{relevant_files}
"""

MAX_TOOL_RESULT_CHARS = 2_000
MAX_MESSAGE_CHARS = 4_000
MAX_SUMMARY_CHARS = 12_000
DEFAULT_KEEP_TOKENS = 10_000
DEFAULT_MAX_HISTORY_TOKENS = 60_000


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated]"


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") == "image_url":
                    parts.append("[image]")
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(p for p in parts if p)
    return str(content)


def _format_message(message: dict[str, Any]) -> str:
    role = message.get("role", "unknown")
    content = _message_text(message)
    if role == "tool":
        content = _truncate(content, MAX_TOOL_RESULT_CHARS)
    else:
        content = _truncate(content, MAX_MESSAGE_CHARS)
    return f"[{role}] {content}".strip()


def _extract_file_mentions(text: str) -> list[str]:
    import re

    candidates = re.findall(r"(?:[A-Za-z]:\\[^\s`'\"]+|[\w./-]+\.[A-Za-z0-9]{1,8})", text)
    result: list[str] = []
    for item in candidates:
        cleaned = item.rstrip(".,;:)")
        if cleaned and cleaned not in result:
            result.append(cleaned)
        if len(result) >= 12:
            break
    return result


def build_session_summary(messages: list[dict[str, Any]]) -> str:
    """把待压缩历史整理为结构化 session memory。"""
    user_messages = [m for m in messages if m.get("role") == "user"]
    assistant_messages = [m for m in messages if m.get("role") == "assistant"]
    tool_messages = [m for m in messages if m.get("role") == "tool"]

    first_user = _message_text(user_messages[0]) if user_messages else "(unknown)"
    last_user = _message_text(user_messages[-1]) if user_messages else "(unknown)"
    recent_assistant = [_message_text(m) for m in assistant_messages[-5:]]
    recent_tools = [_message_text(m) for m in tool_messages[-8:]]

    all_text = "\n".join(_message_text(m) for m in messages)
    files = _extract_file_mentions(all_text)

    done_lines = []
    for text in recent_assistant:
        text = text.strip()
        if text:
            done_lines.append(f"- {_truncate(text.replace(chr(10), ' '), 500)}")
    if not done_lines:
        done_lines = ["- (none)"]

    tool_lines = []
    for text in recent_tools:
        text = text.strip()
        if text:
            tool_lines.append(f"- {_truncate(text.replace(chr(10), ' '), 500)}")
    if not tool_lines:
        tool_lines = ["- (none)"]

    file_lines = [f"- {path}" for path in files] or ["- (none)"]

    summary = SUMMARY_TEMPLATE.format(
        goal=f"- {_truncate(first_user.replace(chr(10), ' '), 800)}",
        done="\n".join(done_lines),
        in_progress=f"- 最近用户请求：{_truncate(last_user.replace(chr(10), ' '), 800)}",
        decisions="- (none)",
        next_steps="- 根据最新用户输入继续推进，必要时先核对当前文件状态。",
        critical_context="\n".join(tool_lines),
        relevant_files="\n".join(file_lines),
    )
    return _truncate(summary, MAX_SUMMARY_CHARS)


def split_messages_for_compaction(
    messages: list[dict[str, Any]],
    keep_tokens: int = DEFAULT_KEEP_TOKENS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """返回 (to_compact, to_keep)。从尾部保留约 keep_tokens 的近期消息。"""
    if not messages:
        return [], []

    total = 0
    keep_start = len(messages)
    for idx in range(len(messages) - 1, -1, -1):
        total += estimate_message_tokens(messages[idx])
        keep_start = idx
        if total >= keep_tokens:
            break

    # 避免把 tool 结果留在窗口开头而丢失对应 assistant tool_call。
    while keep_start > 0 and messages[keep_start].get("role") == "tool":
        keep_start -= 1

    return messages[:keep_start], messages[keep_start:]


def should_compact(messages: list[dict[str, Any]], max_history_tokens: int = DEFAULT_MAX_HISTORY_TOKENS) -> bool:
    """判断历史是否需要压缩。"""
    total = sum(estimate_message_tokens(m) for m in messages)
    return total > max_history_tokens or len(messages) > 40


def make_memory_record(session_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    """生成可存储的 session memory 记录。"""
    summary = build_session_summary(messages)
    return {
        "session_id": session_id,
        "summary": summary,
        "source_message_count": len(messages),
        "source_token_estimate": sum(estimate_message_tokens(m) for m in messages),
        "summary_token_estimate": estimate_tokens(summary),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
