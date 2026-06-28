"""
Token 估算工具：参考 opencode (chars/4) 与 claude-code (rough estimation) 的实现。

提供消息级、字符串级的 token 估算，以及上下文窗口占用计算。
"""
from __future__ import annotations

import json
from typing import Any

# 与 opencode 一致：4 字符 ≈ 1 token
CHARS_PER_TOKEN = 4

# 当前统一按 200k 上下文窗口估算，不做模型映射。
DEFAULT_CONTEXT_WINDOW = 200_000


def estimate_tokens(text: str) -> int:
    """估算字符串的 token 数量（参考 opencode: len / 4）。"""
    if not text:
        return 0
    return max(0, len(text) // CHARS_PER_TOKEN)


def estimate_message_tokens(message: dict[str, Any]) -> int:
    """估算单条消息的 token 数量。

    统计 content + role + tool_calls + tool_call_id 等字段的文本长度。
    参考 claude-code 的 roughTokenCountEstimationForMessages。
    """
    if not message:
        return 0

    total = 0
    # role 开销（约 4 token）
    total += 4

    content = message.get("content")
    if isinstance(content, str):
        total += estimate_tokens(content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    total += estimate_tokens(part.get("text", ""))
                elif part.get("type") == "image_url":
                    # 图片基础开销约 85 token（base64 不计入）
                    total += 85
            elif isinstance(part, str):
                total += estimate_tokens(part)

    # tool_calls 的参数也是文本
    tool_calls = message.get("tool_calls")
    if tool_calls:
        for tc in tool_calls:
            func = tc.get("function", {}) if isinstance(tc, dict) else {}
            total += estimate_tokens(func.get("name", ""))
            total += estimate_tokens(func.get("arguments", ""))

    # tool_call_id
    tcid = message.get("tool_call_id")
    if tcid:
        total += estimate_tokens(str(tcid))

    # reasoning_content
    reasoning = message.get("reasoning_content")
    if reasoning:
        total += estimate_tokens(str(reasoning))

    return total


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """估算消息列表的总 token 数。"""
    return sum(estimate_message_tokens(msg) for msg in messages)


def get_model_context_window(model: str = "") -> int:
    """统一返回 200k 上下文窗口。"""
    return DEFAULT_CONTEXT_WINDOW


def build_token_usage_info(
    messages: list[dict[str, Any]],
    model: str = "",
) -> dict[str, Any]:
    """构建 token 使用信息，供日志记录和前端展示。

    返回:
        {
            "estimated_tokens": int,       # 估算总 token
            "context_window": int,         # 模型上下文窗口
            "usage_percent": float,        # 占用百分比
            "message_count": int,          # 消息数量
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


def estimate_tool_definitions_tokens(tool_definitions: Any) -> int:
    """估算工具 schema 列表占用的 token。"""
    if not tool_definitions:
        return 0
    try:
        text = json.dumps(tool_definitions, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(tool_definitions)
    return estimate_tokens(text)


def build_context_usage_breakdown(
    *,
    system_prompt_base: str = "",
    tool_definitions: Any = None,
    rules_text: str = "",
    skills_text: str = "",
    summarized_messages: list[dict[str, Any]] | None = None,
    conversation_messages: list[dict[str, Any]] | None = None,
    model: str = "",
) -> dict[str, Any]:
    """构建按"功能模块"细分的上下文占用信息（对齐 Claude Code Context Usage 视图）。

    各项含义：
        system_prompt: 主系统提示词的纯净部分（不含 skills / rules / mcp 等可分项内容）
        tool_definitions: 工具 schema 序列化后的 token 估算
        rules: 用户 rules.md + agent 记忆等约束文本
        skills: 已安装 skills 的描述文本
        summarized_conversation: 历史压缩记忆（session memory）
        conversation: 最近消息窗口 + 最近两轮工具/思考轨迹

    返回 dict，包含每项 token 数、总数、context_window、usage_percent。
    """
    breakdown: dict[str, int] = {
        "system_prompt": estimate_tokens(system_prompt_base),
        "tool_definitions": estimate_tool_definitions_tokens(tool_definitions),
        "rules": estimate_tokens(rules_text),
        "skills": estimate_tokens(skills_text),
        "summarized_conversation": estimate_messages_tokens(summarized_messages or []),
        "conversation": estimate_messages_tokens(conversation_messages or []),
    }
    total = sum(breakdown.values())
    context_window = get_model_context_window(model)
    usage_percent = round((total / context_window) * 100, 1) if context_window > 0 else 0.0
    return {
        "breakdown": breakdown,
        "estimated_tokens": total,
        "context_window": context_window,
        "usage_percent": usage_percent,
    }


def extract_usage_from_response(response: dict[str, Any]) -> dict[str, int] | None:
    """从 LLM API 响应中提取 usage 字段（如果存在）。

    OpenAI 兼容格式: response.usage = {prompt_tokens, completion_tokens, total_tokens}
    部分 Provider 另含 cached_tokens / cache_read_input_tokens。
    """
    usage = response.get("usage")
    if not usage or not isinstance(usage, dict):
        return None
    result = _normalize_api_usage(usage)
    if not usage_has_tokens(result):
        return None
    return result


def extract_usage_from_stream_chunk(chunk: dict[str, Any]) -> dict[str, int] | None:
    """从流式响应 chunk 中提取 usage（部分模型在最后一个 chunk 返回）。"""
    usage = chunk.get("usage")
    if not usage or not isinstance(usage, dict):
        return None
    result = _normalize_api_usage(usage)
    if not usage_has_tokens(result):
        return None
    return result


def _normalize_api_usage(usage: dict[str, Any]) -> dict[str, int]:
    """归一化 OpenAI 兼容 usage（MiMo / DeepSeek / 多数国产网关结构一致）。

    - completion_tokens 已含 reasoning，勿再与 reasoning_tokens 相加
    - reasoning_tokens 仅作元数据留存，UI 不单独展示
    """
    result: dict[str, int] = {
        "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
        "total_tokens": int(usage.get("total_tokens", 0) or 0),
    }
    if not result["total_tokens"] and (result["prompt_tokens"] or result["completion_tokens"]):
        result["total_tokens"] = result["prompt_tokens"] + result["completion_tokens"]

    completion_details = usage.get("completion_tokens_details") or {}
    if isinstance(completion_details, dict):
        reasoning = int(completion_details.get("reasoning_tokens") or 0)
        if reasoning:
            result["reasoning_tokens"] = reasoning

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
        elif val:
            result[key] = val

    if not result.get("cached_tokens"):
        for key in ("cached_tokens",):
            val = int(usage.get(key) or 0)
            if val:
                result["cached_tokens"] = val

    return result


def usage_has_tokens(usage: dict[str, int] | None) -> bool:
    if not usage:
        return False
    return bool(
        usage.get("prompt_tokens")
        or usage.get("completion_tokens")
        or usage.get("total_tokens")
    )


def attach_stream_usage_options(payload: dict[str, Any]) -> dict[str, Any]:
    """OpenAI / DeepSeek / MiMo：流式最后一包返回 usage。"""
    if payload.get("stream"):
        opts = payload.get("stream_options")
        if not isinstance(opts, dict):
            opts = {}
        opts.setdefault("include_usage", True)
        payload["stream_options"] = opts
    return payload


def recalc_api_usage_totals(api_usage: dict[str, Any]) -> None:
    prompt = int(api_usage.get("prompt_tokens") or 0)
    completion = int(api_usage.get("completion_tokens") or 0)
    if prompt or completion:
        api_usage["total_tokens"] = prompt + completion
