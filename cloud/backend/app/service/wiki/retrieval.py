"""BM25 纯文本检索（替代向量检索）。

设计（对应"文本搜索 + AI 记忆"）：
- 中文按字符 bigram 分词（无需分词器依赖），英文/数字按词。
- BM25 打分排序（k1=1.5, b=0.75），标题重复加权，命中标题的文档得分更高。
- 检索范围是 wiki/ 下全部 md 文档（单用户文档量小，全量扫描足够快）。
"""
from __future__ import annotations

import asyncio
import math
import re
from pathlib import Path

from app.config.settings import settings
from app.service.wiki.workspace import WikiWorkspace

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_META_RE = re.compile(r'^(title|tags):\s*(.+)$', re.MULTILINE)


def tokenize(text: str) -> list[str]:
    """中文 bigram + 英文/数字词。"""
    tokens: list[str] = []
    for seg in _CJK_RE.findall(text):
        seg = seg.strip()
        if len(seg) == 1:
            tokens.append(seg)
        else:
            for i in range(len(seg) - 1):
                tokens.append(seg[i : i + 2])
    for w in _WORD_RE.findall(text):
        tokens.append(w.lower())
    return tokens


def _parse_frontmatter(md: str) -> tuple[str, list[str], str]:
    """解析 frontmatter 中的 title/tags，返回 (title, tags, body)。"""
    m = _FRONTMATTER_RE.match(md)
    if not m:
        return "", [], md
    fm = m.group(1)
    title = ""
    tags: list[str] = []
    for line in fm.splitlines():
        lm = _META_RE.match(line.strip())
        if not lm:
            continue
        key, val = lm.group(1), lm.group(2).strip().strip('"\'')
        if key == "title":
            title = val
        elif key == "tags" and val.startswith("["):
            tags = [t.strip().strip("'\"") for t in val[1:-1].split(",") if t.strip()]
    return title, tags, md[m.end():]


class BM25Index:
    def __init__(self, docs: list[dict], k1: float = 1.5, b: float = 0.75):
        """docs: [{path, title, body}]"""
        self.k1 = k1
        self.b = b
        self.doc_count = len(docs)
        self.dl: list[int] = []
        self.tf: list[dict[str, int]] = []
        self.df: dict[str, int] = {}
        avg_len = 0.0
        for d in docs:
            # 标题重复加权（标题命中更重要）
            title_tokens = tokenize(d.get("title") or "")
            tokens = title_tokens * 3 + tokenize(d.get("body") or "")
            tf: dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            self.tf.append(tf)
            dl = len(tokens)
            self.dl.append(dl)
            avg_len += dl
            for t in set(tf):
                self.df[t] = self.df.get(t, 0) + 1
        self.avgdl = avg_len / self.doc_count if self.doc_count else 1.0

    def search(self, query: str, top_k: int = 8) -> list[tuple[int, float]]:
        """返回 [(doc_idx, score)] 降序。"""
        q_tokens = set(tokenize(query))
        if not q_tokens or self.doc_count == 0:
            return []
        scores: list[float] = [0.0] * self.doc_count
        for t in q_tokens:
            df = self.df.get(t, 0)
            if df == 0:
                continue
            idf = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1.0)
            for i, tf_map in enumerate(self.tf):
                tf = tf_map.get(t, 0)
                if not tf:
                    continue
                dl = self.dl[i]
                denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                scores[i] += idf * (tf * (self.k1 + 1)) / denom
        ranked = sorted(range(self.doc_count), key=lambda i: scores[i], reverse=True)
        return [(i, scores[i]) for i in ranked if scores[i] > 0][:top_k]


def _load_doc(ws: WikiWorkspace, p: Path) -> dict | None:
    try:
        md = p.read_text(encoding="utf-8")
    except OSError:
        return None
    title, tags, body = _parse_frontmatter(md)
    return {
        "path": ws.rel_path(p),
        "title": title or p.stem,
        "tags": tags,
        "content_md": md,
        "body": body,
    }


async def retrieve(user_email: str, question: str, *, top_k: int | None = None) -> list[dict]:
    """BM25 检索 wiki 文档，返回 [{file_path, title, tags, content_md, score, via}]。"""
    top_k = top_k or settings.KB_TOP_K
    ws = WikiWorkspace(user_email).ensure()
    paths = ws.all_pages()
    if not paths:
        return []

    docs = await asyncio.gather(
        *[asyncio.to_thread(_load_doc, ws, p) for p in paths]
    )
    docs = [d for d in docs if d and (d["body"] or "").strip()]
    if not docs:
        return []

    index = BM25Index(docs)
    ranked = index.search(question, top_k)
    results = []
    for i, score in ranked:
        d = docs[i]
        results.append(
            {
                "file_path": d["path"],
                "title": d["title"],
                "tags": d["tags"],
                "content_md": d["content_md"],
                "score": round(score, 4),
                "via": "text",
            }
        )
    return results
