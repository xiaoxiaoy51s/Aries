"""Bilibili 清洗器。

B站视频页的结构化信息分散在 <head> 的 meta 标签里（均带 data-vue-meta）：
- 标题：og:title（或 <title>，带「_哔哩哔哩_bilibili」后缀）
- 描述：meta[name=description]（B站 SEO 摘要，作为正文描述）
- 作者：meta[name=author]（UP主名），缺失时回退到 JSON-LD 的 author.name
- 视频：og:video（player.bilibili.com 播放器地址，非直链 mp4）
- 封面：og:image
"""
from __future__ import annotations

import re

from app.service.wiki.cleaners.base import BaseCleaner, _abs_url, extract_og, meta_by_name


class BilibiliCleaner(BaseCleaner):
    platform = "bilibili"
    NOISE = {
        "哔哩哔哩", "bilibili", "登录后观看", "一键三连", "投币", "弹幕", "点赞",
        "转发", "下载", "UP主", "已注销", "大会员", "充电",
    }
    # 正文候选选择器（B 站视频简介/专栏正文）
    BODY_SELECTORS = (
        "article", "main", ".article-content", ".desc-info", ".basic-desc-info",
    )

    def extract_meta(self, html: str) -> dict:
        """提取B站视频标题 / 描述 / 作者 / 视频 / 封面。"""
        og = extract_og(html)
        out: dict = {}

        # 标题：og:title 优先，回退 <title>，统一去掉「_哔哩哔哩_bilibili」后缀
        titles = og.get("title") or []
        title = titles[0].strip() if titles else ""
        if not title:
            m = re.search(r"<title[^>]*>([\s\S]*?)</title>", html or "", re.IGNORECASE)
            if m:
                title = m.group(1).strip()
        if title:
            title = re.sub(
                r"\s*[_｜|]\s*(?:哔哩哔哩|bilibili).*$",
                "",
                title,
                flags=re.IGNORECASE,
            ).strip()
            if title:
                out["title"] = title

        # 描述：meta[name=description]
        desc = meta_by_name(html, "description")
        if desc:
            out["description"] = desc.strip()

        # 作者：meta[name=author]（UP主名），缺失时回退 JSON-LD author.name
        author = meta_by_name(html, "author")
        if not author:
            m = re.search(r'"author"\s*:\s*\{[^}]*?"name"\s*:\s*"([^"]+)"', html or "")
            if m:
                author = m.group(1)
        if author:
            out["author"] = author.strip()

        # 视频：og:video（播放器地址，非直链，仅作元信息）
        video = _abs_url((og.get("video") or [""])[0])
        if video:
            out["video"] = video.strip()

        # 封面：og:image
        imgs = og.get("image") or []
        if imgs:
            out["images"] = [_abs_url(u) for u in imgs]

        return out
