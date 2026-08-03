"""LLM 调用（非流式），复用用户激活模型 ModelItem。

与 ChatService 一致：httpx 直连 {baseUrl}/chat/completions，Bearer apiKey。
wiki ingest / graph 推断等离线任务用非流式，取完整 JSON。
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.model.model_config import ModelItem


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(connect=30.0, read=300.0, write=120.0, pool=30.0),
        trust_env=False,
    )


async def chat_complete(
    model: ModelItem,
    messages: list[dict],
    *,
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> str:
    """非流式对话补全，返回 content 字符串。"""
    base_url = (model.baseUrl or "").rstrip("/")
    url = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {model.apiKey}",
    }
    payload = {
        "model": model.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    async with _client() as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    return (choices[0].get("message") or {}).get("content", "") or ""


async def chat_json(
    model: ModelItem,
    messages: list[dict],
    *,
    max_tokens: int = 8192,
) -> dict:
    """非流式对话并解析返回的 JSON 对象。"""
    raw = await chat_complete(model, messages, max_tokens=max_tokens, temperature=0.1)
    return parse_json(raw)


def parse_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON 对象（去 code fence / 取首个 {...}）。"""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("LLM 输出中未找到 JSON 对象")
    return json.loads(match.group())
