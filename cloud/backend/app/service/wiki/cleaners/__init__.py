"""平台清洗包：按平台拆分抓取文本的清洗规则与正文选择器。

- `get_cleaner(platform)` 根据平台标识返回对应 Cleaner（未识别回退 GenericCleaner）
- 每个 Cleaner 继承 BaseCleaner：`clean_text` 通用清洗 + `NOISE` 平台噪音 + `BODY_SELECTORS` 正文选择器
- 新增平台：在 `_CLEANERS` 注册即可，无需改动调用方
"""
from __future__ import annotations

from app.service.wiki.cleaners.base import BaseCleaner
from app.service.wiki.cleaners.bilibili import BilibiliCleaner
from app.service.wiki.cleaners.generic import GenericCleaner
from app.service.wiki.cleaners.wechat import WechatCleaner
from app.service.wiki.cleaners.xiaohongshu import XiaohongshuCleaner

_CLEANERS: dict[str, type[BaseCleaner]] = {
    c.platform: c
    for c in (
        XiaohongshuCleaner,
        WechatCleaner,
        BilibiliCleaner,
        GenericCleaner,
    )
}

# 别名：前端可能传英文全名/简写，统一归一
_ALIASES = {
    "xhs": "xiaohongshu",
    "red": "xiaohongshu",
    "wechat": "wechat",
    "weixin": "wechat",
    "wx": "wechat",
    "gzh": "wechat",
    "bili": "bilibili",
    "other": "generic",
    "": "generic",
}


def get_cleaner(platform: str = "") -> BaseCleaner:
    """返回平台对应的 Cleaner（未识别回退 GenericCleaner）。"""
    key = (platform or "").strip().lower()
    key = _ALIASES.get(key, key)
    cls = _CLEANERS.get(key, GenericCleaner)
    return cls()


# 常见平台域名 -> 规范平台标识（用于前端未显式选平台时自动推断）
_DOMAIN_PLATFORM = (
    ("xiaohongshu.com", "xiaohongshu"),
    ("mp.weixin.qq.com", "wechat"),
    ("bilibili.com", "bilibili"),
)


def infer_platform(url: str = "", platform: str = "") -> str:
    """推断平台：显式传了 platform 用之，否则按 URL 域名匹配。"""
    if platform and platform.strip():
        return platform.strip()
    low = (url or "").lower()
    for domain, name in _DOMAIN_PLATFORM:
        if domain in low:
            return name
    return ""


__all__ = ["BaseCleaner", "GenericCleaner", "get_cleaner", "infer_platform"]
