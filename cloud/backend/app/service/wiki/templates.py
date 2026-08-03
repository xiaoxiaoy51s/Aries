"""来源元数据与 frontmatter 构造（单文档方案）。

设计要点（对应"一个链接/一个文件 -> 一个 md"）：
- 每个来源只生成 1 个（或内容超长时少数几个）md 文档，AI 决定文件路径与标题。
- frontmatter 确定性字段由代码注入（title/tags/source 元数据/last_updated），LLM 不生成 frontmatter。
- 正文不超过 KB_DOC_MAX_CHARS（约 3000 字），超出拆成多个 md。
- 文件夹由 AI 按内容语义自由组织（如 编程/Python/），类似人类整理文件夹。
"""
from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel

from app.utils.time_utils import local_now_str


class SourceMeta(BaseModel):
    """来源元数据，由调用方填充、代码注入进 frontmatter。"""

    source_type: str = "personal"       # online | local_file | personal
    platform: str = ""                  # bilibili/wechat/xiaohongshu/...
    original_url: str = ""
    author: str = ""
    publish_date: str = ""
    file_name: str = ""
    file_type: str = ""                 # pdf / docx / pptx / xlsx
    file_digest: str = ""               # 文件哈希，去重
    raw_file: str = ""                  # 原始文件相对 user_home 的路径（溯源用）
    source_label: str = "用户输入"
    # 平台结构化字段（小红书等从 og/meta 标签提取，图片/音视频后续走云端 API）
    title: str = ""                     # 原始标题（AI 整理时参考，仍可重命名）
    keywords: list[str] = []            # 平台关键词/标签
    video: str = ""                     # 视频地址
    images: list[str] = []              # 正文图片 URL 列表


# 单文档 wiki 约定（写入 ingest prompt）
SCHEMA = """\
知识库整理约定：
- 一个来源只生成一个 md 文档（内容超长可拆成少数几个），不要再拆分出 entity/concept 等多页。
- 你要决定文件放在哪个文件夹：按内容语义组织，类似人类整理文件夹（如 编程/Python/、学习/数学/、日记/），可复用已有文件夹，也可新建合理的文件夹。
- 标题要清晰、具体、能概括内容，方便只看标题就知道文档讲了什么（如「用 Python 异步爬取 B 站视频字幕」），禁止用「链接1」「未命名」这类。
- 正文控制在 3000 字以内（去掉空格/换行后约 3000 个汉字）。若内容超长，拆成多个 md：第一个为总览（摘要+目录+关键结论），后续为各个部分的详细内容，文件名带序号。
- 正文用 markdown 结构化书写（## 小节），把来源原文中的关键信息整理进正文，保留重要细节、数字、结论。
- 整理时清除无关紧要的内容：广告、推广、公告、活动报名、引导关注/点赞/转发、评论区、导航链接等噪音一律剔除，只保留有知识价值的信息。
- 清除图片链接与 URL（不要保留 ![]() 图片引用、纯链接行、二维码/海报识别出的无意义文本）；图片里的有效文字信息已由 OCR 提取进正文，直接保留其文字即可。
- 用 [[文件名]] 内联链接到知识库中其他相关文档（只链接已存在或本次新增的文件名）。
- 不要生成 frontmatter，frontmatter 由系统注入。
"""

# 通用正文模板（AI 按来源类型灵活调整小节，不强制）
TEMPLATE = """\
## 内容摘要
2~4 句客观概括全文/全片主旨。

## 关键内容
- 要点 1（保留重要细节与数字）
- 要点 2

## 摘录 / 引用
> 原文关键片段（无则删除此小节）

## 关联文档
- [[相关文档]]：简短关联说明
"""


def build_frontmatter(meta: SourceMeta, title: str, *, tags: list[str] | None = None) -> dict[str, Any]:
    """构造单文档 frontmatter dict（含来源溯源字段）。"""
    fm: dict[str, Any] = {
        "title": title or "",
        "tags": tags or [],
        "last_updated": local_now_str(),
    }
    if meta.source_type:
        fm["source_type"] = meta.source_type
    if meta.source_type == "online":
        if meta.platform:
            fm["platform"] = meta.platform
        if meta.original_url:
            fm["original_url"] = meta.original_url
        if meta.author:
            fm["author"] = meta.author
        if meta.publish_date:
            fm["publish_date"] = meta.publish_date
        # 平台结构化字段（title/keywords/video/images）写进 frontmatter 溯源
        if meta.title:
            fm["source_title"] = meta.title
        if meta.keywords:
            fm["keywords"] = meta.keywords
        if meta.video:
            fm["video"] = meta.video
        if meta.images:
            fm["images"] = meta.images
    elif meta.source_type == "local_file":
        if meta.file_name:
            fm["file_name"] = meta.file_name
        if meta.file_type:
            fm["file_type"] = meta.file_type
        if meta.file_digest:
            fm["file_digest"] = meta.file_digest
        if meta.raw_file:
            fm["raw_file"] = meta.raw_file
    elif meta.source_label and meta.source_type == "personal":
        fm["source_label"] = meta.source_label
    if meta.original_url:
        fm.setdefault("original_url", meta.original_url)
    if meta.author:
        fm.setdefault("author", meta.author)
    return fm


def to_frontmatter_block(fm: dict[str, Any]) -> str:
    """dict -> YAML frontmatter 文本块。"""
    body = yaml.safe_dump(
        fm, allow_unicode=True, sort_keys=False, default_flow_style=False
    ).strip()
    return f"---\n{body}\n---\n"
