"""上下文构建器。

全量加载对话历史，从 JSONL 重建消息内容，不上传 reasoning_content。
提供 token 用量预估和缓存命中统计。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.utils.session_logger import read_jsonl_events, reconstruct_from_events
from app.utils.token_counter import build_context_token_info


def _build_api_messages(db_messages: list[dict[str, Any]], current_user_text: str) -> list[dict[str, Any]]:
    """从数据库消息列表构建 API 消息序列。

    规则：
    - 不上传 reasoning_content
    - user 消息直接取 content
    - assistant 消息从 JSONL 重建
    - 去掉与 current_user_text 重复的最后一条 user 消息
    """
    result: list[dict[str, Any]] = []

    for msg in db_messages:
        role = msg.get("role", "")
        if role == "user":
            content = (msg.get("content") or "").strip()
            if content:
                result.append({"role": "user", "content": content})
        elif role == "assistant":
            # 从 JSONL 重建
            log_path = msg.get("log_path") or ""
            content_text = ""
            if log_path:
                events = read_jsonl_events(log_path)
                reconstructed = reconstruct_from_events(events)
                content_text = (reconstructed.get("assistant_content") or "").strip()
            if not content_text:
                content_text = (msg.get("content") or "").strip()
            if content_text:
                result.append({"role": "assistant", "content": content_text})

    # 去掉与当前用户消息重复的最后一条 user 消息
    if current_user_text and result:
        last = result[-1]
        if last.get("role") == "user" and last.get("content") == current_user_text:
            result = result[:-1]

    return result


def build_context_messages(
    db_messages: list[dict[str, Any]],
    current_user_text: str = "",
    model: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """构建完整的上下文消息列表（含 system prompt + 历史 + 当前用户消息）。

    返回 (messages, token_info):
      - messages: 可直接发送给 LLM API 的消息列表
      - token_info: 包含 estimated_tokens, context_window, usage_percent, message_count, breakdown
    """
    # 1. 基础 system prompt
    today = datetime.now().strftime("%Y-%m-%d")
    system_msg: dict[str, Any] = {
        "role": "system",
        "content": (
            f"You are Aries Cloud, a helpful AI assistant.\n"
            f"Today's date is {today}."
        ),
    }

    # 2. 历史消息
    history_messages = _build_api_messages(db_messages, current_user_text)

    # 3. 当前用户消息
    user_msg = {"role": "user", "content": current_user_text}

    # 4. 组装完整消息列表
    messages = [system_msg] + history_messages + [user_msg]

    # 5. token 统计（不含当前 user_msg，只算已发送的上下文）
    context_token_info = build_context_token_info(
        [system_msg] + history_messages,
        model=model,
    )

    return messages, context_token_info
