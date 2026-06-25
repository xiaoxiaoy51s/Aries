from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from fastapi import HTTPException


SEARXNG_SEARCH_URL = "https://searxng.ayuandoubao.icu/search"
DEFAULT_SEARCH_LIMIT = 6
DEFAULT_TIMEOUT_SECONDS = 15
MAX_RESULTS_PER_ROOT_DOMAIN = 2

SPAM_KEYWORDS = {
    "adult": ["色情", "成人", "性爱", "裸体", "激情", "av", "porn", "pornhub", "约炮", "一夜情", "援交", "色情服务"],
    "gambling": ["赌博", "博彩", "赌球", "庄家", "赔率", "下注", "网投", "彩票平台", "时时彩", "百家乐", "老虎机"],
    "loan_shark": ["高利贷", "裸贷", "套路贷", "校园贷", "现金贷", "快速放款", "秒下款"],
}

CATEGORY_ENGINES: dict[str, str] = {
    "images": "bing images,sogou images",
    "videos": "360search videos,bilibili,sogou videos",
    "news": "sogou wechat",
    "it": "github",
}


def get_web_search_tool_definition() -> dict:
    today_str = datetime.now().strftime("%Y-%m-%d")
    return {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "联网搜索网页信息、新闻、事实、资料、实时信息。"
                "使用 SearXNG 搜索引擎并返回结构化结果，需要外部信息时优先调用。"
                f" Today's date is {today_str}; if the user only gives month/day and does not specify a year, use the current year."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜索的关键词或问题",
                    },
                    "category": {
                        "type": "string",
                        "description": "搜索分类，可选值: general（综合/默认, 引擎: sogou,bing）, it（IT技术, 引擎: github）, news（新闻, 引擎: sogou wechat）, images（图片, 引擎: bing images,sogou images）, videos（视频, 引擎: 360search videos,bilibili,sogou videos）。默认 general 走综合搜索",
                    },
                    "engines": {
                        "type": "string",
                        "description": "自定义搜索引擎，可选值: bing, sogou, 360search, bilibili, bing images, sogou images, 360search videos, bilibili, sogou videos, sogou wechat, github。多个引擎用逗号分隔",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量，默认 6",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }


def _normalize_limit(limit: int | None) -> int:
    try:
        normalized = int(limit or DEFAULT_SEARCH_LIMIT)
    except (TypeError, ValueError):
        normalized = DEFAULT_SEARCH_LIMIT
    return max(1, normalized)


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


DEFAULT_ENGINES = "sogou,bing"


def _build_search_url(query: str, category: str | None = None, engines: str | None = None) -> str:
    # 优先使用自定义引擎，其次使用分类配置的引擎，最后使用默认引擎
    if engines:
        selected_engines = engines
    else:
        selected_engines = CATEGORY_ENGINES.get(category or "", DEFAULT_ENGINES)
    params: dict[str, str] = {
        "q": query,
        "format": "json",
        "engines": selected_engines,
    }
    return f"{SEARXNG_SEARCH_URL}?{urlencode(params)}"


def _fetch_searxng_payload(query: str, category: str | None = None, engines: str | None = None) -> dict[str, Any]:
    search_url = _build_search_url(query, category, engines)
    request = Request(
        search_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "NonoClaw/1.0",
        },
        method="GET",
    )

    # 检查是否需要走代理（按域名规则匹配）
    proxy_handler = None
    try:
        from utils.network_manager import get_proxy_for_url
        proxy_dict = get_proxy_for_url(search_url)
        if proxy_dict:
            from urllib.request import ProxyHandler, build_opener
            proxy_handler = ProxyHandler(proxy_dict)
    except Exception:
        pass

    try:
        if proxy_handler:
            opener = build_opener(proxy_handler)
            with opener.open(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                payload = response.read().decode(charset, errors="replace")
        else:
            with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                payload = response.read().decode(charset, errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        raise HTTPException(status_code=502, detail=f"SearXNG request failed: {detail or exc.reason}") from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail=f"SearXNG connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="SearXNG request timed out") from exc

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="SearXNG returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="SearXNG returned invalid payload")
    return data


def _extract_results(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        return []

    results: list[dict[str, Any]] = []
    for item in raw_results[:limit]:
        if not isinstance(item, dict):
            continue

        result_item = {
            "title": _clean_text(item.get("title")),
            "url": _clean_text(item.get("url")),
            "content": _clean_text(item.get("content")),
            "engine": _clean_text(item.get("engine")),
            "category": _clean_text(item.get("category")),
            "score": item.get("score"),
        }
        # 图片搜索时提取图片链接
        if item.get("img_src"):
            result_item["img_src"] = _clean_text(item.get("img_src"))
        if item.get("thumbnail"):
            result_item["thumbnail"] = _clean_text(item.get("thumbnail"))
        # 视频搜索时提取视频链接
        if item.get("video_src"):
            result_item["video_src"] = _clean_text(item.get("video_src"))
        if item.get("duration"):
            result_item["duration"] = _clean_text(item.get("duration"))
        results.append(result_item)
    return results


def _is_spam(item: dict[str, Any]) -> bool:
    combined = f"{item.get('title', '')} {item.get('content', '')} {item.get('url', '')}".lower()
    for category, keywords in SPAM_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                return True
    return False


def _extract_root_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        parts = domain.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else domain
    except Exception:
        return ""


def _simple_clean_results(
    results: list[dict[str, Any]],
    final_limit: int,
    category: str | None = None,
) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    domain_counts: dict[str, int] = {}
    cleaned: list[dict[str, Any]] = []

    # 视频和图片搜索放宽 content 长度限制
    min_content_length = 1 if category in ("videos", "images") else 10

    for item in results:
        title = item.get("title", "")
        url = item.get("url", "")
        content = item.get("content", "")

        if not title or not url:
            continue

        if len(title) < 3 or len(content) < min_content_length:
            continue

        if url in seen_urls:
            continue
        seen_urls.add(url)

        if _is_spam(item):
            continue

        root = _extract_root_domain(url)
        if root and domain_counts.get(root, 0) >= MAX_RESULTS_PER_ROOT_DOMAIN:
            continue
        if root:
            domain_counts[root] = domain_counts.get(root, 0) + 1

        cleaned.append(item)
        if len(cleaned) >= final_limit:
            break

    return cleaned


def _format_assistant_text(query: str, results: list[dict[str, Any]], category: str | None = None) -> str:
    if not results:
        return f'未搜索到与"{query}"相关的结果。'

    is_image_search = category == "images"
    is_video_search = category == "videos"
    lines = [f"联网搜索结果（前 {len(results)} 条）:"]
    for index, item in enumerate(results, start=1):
        title = item.get("title") or "(无标题)"
        url = item.get("url") or "(无链接)"
        snippet = item.get("content") or "暂无摘要"
        engine = item.get("engine") or "unknown"
        lines.append(f"{index}. {title}")
        lines.append(f"URL: {url}")
        # 图片搜索时显示图片链接
        if is_image_search:
            img_src = item.get("img_src") or item.get("thumbnail")
            if img_src:
                lines.append(f"图片: {img_src}")
        # 视频搜索时显示缩略图和时长
        if is_video_search:
            thumbnail = item.get("thumbnail")
            if thumbnail:
                lines.append(f"缩略图: {thumbnail}")
            duration = item.get("duration")
            if duration:
                lines.append(f"时长: {duration}")
        lines.append(f"摘要: {snippet}")
        lines.append(f"来源: {engine}")
        lines.append("")
    return "\n".join(lines).rstrip()


def execute_web_search(
    query: str,
    limit: int | None = None,
    category: str | None = None,
    engines: str | None = None,
) -> dict:
    normalized_query = str(query or "").strip()
    if not normalized_query:
        raise HTTPException(status_code=400, detail="query is required")

    # 图片和视频搜索默认 4 条，其他默认 6 条
    if limit is None:
        if category in ("images", "videos"):
            default_limit = 4
        else:
            default_limit = DEFAULT_SEARCH_LIMIT
    else:
        default_limit = limit

    normalized_limit = _normalize_limit(default_limit)
    payload = _fetch_searxng_payload(normalized_query, category, engines)
    raw_results = _extract_results(payload, 200)
    cleaned_results = _simple_clean_results(raw_results, normalized_limit, category)

    return {
        "query": normalized_query,
        "model": "searxng",
        "assistant_text": _format_assistant_text(normalized_query, cleaned_results, category),
        "results": cleaned_results,
        "limit": normalized_limit,
        "total_fetched": len(raw_results),
        "total_after_cleaning": len(cleaned_results),
    }


def execute_web_search_tool(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = arguments or {}
    result = execute_web_search(
        query=str(payload.get("query", "")).strip(),
        limit=int(payload.get("limit", DEFAULT_SEARCH_LIMIT) or DEFAULT_SEARCH_LIMIT),
        category=str(payload.get("category")) if payload.get("category") else None,
        engines=str(payload.get("engines")) if payload.get("engines") else None,
    )
    return {
        "success": True,
        "output": result.get("assistant_text", ""),
        "data": result,
    }


def get_tool_definition() -> dict:
    return get_web_search_tool_definition()


def execute(**kwargs) -> dict[str, Any]:
    return execute_web_search_tool(kwargs)
