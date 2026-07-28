"""
Token 估算工具：优先使用 tiktoken 真实 tokenizer，不可用时回退到字符级估算。

提供消息级、字符串级的 token 估算，以及上下文窗口占用计算。
"""
from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# tiktoken 编码器（懒加载单例）
# ---------------------------------------------------------------------------
_encoder = None
_encoder_tried = False


def _get_encoder():
    """懒加载 tiktoken cl100k_base 编码器，失败则返回 None。"""
    global _encoder, _encoder_tried
    if _encoder_tried:
        return _encoder
    _encoder_tried = True
    try:
        import tiktoken
        _encoder = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _encoder = None
    return _encoder


# ---------------------------------------------------------------------------
# 字符级估算 fallback
# ---------------------------------------------------------------------------
CHARS_PER_TOKEN = 4
CJK_CHARS_PER_TOKEN = 1.5
DEFAULT_CONTEXT_WINDOW = 200_000


def _count_cjk_chars(text: str) -> int:
    """统计 CJK（中日韩）字符数量。"""
    if not text:
        return 0
    count = 0
    for ch in text:
        cp = ord(ch)
        if (
            0x4E00 <= cp <= 0x9FFF
            or 0x3400 <= cp <= 0x4DBF
            or 0x20000 <= cp <= 0x2A6DF
            or 0x3040 <= cp <= 0x30FF
            or 0xAC00 <= cp <= 0xD7AF
            or 0xFF00 <= cp <= 0xFFEF
        ):
            count += 1
    return count


def _estimate_tokens_chars(text: str) -> int:
    """字符级 token 估算（fallback）。"""
    if not text:
        return 0
    cjk_count = _count_cjk_chars(text)
    non_cjk_len = len(text) - cjk_count
    cjk_tokens = int(cjk_count / CJK_CHARS_PER_TOKEN) if cjk_count else 0
    non_cjk_tokens = non_cjk_len // CHARS_PER_TOKEN
    return max(0, cjk_tokens + non_cjk_tokens)


def estimate_tokens(text: str) -> int:
    """估算字符串的 token 数量。"""
    if not text:
        return 0
    enc = _get_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    return _estimate_tokens_chars(text)


def estimate_message_tokens(message: dict[str, Any]) -> int:
    """估算单条消息的 token 数量。"""
    if not message:
        return 0
    total = 4  # role 开销

    content = message.get("content")
    if isinstance(content, str):
        total += estimate_tokens(content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    total += estimate_tokens(part.get("text", ""))
                elif part.get("type") == "image_url":
                    total += 85

    tool_calls = message.get("tool_calls")
    if tool_calls:
        for tc in tool_calls:
            func = tc.get("function", {}) if isinstance(tc, dict) else {}
            total += estimate_tokens(func.get("name", ""))
            total += estimate_tokens(func.get("arguments", ""))

    return total


def get_model_context_window(model: str = "") -> int:
    """统一返回 200k 上下文窗口。"""
    return DEFAULT_CONTEXT_WINDOW


def build_context_token_info(
    messages: list[dict[str, Any]],
    model: str = "",
) -> dict[str, Any]:
    """构建上下文 token 使用信息。

    返回:
        {
            "estimated_tokens": int,       # 估算总 token
            "context_window": int,         # 模型上下文窗口
            "usage_percent": float,        # 占用百分比
            "message_count": int,          # 消息数量
            "cached_input_tokens": int,    # 可能命中的 cache（估算）
            "breakdown": {                 # 按角色分解
                "system": int,
                "user": int,
                "assistant": int,
                "tool": int,
            },
        }
    """
    total = 0
    breakdown: dict[str, int] = {"system": 0, "user": 0, "assistant": 0, "tool": 0}

    for msg in messages:
        msg_tokens = estimate_message_tokens(msg)
        total += msg_tokens
        role = msg.get("role", "user")
        if role in breakdown:
            breakdown[role] += msg_tokens
        else:
            breakdown["user"] += msg_tokens

    context_window = get_model_context_window(model)
    usage_percent = round((total / context_window) * 100, 1) if context_window > 0 else 0.0

    return {
        "estimated_tokens": total,
        "context_window": context_window,
        "usage_percent": usage_percent,
        "message_count": len(messages),
        "breakdown": breakdown,
    }


def normalize_api_usage(usage: dict[str, Any]) -> dict[str, int]:
    """归一化 OpenAI 兼容 usage 格式。

    支持 prompt_tokens_details.cached_tokens 等缓存字段。
    """
    result: dict[str, int] = {
        "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
        "total_tokens": int(usage.get("total_tokens", 0) or 0),
    }
    if not result["total_tokens"] and (result["prompt_tokens"] or result["completion_tokens"]):
        result["total_tokens"] = result["prompt_tokens"] + result["completion_tokens"]

    # cached_tokens
    cached = 0
    prompt_details = usage.get("prompt_tokens_details") or {}
    if isinstance(prompt_details, dict):
        cached = int(prompt_details.get("cached_tokens") or 0)
    if not cached:
        cached = int(usage.get("prompt_cache_hit_tokens") or 0)
    if cached:
        result["cached_tokens"] = cached
    for key in ("cache_read_input_tokens", "cache_creation_input_tokens"):
        val = int(usage.get(key) or 0)
        if val and key == "cache_read_input_tokens":
            result["cached_tokens"] = result.get("cached_tokens", 0) + val

    # reasoning_tokens
    completion_details = usage.get("completion_tokens_details") or {}
    if isinstance(completion_details, dict):
        reasoning = int(completion_details.get("reasoning_tokens") or 0)
        if reasoning:
            result["reasoning_tokens"] = reasoning

    return result
