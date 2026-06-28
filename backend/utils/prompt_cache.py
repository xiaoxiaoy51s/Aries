"""L1 Prompt 前缀缓存：分层 system messages + 稳定 tools 排序，便于 Provider 命中 prefix cache。"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any


PROMPT_CACHE_VERSION = "1"


def is_prompt_cache_enabled() -> bool:
    val = os.environ.get("ARIES_PROMPT_CACHE", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize_tool_definitions(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """按工具名排序，保证多轮请求 tools JSON 字节级稳定。"""

    def _name(t: dict[str, Any]) -> str:
        fn = t.get("function") or {}
        return str(fn.get("name") or "")

    return sorted(tools or [], key=_name)


def compute_config_fingerprint(
    tool_definitions: list[dict[str, Any]] | None,
    *,
    prompt_parts: dict[str, str] | None = None,
    model: str = "",
) -> str:
    """配置指纹：skills/MCP/subagents/tools 变化时前缀 cache 自然失效。"""
    parts = prompt_parts or {}
    blob = _stable_json({
        "v": PROMPT_CACHE_VERSION,
        "model": model or "",
        "static": parts.get("static") or parts.get("base") or "",
        "rules": parts.get("rules") or "",
        "skills": parts.get("skills") or "",
        "mcp": parts.get("mcp") or "",
        "subagents": parts.get("subagents") or "",
        "plugins": parts.get("plugins") or "",
        "tools": normalize_tool_definitions(tool_definitions),
    })
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _join_non_empty(*chunks: str) -> str:
    return "".join(c for c in chunks if c)


def build_layered_messages(
    prompt_parts: dict[str, str],
    conversation_messages: list[dict[str, Any]],
    *,
    extra_system_suffix: str = "",
) -> list[dict[str, Any]]:
    """构建 cache-friendly 的 messages 列表。

    分层（稳定 → 易变）：
      1. static  — 身份、编码规范、edit 规则（不含日期/session/work_dir）
      2. semi    — rules + subagents + plugins + skills + mcp
      3. runtime — 日期、session、工作目录、agent 模式后缀
      4. 对话历史（user/assistant/tool，每轮只在末尾 append）
    """
    history = [m for m in conversation_messages if m.get("role") != "system"]

    static = (prompt_parts.get("static") or "").strip()
    if not static and prompt_parts.get("full"):
        content = prompt_parts["full"]
        if extra_system_suffix:
            content += extra_system_suffix
        return [{"role": "system", "content": content}, *history]

    layered: list[dict[str, Any]] = []

    if static:
        layered.append({"role": "system", "content": static})

    semi = _join_non_empty(
        prompt_parts.get("rules") or "",
        prompt_parts.get("subagents") or "",
        prompt_parts.get("plugins") or "",
        prompt_parts.get("skills") or "",
        prompt_parts.get("mcp") or "",
    ).strip()
    if semi:
        layered.append({"role": "system", "content": semi})

    runtime = (prompt_parts.get("runtime") or "").strip()
    if extra_system_suffix:
        runtime = runtime + extra_system_suffix
    if runtime:
        layered.append({"role": "system", "content": runtime})

    layered.extend(history)
    return layered


def prepare_llm_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tool_definitions: list[dict[str, Any]] | None = None,
    stream: bool = True,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tool_choice: str | None = "auto",
) -> dict[str, Any]:
    """组装 LLM 请求 payload；tools 使用稳定排序。"""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    if tool_definitions:
        payload["tools"] = normalize_tool_definitions(tool_definitions)
        if tool_choice:
            payload["tool_choice"] = tool_choice
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    from utils.token_counter import attach_stream_usage_options
    return attach_stream_usage_options(payload)


def summarize_cache_usage(api_usage: dict[str, Any] | None) -> dict[str, Any]:
    """从累计 api_usage 计算 Provider 前缀 cache 命中率摘要。"""
    if not api_usage:
        return {}
    prompt = int(api_usage.get("prompt_tokens") or 0)
    cached = int(api_usage.get("cached_tokens") or 0)
    cache_read = int(api_usage.get("cache_read_input_tokens") or 0)
    hit = cached or cache_read
    if not hit:
        return {}
    # prompt_tokens 可能小于 cache hit（Provider 只统计未缓存部分），分母取较大值
    denominator = max(prompt, hit)
    rate = round(min(hit / denominator, 1.0) * 100, 1) if denominator else 0.0
    return {
        "cached_tokens": hit,
        "prompt_tokens": prompt,
        "cache_hit_rate_percent": rate,
    }
