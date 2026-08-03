"""知识库编排层：摄取（文本/文件/链接）/ 删除 / 对话 / 导出。

知识库为纯文件系统（~/.Aries/{email}/wiki/，文件夹由 AI 组织），
检索使用 BM25 文本搜索 + AI 记忆索引（_index.md），无数据库/向量依赖。
"""
from __future__ import annotations

import asyncio
import io
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from app.service.model_config_service import ModelConfigService
from app.service.wiki import image_ocr, ingest, llm, ocr, playwright_fetch, retrieval
from app.service.wiki.cleaners import get_cleaner, infer_platform
from app.service.wiki.templates import SourceMeta
from app.service.wiki.workspace import WikiWorkspace


def _frontmatter_fields(content_md: str) -> dict:
    """解析 md 的 frontmatter 关键字段（title/tags/file_digest/raw_file/original_url 等）。"""
    fields: dict = {}
    m = re.match(r"^---\n([\s\S]*?)\n---", content_md)
    if not m:
        return fields
    for line in m.group(1).splitlines():
        idx = line.find(":")
        if idx <= 0:
            continue
        key = line[:idx].strip()
        val = line[idx + 1 :].strip().strip('"\'')
        if val.startswith("["):
            val = val[1:-1].split(",")
            val = [v.strip().strip("'\"") for v in val if v.strip()]
        fields[key] = val
    return fields


def _collapse_cjk_spaces(text: str) -> str:
    """折叠 CJK 字符之间的多余空格（PDF 文本提取的常见伪空格），保留换行/段落。

    markitdown 经 pdfminer 提取 PDF 中文时，常在每个汉字间插入空格。这里仅移除
    CJK 字符之间的空格/制表符，不触碰换行与中英文之间的空格，属于通用归一化而非
    平台清洗。
    """
    if not text:
        return text
    prev = None
    out = text
    while prev != out:
        prev = out
        out = re.sub(
            r"([\u4e00-\u9fff\uff00-\uffef])[ \t]+([\u4e00-\u9fff\uff00-\uffef])",
            r"\1\2",
            out,
        )
    return out


class KbService:
    @staticmethod
    async def ingest_text(email: str, text: str, meta: SourceMeta | None = None) -> dict:
        """文本摄取（日记/想法/爬虫已提取正文）：AI 整理成 md 写入 wiki。"""
        meta = meta or SourceMeta()
        return await ingest.ingest_source(email, text, meta)

    @staticmethod
    async def ingest_file(
        email: str,
        file_path: str,
        file_name: str,
        file_type: str,
        file_digest: str,
        source_label: str = "",
    ) -> dict:
        """文件摄取：file_digest 去重 -> markitdown 转文本 -> AI 整理成 md。"""
        ws = WikiWorkspace(email).ensure()
        # 文件哈希去重（扫描已有文档 frontmatter 的 file_digest）
        if file_digest:
            for p in ws.all_pages():
                def _read_fm():
                    return _frontmatter_fields(p.read_text(encoding="utf-8", errors="ignore"))
                fm = await asyncio.to_thread(_read_fm)
                if fm.get("file_digest") == file_digest:
                    return {"skipped": True, "file_path": ws.rel_path(p), "title": fm.get("title", "")}
        text = get_cleaner("").clean_text(await _markitdown_convert(ws.user_home / file_path))
        meta = SourceMeta(
            source_type="local_file",
            file_name=file_name,
            file_type=file_type,
            file_digest=file_digest,
            raw_file=file_path,
            source_label=source_label or file_name,
        )
        return await ingest.ingest_source(email, text, meta)

    @staticmethod
    async def ingest_zip(
        email: str,
        zip_path: str,
        source_label: str = "",
    ) -> dict:
        """zip 批量导入：解压压缩包，逐个处理内部受支持文档。

        - md/txt/csv/html/json/xml/rst/rtf：直接读文本，AI 整理入库
        - pdf/docx/pptx/xlsx/xls/epub：markitdown 转文本后入库
        - 返回 {imported, skipped, errors}，供任务日志展示。
        """
        ws = WikiWorkspace(email).ensure()
        archive = ws.user_home / zip_path
        if not archive.exists():
            raise RuntimeError("压缩包不存在")

        imported = 0
        errors: list[str] = []
        _TEXT_EXTS = {"md", "txt", "csv", "html", "htm", "json", "xml", "rst", "rtf"}
        _CONVERT_EXTS = {"pdf", "docx", "pptx", "xlsx", "xls", "epub"}

        def _extract_to_temp() -> Path:
            tmp = ws.user_home / f".zip_extract_{Path(zip_path).stem}"
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive) as zf:
                # 防路径穿越：只解压合法相对路径
                for info in zf.infolist():
                    name = info.filename.replace("\\", "/")
                    if name.startswith("/") or ".." in name.split("/"):
                        continue
                    target = (tmp / name).resolve()
                    if not str(target).startswith(str(tmp.resolve())):
                        continue
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(info) as src, open(target, "wb") as out:
                            out.write(src.read())
            return tmp

        tmp = await asyncio.to_thread(_extract_to_temp)
        try:
            files = sorted(
                p for p in tmp.rglob("*") if p.is_file()
            )
            for p in files:
                ext = p.suffix.lower().lstrip(".")
                rel = p.relative_to(tmp).as_posix()
                try:
                    if ext in _TEXT_EXTS:
                        text = p.read_text(encoding="utf-8", errors="ignore")
                        if not text.strip():
                            continue
                        meta = SourceMeta(
                            source_type="local_file",
                            file_name=p.name,
                            file_type=ext,
                            raw_file="",
                            source_label=f"{source_label or Path(zip_path).name} / {rel}",
                        )
                        await ingest.ingest_source(email, text, meta)
                        imported += 1
                    elif ext in _CONVERT_EXTS:
                        text = await _markitdown_convert(p)
                        if not text or not text.strip():
                            errors.append(f"{rel}: 提取为空")
                            continue
                        meta = SourceMeta(
                            source_type="local_file",
                            file_name=p.name,
                            file_type=ext,
                            raw_file="",
                            source_label=f"{source_label or Path(zip_path).name} / {rel}",
                        )
                        await ingest.ingest_source(email, get_cleaner("").clean_text(text), meta)
                        imported += 1
                    else:
                        errors.append(f"{rel}: 不支持的类型 .{ext}")
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{rel}: {e}")
        finally:
            await asyncio.to_thread(shutil.rmtree, tmp, ignore_errors=True)
        return {"imported": imported, "errors": errors}

    @staticmethod
    async def extract_link(email: str, url: str, platform: str = "") -> dict:
        """抓取链接并提取正文（供前端预览编辑后确认导入）。

        按平台分流：
        - 微信：playwright 渲染页面 -> PDF -> 按页提取文本 + PDF 内嵌图片 OCR 穿插
          （渲染后 PDF 能拿到完整正文，图片文字也一并识别，效果稳定）
        - 其他平台（小红书/知乎/B站等）：用平台 cleaner 结构化提取 og meta 正文，
          图片 URL 下载后走视觉模型 OCR 识别文字并附在正文后
        - 两者都失败时回退 markitdown 直接转换静态 HTML
        """
        import httpx

        url = url.strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError("链接必须以 http(s):// 开头")

        platform = infer_platform(url, platform)
        cleaner = get_cleaner(platform)

        ws = WikiWorkspace(email).ensure()
        raw_seg = url.split("?")[0].rstrip("/").split("/")[-1]
        name = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]", "_", raw_seg)[:60] or "link"
        stamp = datetime.now().strftime("%H%M%S")
        html_path = ws.raw_links / f"{name}_{stamp}.html"

        # 1. httpx 抓取 HTML + cleaner 提取结构化 meta（标题/正文/图片/关键词等）
        meta: dict = {}
        title = ""
        html_src = ""
        try:
            def _fetch() -> None:
                resp = httpx.get(
                    url,
                    follow_redirects=True,
                    timeout=20.0,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                        )
                    },
                    trust_env=False,
                )
                resp.raise_for_status()
                html_path.write_bytes(resp.content)

            await asyncio.to_thread(_fetch)
            html_src = await asyncio.to_thread(html_path.read_text, "utf-8", errors="ignore")
            meta = cleaner.extract_meta(html_src)
            title = (meta.get("title") or "").strip()
        except Exception:
            pass

        text = ""
        pdf_url = ""
        pdf_path = ws.raw_links / f"{name}_{stamp}.pdf"

        # 2. 微信：PDF 渲染 + 按页文本/图片 OCR（效果好）
        if platform == "wechat":
            try:
                rendered = await playwright_fetch.fetch_rendered_pdf(url, save_path=pdf_path)
                if rendered:
                    text = await image_ocr.pdf_content_text(rendered, user_email=email)
                    if not text or len(text.strip()) < 50:
                        # fitz 提取失败/为空时回退 markitdown
                        try:
                            text = await _markitdown_convert(rendered)
                        except Exception:
                            text = ""
                    pdf_url = "/api/kb/raw/" + rendered.relative_to(ws.user_home).as_posix()
            except Exception:
                pass

        # 3. 其他平台：结构化 meta 正文 + 图片 URL 下载 OCR
        else:
            text = (meta.get("description") or "").strip()
            if text:
                imgs = meta.get("images") or []
                if imgs:
                    ocr_text = await image_ocr.ocr_urls_text(imgs, user_email=email)
                    if ocr_text:
                        text = text.rstrip() + "\n\n" + ocr_text
            else:
                # 结构化提取为空（页面 JS 渲染/未抓到 meta）-> 尝试 PDF 兜底
                try:
                    rendered = await playwright_fetch.fetch_rendered_pdf(url, save_path=pdf_path)
                    if rendered:
                        text = await image_ocr.pdf_content_text(rendered, user_email=email)
                        if not text or len(text.strip()) < 50:
                            try:
                                text = await _markitdown_convert(rendered)
                            except Exception:
                                text = ""
                        pdf_url = "/api/kb/raw/" + rendered.relative_to(ws.user_home).as_posix()
                except Exception:
                    pass

        # 4. 兜底：markitdown 直接转换静态 HTML
        if (not text or len(text.strip()) < 50) and html_path.exists():
            try:
                text = await _markitdown_convert(html_path)
            except Exception:
                pass

        # PDF 提取的中文常带伪空格，做一次通用归一化（非平台清洗）
        text = _collapse_cjk_spaces(text)

        result: dict = {"text": text or "", "url": url, "platform": platform}
        if pdf_url:
            result["pdf_url"] = pdf_url
        # 透传结构化字段（关键词/视频/图片 URL 等，供预览展示）
        for k in ("keywords", "video", "images"):
            v = meta.get(k)
            if v:
                result[k] = v
        if title:
            result["title"] = title
        if not text or len(text.strip()) < 50:
            result["error"] = (
                "内容提取过短或为空（可能未安装 playwright 或页面需登录）。"
                "可在预览中手动粘贴正文。"
            )
        return result

    @staticmethod
    async def extract_file_text(email: str, raw_rel: str) -> str:
        """用 markitdown 转换 raw/ 下的文件为文本（供前端预览编辑）。"""
        ws = WikiWorkspace(email)
        target = (ws.user_home / raw_rel).resolve()
        if not target.exists():
            raise RuntimeError("原始文件不存在")
        return get_cleaner("").clean_text(await _markitdown_convert(target))

    @staticmethod
    async def ingest_link(email: str, url: str, platform: str = "") -> dict:
        """链接摄取：抓取正文 -> AI 整理成 md（供对话/内部流程直接导入）。"""
        data = await KbService.extract_link(email, url, platform)
        text = data.get("text") or ""
        if not text or len(text.strip()) < 100:
            raise RuntimeError(
                "链接抓取失败或内容为空（可能是 JS 渲染页面）。请使用页面预览功能手动补充内容后导入。"
            )
        meta = SourceMeta(
            source_type="online",
            platform=platform,
            original_url=url,
            source_label=url,
        )
        return await ingest.ingest_source(email, text, meta)

    @staticmethod
    async def delete_page(email: str, file_path: str) -> bool:
        """删除 md 文档及其在 _index.md 中的记忆条目。"""
        ws = WikiWorkspace(email)
        target = ws.safe_join(file_path)
        if target is None:
            return False
        removed = False
        if target.exists() and target.is_file():
            target.unlink()
            removed = True
        await ingest.remove_doc_from_index(ws, file_path)
        return removed

    @staticmethod
    async def move_page(email: str, src_path: str, new_path: str, new_title: str | None = None) -> bool:
        """移动/重命名文档或文件夹（move 到新路径，含跨文件夹）。

        new_title 仅在移动单个文件时生效：同步更新 frontmatter title。
        移动后重建层级索引与图谱。
        """
        ws = WikiWorkspace(email)
        src = ws.safe_join(src_path)
        dst = ws.safe_join(new_path)
        if src is None or dst is None or not src.exists() or src == dst:
            return False
        # 目标若是已存在的目录，则把文件移入其中
        if dst.is_dir():
            dst = dst / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            return False  # 目标已存在，拒绝覆盖
        await asyncio.to_thread(shutil.move, str(src), str(dst))
        # 单文件重命名时同步 frontmatter title
        if new_title and dst.is_file():
            md = await asyncio.to_thread(dst.read_text, "utf-8", errors="ignore")
            updated = re.sub(
                r"^(title:\s*).*$", lambda m: f"{m.group(1)}{new_title}", md, count=1, flags=re.MULTILINE
            )
            await asyncio.to_thread(dst.write_text, updated, "utf-8")
        await ingest.sync_index(ws)
        return True

    @staticmethod
    async def delete_folder(email: str, dir_path: str) -> bool:
        """删除整个文件夹（含内部所有文档与 _index.md），并重建索引。"""
        ws = WikiWorkspace(email)
        target = ws.safe_join(dir_path)
        if (
            target is None
            or target == ws.root
            or not target.exists()
            or not target.is_dir()
        ):
            return False
        await asyncio.to_thread(shutil.rmtree, str(target), ignore_errors=True)
        await ingest.sync_index(ws)
        return True

    @staticmethod
    async def list_pages(email: str) -> list[dict]:
        """扫描 wiki 目录返回文档列表（含相对路径/标题/tags/更新时间）。

        浏览前先做一次记忆索引对齐，兜底用户绕过 API 的手动增删/移动。
        """
        ws = WikiWorkspace(email).ensure()
        await ingest.sync_index(ws)
        pages = ws.all_pages()
        out: list[dict] = []
        for p in pages:
            try:
                md = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            fm = _frontmatter_fields(md)
            rel = ws.rel_path(p)
            out.append(
                {
                    "path": rel,
                    "title": fm.get("title") or p.stem,
                    "tags": fm.get("tags") or [],
                    "dir": str(p.parent.relative_to(ws.root)) if p.parent != ws.root else "",
                    "updated_at": fm.get("last_updated") or "",
                }
            )
        out.sort(key=lambda x: (x["dir"], x["title"]))
        return out

    @staticmethod
    async def get_page(email: str, file_path: str) -> dict | None:
        """读取单个文档（含 frontmatter 元信息 + 正文）。"""
        ws = WikiWorkspace(email)
        target = ws.safe_join(file_path)
        if target is None or not target.exists() or not target.is_file():
            return None
        md = await asyncio.to_thread(target.read_text, "utf-8", errors="ignore")
        fm = _frontmatter_fields(md)
        rel = ws.rel_path(target)
        return {
            "path": rel,
            "title": fm.get("title") or target.stem,
            "tags": fm.get("tags") or [],
            "content_md": md,
            "updated_at": fm.get("last_updated") or "",
            "meta": fm,
        }

    @staticmethod
    async def chat_answer(email: str, question: str) -> dict:
        """BM25 文本检索 + 对话模型综合回答（无需向量/embedding）。"""
        model = await ModelConfigService.get_active_model(email)
        if not model:
            raise RuntimeError("尚未配置模型，请先在设置中添加模型")

        pages = await retrieval.retrieve(email, question)
        if not pages:
            return {"answer": "知识库中未找到相关内容。", "sources": []}

        ctx = "\n\n".join(
            f"### {p['file_path']}\n{p['content_md'] or ''}" for p in pages
        )
        prompt = (
            "你是知识库问答助手。基于以下 wiki 文档回答问题，用 [[标题]] 引用来源文档。"
            "若内容不足以回答，请明确说明。\n\n"
            f"Wiki 文档：\n{ctx}\n\n问题：{question}\n\n"
            "写结构化 markdown 回答，末尾加 ## Sources 列出引用的文档路径。"
        )
        answer = await llm.chat_complete(
            model, [{"role": "user", "content": prompt}], max_tokens=4096
        )
        return {
            "answer": answer,
            "sources": [
                {"file_path": p["file_path"], "title": p["title"], "via": p["via"]}
                for p in pages
            ],
        }

    @staticmethod
    async def export_zip(email: str) -> bytes:
        """导出该用户 wiki/ 目录为 zip（Obsidian 可用）。"""
        ws = WikiWorkspace(email)

        def _zip() -> bytes:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                if ws.root.exists():
                    for p in ws.root.rglob("*"):
                        if p.is_file():
                            zf.write(p, p.relative_to(ws.user_home).as_posix())
            return buf.getvalue()

        return await asyncio.to_thread(_zip)


async def _markitdown_convert(path: Path) -> str:
    """用 markitdown 把文件转为 markdown 文本。"""

    def _conv() -> str:
        try:
            from markitdown import MarkItDown
        except ImportError as e:
            raise RuntimeError("markitdown 未安装，无法转换文件") from e
        md = MarkItDown(enable_plugins=False)
        try:
            result = md.convert(str(path))
        except Exception as e:
            raise RuntimeError(f"文件转换失败（{path.suffix or '未知类型'}）: {e}") from e
        return result.text_content or ""

    return await asyncio.to_thread(_conv)
