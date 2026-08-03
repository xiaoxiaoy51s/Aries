"""微信公众号清洗器。

公众号文章页与小红书不同：正文并不写在 og meta 标签里，而是静态内嵌在
<div id="js_content"> 节点中，页面其余部分充满脚本/样式噪音。因此核心是
用标准库 HTMLParser 从 js_content 节点内抽取正文文本、图片真实地址
（公众号正文图片为懒加载，真实地址在 data-src 而非 src）与视频地址。
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

from app.service.wiki.cleaners.base import BaseCleaner, _abs_url, _clean_wechat_url, meta_by_name

# 正文内的块级/换行标签：出现时视为换行
_BREAK_TAGS = {
    "p", "br", "section", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "blockquote", "tr", "figure",
}


class _JsContentExtractor(HTMLParser):
    """抽取公众号页面 #js_content 节点的文本与图片/视频地址。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_content = False     # 是否在 #js_content 内
        self.depth = 0              # #js_content 的嵌套深度
        self.in_script_style = False
        self.parts: list[str] = []  # 文本块（'' 表示换行标记）
        self.video = ""

    def _break(self):
        if self.parts and self.parts[-1] != "":
            self.parts.append("")

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if not self.in_content:
            if tag == "div" and a.get("id") == "js_content":
                self.in_content = True
                self.depth = 1
            return
        if tag == "div":
            self.depth += 1
        if tag in _BREAK_TAGS:
            self._break()
        elif tag == "img":
            self._break()
        elif tag == "video":
            src = (
                a.get("data-original")
                or a.get("data-src")
                or a.get("src")
                or ""
            ).strip()
            if src and not src.startswith("data:") and not self.video:
                self.video = src
        elif tag in ("script", "style"):
            self.in_script_style = True

    def handle_endtag(self, tag):
        if not self.in_content:
            return
        if tag == "div":
            self.depth -= 1
            if self.depth <= 0:
                self.in_content = False
        elif tag in _BREAK_TAGS:
            self._break()
        elif tag in ("script", "style"):
            self.in_script_style = False

    def handle_data(self, data):
        if self.in_content and not self.in_script_style:
            if data.strip():
                self.parts.append(data)

    def body(self) -> str:
        """拼接正文文本：相邻文本块合并为一行，''（换行标记）分隔段落。"""
        lines: list[str] = []
        buf = ""
        for part in self.parts:
            if part == "":
                text = " ".join(buf.split()).strip()
                if text:
                    lines.append(text)
                buf = ""
            else:
                buf += part
        if buf.strip():
            lines.append(" ".join(buf.split()).strip())
        return "\n".join(lines)


def _extract_rich_title(html: str) -> str:
    """从 h1#activity-name / .rich_media_title 提取公众号文章标题（静态 HTML 即含）。"""
    m = re.search(
        r'<h1[^>]*?(?:id=["\']activity-name["\']|class=["\'][^"\']*rich_media_title[^"\']*["\'])[^>]*>'
        r"([\s\S]*?)</h1>",
        html or "",
        re.IGNORECASE,
    )
    if not m:
        return ""
    text = re.sub(r"<[^>]+>", "", m.group(1))  # 去内部标签
    return " ".join(text.split())


# 公众号正文真实图片为 jpeg（sz_mmbiz_jpg.../wx_fmt=jpeg）；img data-src 里的 png
# 是缩略占位图。jpeg 原图可能出现在 img 的 src / data-src，也可能内联在 js 变量中
# （带 \x26 / &amp; 转义），因此用正则在整段 HTML 文本中抓取 wx_fmt=jpeg 链接。
_JPEG_IMG_RE = re.compile(r'https?://[^\s"\'<>\\]*?wx_fmt=jpeg[^\s"\'<>\\]*', re.IGNORECASE)


def _decode_img_url(u: str) -> str:
    """解码 HTML 实体与 js 字符串转义，得到可直接请求的图片 URL。"""
    u = u.replace("\\x26", "&").replace("\\x22", '"')
    u = u.replace("&amp;", "&").replace("&#38;", "&")
    return u


def _extract_jpeg_images(html: str) -> list[str]:
    """提取公众号 HTML 中所有 wx_fmt=jpeg 的真实图片链接。

    页面中 png 缩略占位（img data-src）与 jpeg 原图（img src / 内联 js）并存，
    只有 jpeg 是真实内容。正则覆盖 img 属性与 js 内联，解码转义、清懒加载尾参后去重。
    """
    seen: set[str] = set()
    out: list[str] = []
    for m in _JPEG_IMG_RE.finditer(html or ""):
        u = _clean_wechat_url(_decode_img_url(_abs_url(m.group(0))))
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


class WechatCleaner(BaseCleaner):
    platform = "wechat"
    NOISE = {
        "微信扫一扫", "关注该公众号", "使用小程序", "使用完整服务", "预览时标签不可点",
        "跳转二维码", "作者头像", "原创", "去阅读", "在小说阅读器读本章",
        "在小说阅读器中沉浸阅读", "左右滑动查看更多精彩内容", "左右滑动查看更多",
        "扫描二维码", "长按识别二维码", "阅读原文", "已同步到看一看",
    }
    # 正文候选选择器（playwright 渲染兜底时使用）
    BODY_SELECTORS = (".rich_media_content", "#js_content", "article", "main")

    def extract_meta(self, html: str) -> dict:
        """提取公众号标题 / 正文 / 图片 / 视频。

        - title: meta[name=og:title] > <title>，去掉「_公众号名」后缀
        - description: #js_content 节点内的完整正文
        - images: 正文 wx_fmt=jpeg 真实图（正则提取，跳过 png 缩略占位）
        - video: 正文内 <video> 的 data-src/src
        - author: meta[name=author]
        """
        out: dict = {}

        title = (meta_by_name(html, "og:title") or "").strip()
        if not title:
            title = _extract_rich_title(html)  # h1#activity-name / .rich_media_title（纯标题）
        from_title_tag = False
        if not title:
            m = re.search(r"<title[^>]*>([\s\S]*?)</title>", html or "", re.IGNORECASE)
            if m:
                title = m.group(1).strip()
                from_title_tag = True
        if title:
            # 仅 <title> 兜底场景才去「标题_公众号名」后缀（og:title / h1 是纯标题，避免误删）
            if from_title_tag:
                title = re.sub(r"[_|｜，,]+[^_|｜，,]+$", "", title).strip()
            if title:
                out["title"] = title

        author = meta_by_name(html, "author") or ""
        if author and author.strip():
            out["author"] = author.strip()

        extractor = _JsContentExtractor()
        extractor.feed(html or "")
        body = self.clean_text(extractor.body())
        if body:
            out["description"] = body
        imgs = _extract_jpeg_images(html)
        if imgs:
            out["images"] = imgs
        if extractor.video:
            out["video"] = _clean_wechat_url(_abs_url(extractor.video))
        return out
