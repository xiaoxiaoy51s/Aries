"""Web search tool: 通过 SearXNG 进行联网搜索。"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

import httpx

DEFAULT_SEARXNG_URL = "https://searxng.ayuandoubao.icu/search"
DEFAULT_SEARCH_LIMIT = 6
DEFAULT_TIMEOUT = 15

CATEGORY_ENGINES: dict[str, str] = {
    "images": "bing images,sogou images",
    "videos": "360search videos,bilibili,sogou videos",
    "news": "sogou wechat",
    "it": "github",
}

# OpenAI function-calling schema
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "联网搜索网页信息、新闻、事实、资料。"
            "当用户需要实时信息、外部资料、新闻动态、事实核查时使用。"
            "简单常识问题不需要搜索。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "category": {
                    "type": "string",
                    "enum": ["general", "images", "videos", "news", "it"],
                    "description": "搜索分类，默认 general",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量，默认 6",
                },
            },
            "required": ["query"],
        },
    },
}


async def execute(query: str, category: str = "general", limit: int = 6) -> str:
    """执行搜索，返回格式化文本结果。"""
    engines = CATEGORY_ENGINES.get(category, "sogou,bing")
    params = {
        "q": query,
        "format": "json",
        "engines": engines,
    }
    url = f"{DEFAULT_SEARXNG_URL}?{urlencode(params)}"

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, trust_env=False) as client:
            resp = await client.get(url, headers={
                "Accept": "application/json",
                "User-Agent": "AriesCloud/1.0",
            })
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return f"搜索失败: {e}"

    raw_results = data.get("results", [])
    if not isinstance(raw_results, list):
        return "搜索返回数据格式异常"

    # 去重 + 清理
    seen_urls: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        content = (item.get("content") or "").strip()
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        cleaned.append({
            "title": title,
            "url": url,
            "content": content,
            "engine": (item.get("engine") or "").strip(),
        })
        if len(cleaned) >= limit:
            break

    if not cleaned:
        return f'未搜索到与"{query}"相关的结果。'

    # 格式化输出
    lines = [f"联网搜索结果（前 {len(cleaned)} 条）:"]
    for idx, item in enumerate(cleaned, start=1):
        lines.append(f"{idx}. {item['title']}")
        lines.append(f"URL: {item['url']}")
        lines.append(f"摘要: {item['content']}")
        lines.append(f"来源: {item['engine']}")
        lines.append("")

    return "\n".join(lines).rstrip()
