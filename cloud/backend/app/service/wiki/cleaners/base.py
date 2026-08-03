"""平台清洗基类：通用文本清洗 + JS 渲染页判定 + 各平台正文选择器。

各平台 Cleaner 继承 BaseCleaner 并覆盖：
- `platform`: 平台标识（与前端传入值一致：xiaohongshu/wechat/bilibili/other）
- `NOISE`: 平台专有噪音词（与 COMMON_NOISE 合并后逐行过滤）
- `BODY_SELECTORS`: 该平台正文 DOM 候选选择器（供 playwright 渲染抓取使用）
- 可选重写 `clean_text`：先 super().clean_text() 通用清洗，再做平台特有格式处理

通用清洗规则（clean_text）：
- 剥离 markdown 链接 [文字](url) 保留链接文字；剥离行内图片标记
- 删除平台 UI/导航/版权噪音行与纯符号装饰行；合并多余空行
"""
from __future__ import annotations

import re

# 所有平台共用的噪音词（平台 UI 元素、通用导航、装饰词），单独成行时删除
COMMON_NOISE = {
    "赞", "在看", "分享", "留言", "收藏", "关注", "加载中", "更多", "关于我们",
    "首页", "消息", "我", "取消", "允许", "知道了", "听过", "点击加载更多",
    "正在加载", "登录后查看", "发布于", "编辑于",
}

# JS 渲染页特征词：正文需动态加载，静态抓取只能拿到骨架
JS_RENDER_HINTS = ("加载中", "点击加载更多", "正在加载", "登录后查看")


def _strip_markdown(line: str) -> str:
    """剥离行内 markdown 链接与图片标记，保留文字内容。"""
    line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line).strip()
    line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line).strip()
    return line


# 匹配 <meta property="og:xxx" content="yyy">（兼容属性顺序互换）
_OG_META_RE = re.compile(
    r'<meta[^>]+(?:property=["\']og:(?P<k1>[^"\']+)["\'][^>]*content=["\'](?P<v1>[^"\']*)["\']'
    r'|content=["\'](?P<v2>[^"\']*)["\'][^>]*property=["\']og:(?P<k2>[^"\']+)["\'])',
    re.IGNORECASE,
)


def extract_og(html: str) -> dict[str, list[str]]:
    """提取 HTML 中所有 og: 前缀的 meta 标签（同名多值合并为列表）。"""
    out: dict[str, list[str]] = {}
    for m in _OG_META_RE.finditer(html or ""):
        key = (m.group("k1") or m.group("k2") or "").strip()
        val = (m.group("v1") or m.group("v2") or "").strip()
        if key:
            out.setdefault(key, []).append(val)
    return out


def _abs_url(url: str) -> str:
    """把协议相对链接（//xxx）补成 https://xxx。"""
    u = (url or "").strip()
    if u.startswith("//"):
        return "https:" + u
    return u


def _clean_wechat_url(url: str) -> str:
    """清理微信图片/视频 URL 的懒加载尾参，保留 wx_fmt 与原始路径。

    只清掉 from=appmsg/tp=webp/wxfrom/wx_lazy/#imgIndex 等参数；
    sz_ 前缀/尺寸/格式组合各不相同，不做路径或格式转换。
    """
    u = (url or "").strip()
    if "mmbiz.qpic.cn" not in u:
        return u
    base, _, query = u.partition("?")
    base = base.split("#")[0]
    fmt = ""
    for kv in query.split("&"):
        if kv.startswith("wx_fmt="):
            fmt = kv.split("=", 1)[1]
    return f"{base}?wx_fmt={fmt}" if fmt else base


def meta_by_name(html: str, name: str) -> str | None:
    """按 name 属性取值（如 keywords / description）。"""
    m = re.search(
        rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]*content=["\']([^"\']*)["\']',
        html or "",
        re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


class BaseCleaner:
    platform = "generic"
    NOISE: set[str] = set()
    # 该平台正文的 DOM 候选选择器（按优先级；空表示交给通用选择器）
    BODY_SELECTORS: tuple[str, ...] = ("article", "main")

    @property
    def noise(self) -> set[str]:
        return COMMON_NOISE | self.NOISE

    @property
    def body_selectors(self) -> tuple[str, ...]:
        return self.BODY_SELECTORS

    def extract_meta(self, html: str) -> dict:
        """从页面 HTML 提取结构化元信息（各平台覆盖）。

        约定返回字段（能取到才放）：
        - title: 标题
        - description: 正文描述（可作为正文首选）
        - keywords: 关键词列表
        - images: 正文图片 URL 列表
        - video: 视频地址
        默认空字典；小红书/公众号等平台按自身数据结构覆盖实现。
        """
        return {}

    def clean_text(self, text: str) -> str:
        """清洗抓取/转换出的原始文本：去链接噪音、平台 UI 行、纯符号行。"""
        out: list[str] = []
        for raw in (text or "").splitlines():
            line = _strip_markdown(raw)
            if not line:
                continue
            # 噪音行判断（容忍行首列表符号）
            bare = re.sub(r"^[\s*\-•]+", "", line)
            if (
                bare in self.noise
                or bare.startswith("©")
                or bare.startswith(("地址：", "电话："))
            ):
                continue
            # 纯数字/符号装饰行（页码、分隔）
            if re.fullmatch(r"[0-9\s.,，。;；:：-]+", line) and len(line) < 20:
                continue
            out.append(line)
        return "\n".join(out).strip()

    def looks_like_js_page(self, text: str) -> bool:
        """判断抓取结果是否像 JS 动态渲染页（正文需浏览器执行才能拿到）。

        依据：内容过短 / 出现加载特征词 / 无正文特征行（≥30 字的非标题标签行）。
        """
        clean = (text or "").strip()
        if not clean or len(clean) < 50:
            return True
        if any(h in clean for h in JS_RENDER_HINTS):
            return True
        body_lines = [
            l for l in clean.splitlines()
            if not l.lstrip().startswith(("#", ">", "-", "*")) and len(l) >= 30
        ]
        return not body_lines
