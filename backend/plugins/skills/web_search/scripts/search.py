#!/usr/bin/env python3
"""Standalone CLI web search script using SearXNG.

Usage:
    python search.py "query"
    python search.py "query" --category images --limit 4
    python search.py "query" --engines bing,sogou
    python search.py "query" --server https://your-searxng.example.com/search

Output: JSON to stdout with structured search results.

Environment variables:
    SEARXNG_URL  - Override the default SearXNG server URL
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

DEFAULT_SEARXNG_URL = "https://searxng.ayuandoubao.icu/search"
DEFAULT_SEARCH_LIMIT = 6
DEFAULT_TIMEOUT_SECONDS = 15
MAX_RESULTS_PER_ROOT_DOMAIN = 2

CATEGORY_ENGINES: dict[str, str] = {
    "images": "bing images,sogou images",
    "videos": "360search videos,bilibili,sogou videos",
    "news": "sogou wechat",
    "it": "github",
}

SPAM_KEYWORDS = {
    "adult": [
        "色情", "成人", "性爱", "裸体", "激情", "av", "porn", "pornhub",
        "约炮", "一夜情", "援交", "色情服务",
    ],
    "gambling": [
        "赌博", "博彩", "赌球", "庄家", "赔率", "下注", "网投",
        "彩票平台", "时时彩", "百家乐", "老虎机",
    ],
    "loan_shark": [
        "高利贷", "裸贷", "套路贷", "校园贷", "现金贷", "快速放款", "秒下款",
    ],
}


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


def _build_search_url(
    query: str,
    server: str,
    category: str | None = None,
    engines: str | None = None,
) -> str:
    if engines:
        selected_engines = engines
    else:
        selected_engines = CATEGORY_ENGINES.get(category or "", "sogou,bing")
    params: dict[str, str] = {
        "q": query,
        "format": "json",
        "engines": selected_engines,
    }
    return f"{server}?{urlencode(params)}"


def _fetch_searxng(
    query: str,
    server: str,
    category: str | None = None,
    engines: str | None = None,
) -> dict[str, Any]:
    search_url = _build_search_url(query, server, category, engines)
    request = Request(
        search_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "WebSearchSkill/1.0",
        },
        method="GET",
    )

    # Optional proxy support
    proxy_handler = None
    try:
        from utils.network_manager import get_proxy_for_url  # type: ignore[import-untyped]
        proxy_dict = get_proxy_for_url(search_url)
        if proxy_dict:
            from urllib.request import ProxyHandler, build_opener
            proxy_handler = ProxyHandler(proxy_dict)
    except Exception:
        pass

    try:
        if proxy_handler:
            opener = build_opener(proxy_handler)
            resp = opener.open(request, timeout=DEFAULT_TIMEOUT_SECONDS)
        else:
            resp = urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS)
        with resp as response:
            charset = response.headers.get_content_charset() or "utf-8"
            payload = response.read().decode(charset, errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        return {"error": f"SearXNG request failed: {detail or exc.reason}"}
    except URLError as exc:
        return {"error": f"SearXNG connection failed: {exc.reason}"}
    except TimeoutError:
        return {"error": "SearXNG request timed out"}

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {"error": "SearXNG returned invalid JSON"}

    if not isinstance(data, dict):
        return {"error": "SearXNG returned invalid payload"}
    return data


def _extract_results(data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        return []

    results: list[dict[str, Any]] = []
    for item in raw_results[:limit]:
        if not isinstance(item, dict):
            continue
        result_item: dict[str, Any] = {
            "title": _clean_text(item.get("title")),
            "url": _clean_text(item.get("url")),
            "content": _clean_text(item.get("content")),
            "engine": _clean_text(item.get("engine")),
            "category": _clean_text(item.get("category")),
            "score": item.get("score"),
        }
        if item.get("img_src"):
            result_item["img_src"] = _clean_text(item.get("img_src"))
        if item.get("thumbnail"):
            result_item["thumbnail"] = _clean_text(item.get("thumbnail"))
        if item.get("video_src"):
            result_item["video_src"] = _clean_text(item.get("video_src"))
        if item.get("duration"):
            result_item["duration"] = _clean_text(item.get("duration"))
        results.append(result_item)
    return results


def _is_spam(item: dict[str, Any]) -> bool:
    combined = f"{item.get('title', '')} {item.get('content', '')} {item.get('url', '')}".lower()
    for _cat, keywords in SPAM_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                return True
    return False


def _extract_root_domain(url: str) -> str:
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        parts = domain.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else domain
    except Exception:
        return ""


def _clean_results(
    results: list[dict[str, Any]],
    final_limit: int,
    category: str | None = None,
) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    domain_counts: dict[str, int] = {}
    cleaned: list[dict[str, Any]] = []
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


def _format_assistant_text(
    query: str,
    results: list[dict[str, Any]],
    category: str | None = None,
) -> str:
    if not results:
        return f'未搜索到与"{query}"相关的结果。'
    is_image = category == "images"
    is_video = category == "videos"
    lines = [f"联网搜索结果（前 {len(results)} 条）:"]
    for idx, item in enumerate(results, start=1):
        title = item.get("title") or "(无标题)"
        url = item.get("url") or "(无链接)"
        snippet = item.get("content") or "暂无摘要"
        engine = item.get("engine") or "unknown"
        lines.append(f"{idx}. {title}")
        lines.append(f"URL: {url}")
        if is_image:
            img = item.get("img_src") or item.get("thumbnail")
            if img:
                lines.append(f"图片: {img}")
        if is_video:
            thumb = item.get("thumbnail")
            if thumb:
                lines.append(f"缩略图: {thumb}")
            dur = item.get("duration")
            if dur:
                lines.append(f"时长: {dur}")
        lines.append(f"摘要: {snippet}")
        lines.append(f"来源: {engine}")
        lines.append("")
    return "\n".join(lines).rstrip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Web search via SearXNG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("query", help="Search query string")
    parser.add_argument(
        "--category",
        choices=list(CATEGORY_ENGINES.keys()) + ["general"],
        default=None,
        help="Search category (default: general)",
    )
    parser.add_argument("--engines", default=None, help="Comma-separated engine list")
    parser.add_argument("--limit", type=int, default=None, help="Max results (default: 6, images/videos: 4)")
    parser.add_argument(
        "--server",
        default=None,
        help=f"SearXNG server URL (default: $SEARXNG_URL or {DEFAULT_SEARXNG_URL})",
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format (default: json)",
    )

    args = parser.parse_args()

    query = args.query.strip()
    if not query:
        print(json.dumps({"error": "query is required"}, ensure_ascii=False))
        sys.exit(1)

    server = args.server or DEFAULT_SEARXNG_URL

    # Resolve limit
    if args.limit is not None:
        limit = max(1, args.limit)
    elif args.category in ("images", "videos"):
        limit = 4
    else:
        limit = DEFAULT_SEARCH_LIMIT

    category = args.category if args.category and args.category != "general" else None

    # Fetch
    data = _fetch_searxng(query, server, category, args.engines)
    if "error" in data:
        print(json.dumps(data, ensure_ascii=False))
        sys.exit(1)

    raw_results = _extract_results(data, 200)
    cleaned = _clean_results(raw_results, limit, category)

    assistant_text = _format_assistant_text(query, cleaned, category)

    output = {
        "query": query,
        "model": "searxng",
        "assistant_text": assistant_text,
        "results": cleaned,
        "limit": limit,
        "total_fetched": len(raw_results),
        "total_after_cleaning": len(cleaned),
    }

    if args.format == "text":
        print(assistant_text)
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
