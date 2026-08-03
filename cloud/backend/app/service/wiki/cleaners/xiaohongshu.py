"""小红书清洗器。

小红书的页面数据规整地放在 og: 前缀的 meta 标签里（og:title / og:description /
og:image / keywords / og:video），结构固定，因此核心是结构化 meta 提取，
而非噪音词过滤。正文描述取 og:description（即完整正文），图片取 og:image。
"""
from __future__ import annotations

import re

from app.service.wiki.cleaners.base import BaseCleaner, _abs_url, extract_og, meta_by_name


class XiaohongshuCleaner(BaseCleaner):
    platform = "xiaohongshu"
    NOISE = {
        "创作中心", "业务合作", "发现", "RED", "直播", "发布", "通知",
        "行吟信息科技（上海）有限公司", "登录后推荐更懂你的笔记", "可用", "扫码",
        "手机号登录", "获取验证码", "登录", "小红书", "新用户可直接登录",
    }
    # 正文候选选择器（playwright 渲染兜底时使用）
    BODY_SELECTORS = (".note-content", "#detail-desc", "article", "main")

    def extract_meta(self, html: str) -> dict:
        """解析小红书 og meta 标签：标题 / 正文描述 / 图片 / 关键词 / 视频。"""
        og = extract_og(html)
        out: dict = {}

        titles = og.get("title") or []
        if titles:
            # og:title 形如「标题 - 小红书」，去掉平台后缀
            title = re.sub(r"\s*-\s*小红书\s*$", "", titles[0]).strip()
            if title:
                out["title"] = title

        descs = og.get("description") or []
        if descs:
            out["description"] = descs[0].strip()

        kws = og.get("keywords") or []
        if not kws:
            kw = meta_by_name(html, "keywords")
            if kw:
                kws = [kw]
        if kws:
            out["keywords"] = [
                k.strip() for k in kws[0].split(",") if k.strip()
            ]

        imgs = og.get("image") or []
        if imgs:
            out["images"] = [_abs_url(u) for u in imgs]

        video = _abs_url(
            (
                og.get("video")
                or og.get("video:url")
                or og.get("video:secure_url")
                or [""]
            )[0]
        )
        if video:
            out["video"] = video

        return out
