"""摄取：源文本 -> LLM 整理成 md 文档（AI 定文件夹/标题/正文）-> 写 wiki + 更新所在文件夹索引。

索引机制（每文件夹一份 _index.md）：
- 每个文件夹内有一份 _index.md：用途说明 + 子目录入口 + 文档摘要清单。
- 顶层 wiki/_index.md 为总入口。
- 单文件夹文档数超过 KB_DIR_MAX_FILES 时，AI 基于现有 _index.md 的摘要
  生成分组迁移计划，代码执行 move（不重新读 md 正文），并更新源/目标索引。
"""
from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

from app.config.settings import settings
from app.service.model_config_service import ModelConfigService
from app.service.wiki import llm
from app.service.wiki.templates import SCHEMA, TEMPLATE, SourceMeta, build_frontmatter, to_frontmatter_block
from app.service.wiki.workspace import WikiWorkspace, _META_EXCLUDE

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n?", re.DOTALL)

# 同用户 ingest 串行锁，防止并发任务同时写索引/迁移目录
_user_locks: dict[str, asyncio.Lock] = {}


def _lock_for(email: str) -> asyncio.Lock:
    lock = _user_locks.get(email)
    if lock is None:
        lock = asyncio.Lock()
        _user_locks[email] = lock
    return lock


def strip_frontmatter(md: str) -> str:
    return _FRONTMATTER_RE.sub("", md, count=1)


async def _read(path: Path) -> str:
    def _r() -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    return await asyncio.to_thread(_r)


async def _write(path: Path, content: str) -> None:
    def _w() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    await asyncio.to_thread(_w)


def _safe_name(name: str) -> str:
    """文件名去非法字符。"""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name or "").strip(" .")
    return name or "untitled"


async def _unique_path(ws: WikiWorkspace, rel: str) -> str:
    """若文件已存在则加序号后缀，避免覆盖。"""
    target = ws.safe_join(rel)
    if target is None:
        raise ValueError(f"非法文件路径: {rel}")
    if not target.exists():
        return rel
    p = Path(rel)
    stem, suffix = p.stem, p.suffix
    for i in range(2, 100):
        cand = str(p.with_name(f"{stem}-{i}{suffix}"))
        if ws.safe_join(cand) and not ws.safe_join(cand).exists():
            return cand
    return rel  # 兜底直接覆盖


# ==================== 索引读写 ====================

def _parse_index(content: str) -> tuple[str, list[str], list[str]]:
    """解析 _index.md，返回 (head, subdir_lines, doc_lines)。

    head 为标题与用途说明（## 子目录 之前的所有内容）；
    文档条目形如 `- [标题](相对路径)｜摘要`。
    """
    head: list[str] = []
    subdir: list[str] = []
    docs: list[str] = []
    section = "head"
    for line in (content or "").splitlines():
        if line.strip() == "## 子目录":
            section = "subdir"
            continue
        if line.strip() == "## 文档":
            section = "docs"
            continue
        if section == "head":
            head.append(line)
        elif section == "subdir":
            if line.strip():
                subdir.append(line)
        else:
            if line.strip():
                docs.append(line)
    return "\n".join(head).strip(), subdir, docs


def _entry_path(entry: str) -> str | None:
    """从索引条目提取相对路径。"""
    m = re.search(r"\]\(([^)]+)\)", entry)
    return m.group(1).strip() if m else None


def _render_index(rel_dir: str, purpose: str, subdir: list[str], docs: list[str]) -> str:
    lines = [f"# _index {rel_dir or '根目录'}", ""]
    if purpose:
        lines += [f"> {purpose}", ""]
    if subdir:
        lines += ["## 子目录", *subdir, ""]
    lines += ["## 文档", *docs, ""]
    return "\n".join(lines).rstrip() + "\n"


async def _index_path_for(ws: WikiWorkspace, rel_dir: str) -> Path:
    """返回 rel_dir（相对 wiki，'' 表示根）对应的 _index.md 路径。"""
    if not rel_dir or rel_dir == ".":
        return ws.index_file
    folder = ws.safe_join(rel_dir)
    if folder is None:
        raise ValueError(f"非法文件夹路径: {rel_dir}")
    return ws.index_for(folder)


async def _update_index(ws: WikiWorkspace, entries: list[dict]) -> None:
    """把文档条目写进各自所在文件夹的 _index.md。

    entries: [{folder: "编程/Python", entry: "- [标题](路径)｜摘要"}]
    同名条目（按路径）替换，否则追加。不影响用途说明与子目录段。
    """
    if not entries:
        return
    by_folder: dict[str, list[str]] = {}
    for e in entries:
        folder = (e.get("folder") or "").strip()
        entry = (e.get("entry") or "").strip()
        if not entry:
            continue
        by_folder.setdefault(folder, []).append(entry)

    for folder, adds in by_folder.items():
        path = await _index_path_for(ws, folder)
        content = await _read(path)
        head, subdir, docs = _parse_index(content)
        for entry in adds:
            pkey = _entry_path(entry) or entry
            replaced = False
            for i, ln in enumerate(docs):
                if (_entry_path(ln) or "") == pkey:
                    docs[i] = entry
                    replaced = True
                    break
            if not replaced:
                docs.append(entry)
        await _write(path, _render_index(folder, _purpose_of(head), subdir, docs))


async def remove_doc_from_index(ws: WikiWorkspace, rel: str) -> None:
    """删除 rel 所在文件夹 _index.md 中指向 rel 的条目。"""
    p = Path(rel)
    folder = str(p.parent.as_posix()) if p.parent != Path(".") else ""
    path = await _index_path_for(ws, folder)
    content = await _read(path)
    head, subdir, docs = _parse_index(content)
    kept = [ln for ln in docs if (_entry_path(ln) or "") != rel]
    if len(kept) != len(docs):
        await _write(path, _render_index(folder, _purpose_of(head), subdir, kept))


def _purpose_of(head: str) -> str:
    """从 head 段提取用途说明（`>` 开头的行）。"""
    return "\n".join(
        ln.strip().lstrip(">").strip() for ln in (head or "").splitlines()
        if ln.strip().startswith(">")
    ).strip()


def _subdir_entry(ws: WikiWorkspace, child_folder: Path) -> str:
    """生成子目录条目：- [[相对路径]]｜主题（从子目录 _index.md 用途行提取）。"""
    rel = ws.rel_path(child_folder)
    try:
        content = (child_folder / "_index.md").read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^>\s*(.+)$", content, re.MULTILINE)
        summary = m.group(1).strip() if m else ""
    except OSError:
        summary = ""
    return f"- [[{rel}]]｜{summary}" if summary else f"- [[{rel}]]"


def _has_docs_under(folder: Path, pages: list[Path]) -> bool:
    """folder 下（任意深度）是否有知识文档。"""
    return any(folder in p.parents for p in pages)


async def _sync_one_folder(ws: WikiWorkspace, folder: Path, path_set: set[str], pages: list[Path]) -> None:
    """对齐单个文件夹的 _index.md：清理失效条目、补新增文档、重建子目录段。"""
    rel_dir = ws.rel_path(folder)
    index_path = ws.index_for(folder)
    content = await _read(index_path)
    head, _subdir, docs = _parse_index(content)

    indexed: set[str] = set()
    kept: list[str] = []
    for ln in docs:
        p = _entry_path(ln)
        if p and p not in path_set:
            continue
        if p:
            indexed.add(p)
        kept.append(ln)
    for p in sorted(path_set):
        if ws.safe_join(p).parent == folder and p not in indexed:
            title = _frontmatter_title(ws, p) or Path(p).stem
            kept.append(f"- [{title}]({p})｜{title}")

    subdirs = []
    for child in sorted(folder.iterdir(), key=lambda c: c.name):
        if child.is_dir() and _has_docs_under(child, pages):
            subdirs.append(_subdir_entry(ws, child))
    await _write(index_path, _render_index(rel_dir, _purpose_of(head), subdirs, kept))


async def sync_index(ws: WikiWorkspace) -> None:
    """递归对齐所有文件夹 _index.md 与实际文件（无需 LLM，成本极低）。

    对每个文件夹：删除失效文档条目、为新增文档用 title 兜底补条目、
    重建「子目录」段（从子目录 _index.md 提取主题）。用途说明保留 AI 维护的内容。
    """
    pages = ws.all_pages()
    path_set = {ws.rel_path(p) for p in pages}
    folders = {p.parent for p in pages}

    for folder in folders:
        await _sync_one_folder(ws, folder, path_set, pages)

    # 顶层 _index.md
    root_content = await _read(ws.index_file)
    head, _subdir, docs = _parse_index(root_content)
    indexed_root = set()
    kept_root = []
    for ln in docs:
        p = _entry_path(ln)
        if p and p not in path_set:
            continue
        if p:
            indexed_root.add(p)
        kept_root.append(ln)
    for p in sorted(path_set):
        if ws.safe_join(p).parent == ws.root and p not in indexed_root:
            title = _frontmatter_title(ws, p) or Path(p).stem
            kept_root.append(f"- [{title}]({p})｜{title}")
    subdirs_root = [_subdir_entry(ws, c) for c in sorted(ws.root.iterdir(), key=lambda c: c.name)
                    if c.is_dir() and _has_docs_under(c, pages)]
    await _write(ws.index_file, _render_index("", _purpose_of(head), subdirs_root, kept_root))


def _frontmatter_title(ws: WikiWorkspace, rel: str) -> str | None:
    target = ws.safe_join(rel)
    if not target or not target.exists():
        return None
    try:
        md = target.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    m = re.search(r'^title:\s*"?([^"\n]+)"?', md, re.MULTILINE)
    return m.group(1).strip() if m else None


# ==================== 目录过载迁移 ====================

async def _maybe_reorganize(ws: WikiWorkspace, model) -> None:
    """单文件夹文档数超阈值时，AI 基于现有 _index.md 分组，代码 move 迁移并更新索引。

    迁移只读文件夹 _index.md 的摘要，不读 md 正文；move 而非 copy。
    """
    threshold = settings.KB_DIR_MAX_FILES
    for _ in range(10):  # 循环处理可能出现的嵌套过载，限制深度
        overloaded = []
        for folder in ws.all_folders():
            files = [p for p in folder.glob("*.md") if p.name not in _META_EXCLUDE]
            if len(files) > threshold:
                overloaded.append(folder)
        if not overloaded:
            return

        folder = overloaded[0]
        rel_dir = ws.rel_path(folder)
        idx = await _read(ws.index_for(folder))
        files = sorted(ws.rel_path(p) for p in folder.glob("*.md") if p.name not in _META_EXCLUDE)
        if len(files) <= threshold:
            return

        prompt = f"""知识库目录「{rel_dir}」文档过多，需要按语义拆分成 2~5 个子目录。
基于下面的 _index.md 摘要（不要读 md 正文）为每个文件分配新的子目录，并保留原文摘要。

{idx or '（无索引）'}

只返回 JSON：{{"groups": [
  {{"folder": "子目录名（只填这一层，不含父路径）", "summary": "子目录一句话主题",
   "entries": [{{"file": "原相对路径", "new_path": "新相对路径（{rel_dir}/子目录名/原文件名）", "entry": "- [标题](新相对路径)｜原摘要"}}]}}
]}}
每个文件必须且只能出现在一个 groups 里；groups 覆盖全部 {len(files)} 个文件。"""
        data = await llm.chat_json(model, [{"role": "user", "content": prompt}], max_tokens=8192)

        groups = data.get("groups") or []
        if not groups:
            return
        # 1. move 文件
        for g in groups:
            sub = (g.get("folder") or "").strip().strip("/")
            for ent in g.get("entries") or []:
                src_rel = ent.get("file") or ""
                new_rel = ent.get("new_path") or ""
                src = ws.safe_join(src_rel)
                dst = ws.safe_join(new_rel)
                if src and dst and src.exists() and src != dst:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    await asyncio.to_thread(shutil.move, str(src), str(dst))
        # 2. 写新子目录 _index.md（用 AI 返回的摘要条目）
        for g in groups:
            sub = (g.get("folder") or "").strip().strip("/")
            entries = [e.get("entry") for e in g.get("entries") or [] if e.get("entry")]
            new_dir_rel = f"{rel_dir}/{sub}" if rel_dir else sub
            new_index = ws.safe_join(f"{new_dir_rel}/_index.md")
            if new_index:
                await _write(
                    new_index,
                    _render_index(new_dir_rel, g.get("summary") or "", [], entries),
                )
        # 3. 源目录 _index.md 清理已迁移条目，sync 重建子目录段
        await sync_index(ws)


# ==================== 摄取主流程 ====================

def _existing_structure(ws: WikiWorkspace) -> str:
    """生成现有目录结构摘要（文件夹 + 文件数 + 标题），供 AI 复用文件夹。"""
    pages = ws.all_pages()
    if not pages:
        return "（知识库为空，这是第一个来源）"
    lines: list[str] = []
    by_dir: dict[Path, list[Path]] = {}
    for p in pages:
        by_dir.setdefault(p.parent, []).append(p)
    for d in sorted(by_dir, key=lambda x: ws.rel_path(x)):
        files = ", ".join(f"「{p.stem}」" for p in by_dir[d])
        lines.append(f"- {ws.rel_path(d)}/: {files}")
    return "\n".join(lines)


async def ingest_source(user_email: str, source_text: str, meta: SourceMeta) -> dict:
    """摄取一段源文本：AI 整理成 md 写入 wiki 并更新所在文件夹索引。返回摘要。"""
    async with _lock_for(user_email):
        ws = WikiWorkspace(user_email).ensure()
        # 摄取前先对齐记忆索引与实际文件（用户可能手动增删过）
        await sync_index(ws)
        model = await ModelConfigService.get_active_model(user_email)
        if not model:
            raise RuntimeError("尚未配置模型，请先在设置中添加模型")

        # 目录过载自动重组（move 迁移 + 双索引更新）
        await _maybe_reorganize(ws, model)

        idx = await _read(ws.index_file)
        structure = _existing_structure(ws)
        max_chars = settings.KB_DOC_MAX_CHARS

        source_info = {
            "source_type": meta.source_type,
            "platform": meta.platform,
            "file_type": meta.file_type,
            "source_label": meta.source_label,
            # 平台结构化字段（小红书 og 提取；标题供参考，关键词可作 tags）
            "original_title": meta.title,
            "keywords": meta.keywords,
            "video": meta.video,
            "images_count": len(meta.images),
        }
        prompt = f"""你在维护一个纯文件系统的知识库，把下面的源内容整理成 md 文档存进合适的文件夹。

{SCHEMA}

索引规则：
- 每个文件夹内有一份 _index.md（用途说明 + 子目录入口 + 文档摘要）。顶层 _index.md 是总入口。
- 新文档写入后，你要在它所在文件夹的 _index.md 的「文档」段新增一条：- [标题](相对路径)｜一句话摘要。
- 优先复用已有文件夹；文件夹文档数接近 {settings.KB_DIR_MAX_FILES} 时考虑新建更深层的子文件夹分流。

单个 md 正文上限 {max_chars} 字。内容超长必须拆成多个 md（第一个为总览，其余按部分拆分，文件名带 -1/-2 序号）。

正文模板参考（按来源类型灵活调整，不必死板套用）：
{TEMPLATE}

来源元数据（由系统注入 frontmatter，你不要生成 frontmatter）：
{source_info}

顶层记忆索引（了解已有文件夹用途）：
{idx or '（空）'}

当前目录结构（文件名列表，避免与已有文档重名）：
{structure}

新源内容（来源：{meta.source_label}）：
=== SOURCE START ===
{source_text}
=== SOURCE END ===

只返回一个合法 JSON 对象（不要 markdown fence，不要 JSON 外的文字）：
{{
  "files": [
    {{
      "path": "文件夹/文件名.md（相对 wiki 根，文件夹用 / 分层；正文很长则拆多个文件）",
      "title": "清晰具体的人类可读标题",
      "tags": ["标签"],
      "body": "md 正文（不含 frontmatter，≤{max_chars} 字；markdown 结构化；关键信息/数字/结论都要保留）"
    }}
  ],
  "index_entries": [
    {{"folder": "文件所在文件夹相对路径（如 编程/Python，根目录则留空）", "entry": "- [标题](文件相对路径.md)｜一句话摘要"}}
  ]
}}
"""
        data = await llm.chat_json(model, [{"role": "user", "content": prompt}], max_tokens=16384)

        files = data.get("files") or []
        if not files:
            raise RuntimeError("AI 未生成任何文档，请重试")

        written: list[dict] = []
        for f in files:
            title = (f.get("title") or "").strip() or meta.source_label
            body = (f.get("body") or "").strip()
            if not body:
                continue
            # 正文超长兜底截断（正常应由 AI 拆多个文件）
            if len(body) > max_chars:
                body = body[:max_chars].rstrip() + "\n\n> （内容过长已截断）"
            rel = (f.get("path") or "").strip()
            if not rel:
                name = _safe_name(title)[:60]
                rel = f"{name}.md"
            if not rel.lower().endswith(".md"):
                rel += ".md"
            rel = await _unique_path(ws, rel)
            fm = build_frontmatter(meta, title, tags=f.get("tags") or [])
            content = to_frontmatter_block(fm) + body
            await _write(ws.safe_join(rel), content)
            written.append({"path": rel, "title": title, "tags": f.get("tags") or []})

        # 更新所在文件夹索引（AI 条目 + 代码兜底补全）
        entries = list(data.get("index_entries") or [])
        for w in written:
            folder = str(Path(w["path"]).parent.as_posix())
            if folder == ".":
                folder = ""
            if not any(w["path"] in (e.get("entry") or "") for e in entries):
                entries.append(
                    {"folder": folder, "entry": f"- [{w['title']}]({w['path']})｜{w['title']}"}
                )
        await _update_index(ws, entries)

        # 写入后再次同步全量索引：确保新建子文件夹出现在父级/根 _index.md 的子目录段
        await sync_index(ws)

        return {"title": written[0]["title"], "files": [w["path"] for w in written]}
