"""知识库 API 接口（纯文件系统 + BM25 检索）。"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.database import get_db
from app.interceptor.auth_interceptor import get_current_user
from app.model.user import User
from app.repository.wiki_repository import WikiRepository
from app.service.kb_service import KbService
from app.service.wiki.templates import SourceMeta
from app.service.wiki.workspace import WikiWorkspace

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


# ============ DTO ============

class IngestRequest(BaseModel):
    text: str
    source_label: str | None = None
    source_type: str = "personal"      # online | local_file | personal
    platform: str = ""                 # bilibili/wechat/xiaohongshu/...
    original_url: str = ""
    author: str = ""
    publish_date: str = ""
    file_name: str = ""                # 本地文件溯源
    file_type: str = ""
    file_digest: str = ""
    raw_file: str = ""
    # 平台结构化字段（小红书 og 等，图片/音视频后续走云端 API）
    title: str = ""
    keywords: list[str] = []
    video: str = ""
    images: list[str] = []


class DeletePageRequest(BaseModel):
    file_path: str


# ============ 提取预览 ============

class ExtractLinkRequest(BaseModel):
    url: str
    platform: str = ""


@router.post("/extract/link")
async def extract_link(
    req: ExtractLinkRequest,
    user: User = Depends(get_current_user),
):
    """抓取链接并提取正文（供前端预览编辑后确认导入）。"""
    try:
        return await KbService.extract_link(user.email, req.url, req.platform)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/extract/file")
async def extract_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """上传文件并提取文本（供前端预览编辑后确认导入）。"""
    content = await file.read()
    if len(content) > settings.SHELL_MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413, detail=f"文件过大（上限 {settings.SHELL_MAX_FILE_SIZE} 字节）"
        )
    file_type = Path(file.filename or "file").suffix.lower().lstrip(".")
    if file_type not in _SUPPORTED_FILE_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file_type or '未知'}")

    digest = hashlib.sha256(content).hexdigest()
    ws = WikiWorkspace(user.email).ensure()
    raw_name = (file.filename or "upload").replace("\\", "/").split("/")[-1].replace("\x00", "")
    stem = Path(raw_name).stem or "upload"
    dest = ws.raw_notes / f"{stem}_{digest[:6]}.{file_type}"
    await asyncio.to_thread(dest.write_bytes, content)
    rel = dest.relative_to(ws.user_home).as_posix()
    text = await KbService.extract_file_text(user.email, rel)
    return {
        "text": text or "",
        "file_name": dest.name,
        "file_type": file_type,
        "file_digest": digest,
        "raw_file": rel,
    }


# ============ 摄取 ============

@router.post("/ingest/zip")
async def ingest_zip(
    file: UploadFile = File(...),
    source_label: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传 zip 压缩包（内含 md/txt/pdf/docx 等文档），解压后逐个入队导入。"""
    content = await file.read()
    if len(content) > settings.SHELL_MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413, detail=f"文件过大（上限 {settings.SHELL_MAX_FILE_SIZE} 字节）"
        )
    name = file.filename or "archive.zip"
    if not name.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持 .zip 压缩包")

    import io
    import zipfile

    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="压缩包已损坏或不是有效的 zip 文件")

    # 统计内部受支持文档数量，逐个入队
    import hashlib

    ws = WikiWorkspace(user.email).ensure()
    digest = hashlib.sha256(content).hexdigest()
    raw_name = name.replace("\\", "/").split("/")[-1].replace("\x00", "")
    dest = ws.raw_notes / f"{Path(raw_name).stem}_{digest[:6]}.zip"
    await asyncio.to_thread(dest.write_bytes, content)
    rel = dest.relative_to(ws.user_home).as_posix()

    count = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        ext = Path(info.filename).suffix.lower().lstrip(".")
        if ext in _SUPPORTED_FILE_TYPES or ext == "zip":
            count += 1
    if count == 0:
        raise HTTPException(status_code=400, detail="压缩包内没有可导入的文档")

    job = await WikiRepository.create_job(
        db,
        user.id,
        "ingest_zip",
        {
            "zip_path": rel,
            "file_name": dest.name,
            "source_label": source_label or dest.name,
        },
    )
    return {"job_id": job.id, "status": "queued", "count": count}


@router.post("/ingest")
async def ingest(
    req: IngestRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """摄取文本（链接由 AI 的 playwright 爬虫提取后也走此接口，可带 platform 等元数据）。异步入队。"""
    meta = SourceMeta(
        source_type=req.source_type,
        platform=req.platform,
        original_url=req.original_url,
        author=req.author,
        publish_date=req.publish_date,
        source_label=req.source_label or "用户输入",
        file_name=req.file_name,
        file_type=req.file_type,
        file_digest=req.file_digest,
        raw_file=req.raw_file,
        title=req.title,
        keywords=req.keywords,
        video=req.video,
        images=req.images,
    )
    job = await WikiRepository.create_job(
        db, user.id, "ingest_text", {"text": req.text, "meta": meta.model_dump()}
    )
    return {"job_id": job.id, "status": "queued"}


class IngestLinkRequest(BaseModel):
    url: str
    platform: str = ""                 # bilibili/wechat/xiaohongshu/...


@router.post("/ingest/link")
async def ingest_link(
    req: IngestLinkRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """链接摄取：异步入队，后台 CLI 抓取正文 -> AI 整理成 md。"""
    job = await WikiRepository.create_job(
        db, user.id, "ingest_link", {"url": req.url, "platform": req.platform}
    )
    return {"job_id": job.id, "status": "queued"}


_SUPPORTED_FILE_TYPES = {
    "pdf", "docx", "pptx", "xlsx", "xls", "html", "htm", "txt",
    "csv", "json", "xml", "rst", "rtf", "epub", "md",
}


@router.post("/ingest/file")
async def ingest_file(
    file: UploadFile = File(...),
    source_label: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传本地文件（pdf/word/pptx/xlsx 等），异步入队：CLI 提取文字 -> AI 整理成 md。"""
    content = await file.read()
    if len(content) > settings.SHELL_MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413, detail=f"文件过大（上限 {settings.SHELL_MAX_FILE_SIZE} 字节）"
        )
    file_type = Path(file.filename or "file").suffix.lower().lstrip(".")
    if file_type not in _SUPPORTED_FILE_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file_type or '未知'}")

    digest = hashlib.sha256(content).hexdigest()
    ws = WikiWorkspace(user.email).ensure()
    raw_name = (file.filename or "upload").replace("\\", "/").split("/")[-1].replace("\x00", "")
    stem = Path(raw_name).stem or "upload"
    dest = ws.raw_notes / f"{stem}_{digest[:6]}.{file_type}"
    await asyncio.to_thread(dest.write_bytes, content)
    rel = dest.relative_to(ws.user_home).as_posix()

    job = await WikiRepository.create_job(
        db,
        user.id,
        "ingest_file",
        {
            "file_path": rel,
            "file_name": dest.name,
            "file_type": file_type,
            "file_digest": digest,
            "source_label": source_label or dest.name,
        },
    )
    return {"job_id": job.id, "status": "queued", "file_digest": digest, "file_type": file_type}


# ============ 对话 ============

class ChatRequest(BaseModel):
    question: str


@router.post("/chat")
async def chat(req: ChatRequest, user: User = Depends(get_current_user)):
    """BM25 文本检索 + LLM 综合回答。"""
    try:
        return await KbService.chat_answer(user.email, req.question)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ 页面浏览/删除 ============

@router.get("/pages")
async def list_pages(user: User = Depends(get_current_user)):
    """扫描 wiki 目录返回文档列表（含相对路径/标题/文件夹）。"""
    return await KbService.list_pages(user.email)


@router.get("/page")
async def get_page(
    path: str, user: User = Depends(get_current_user)
):
    """读取单个文档内容（按相对 wiki 的路径）。"""
    page = await KbService.get_page(user.email, path)
    if not page:
        raise HTTPException(status_code=404, detail="文档不存在")
    return page


@router.delete("/pages")
async def delete_page(
    req: DeletePageRequest,
    user: User = Depends(get_current_user),
):
    """删除 md 文档，并同步清理 _index.md 记忆条目。"""
    removed = await KbService.delete_page(user.email, req.file_path)
    if not removed:
        raise HTTPException(status_code=404, detail="文档不存在或路径不合法")
    return {"removed": removed}


class MovePageRequest(BaseModel):
    path: str
    new_path: str
    new_title: str | None = None


@router.post("/move")
async def move_page(
    req: MovePageRequest,
    user: User = Depends(get_current_user),
):
    """移动/重命名文档或文件夹（move，跨文件夹亦可）。"""
    ok = await KbService.move_page(
        user.email, req.path, req.new_path, new_title=req.new_title
    )
    if not ok:
        raise HTTPException(status_code=400, detail="移动失败：路径不合法或目标已存在")
    return {"moved": True}


class DeleteFolderRequest(BaseModel):
    path: str


@router.post("/folder/delete")
async def delete_folder(
    req: DeleteFolderRequest,
    user: User = Depends(get_current_user),
):
    """删除整个文件夹（含内部所有文档与索引）。"""
    ok = await KbService.delete_folder(user.email, req.path)
    if not ok:
        raise HTTPException(status_code=400, detail="删除失败：路径不合法")
    return {"deleted": True}


# ============ 导出 / 原始文件 / 任务 ============

# 允许代理的图床域名（防 SSRF：只放行图片 CDN）
_PROXY_ALLOWED_HOSTS = ("mmbiz.qpic.cn",)


@router.get("/image_proxy")
async def image_proxy(url: str, user: User = Depends(get_current_user)):
    """代理外链图片/视频，绕过图床防盗链。

    微信 mmbiz 图片对非微信 Referer 的请求（如前端页面 localhost）返回水印/占位图，
    这里由后端用 httpx 带微信 Referer 拉取真实内容，再回传给前端。
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="仅支持 http(s) 链接")
    if not any(h in parsed.netloc for h in _PROXY_ALLOWED_HOSTS):
        raise HTTPException(status_code=403, detail="不允许代理该域名")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Referer": "https://mp.weixin.qq.com/",
    }
    last_err: Exception | None = None
    r = None
    try:
        # 图床偶发 SSL 断连，重试 2 次
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            for _ in range(3):
                try:
                    r = await client.get(url, headers=headers)
                    r.raise_for_status()
                    last_err = None
                    break
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    await asyncio.sleep(0.4)
    except Exception as e:
        last_err = e
    if r is None or last_err is not None:
        raise HTTPException(status_code=502, detail=f"资源拉取失败: {last_err}")
    return Response(
        content=r.content,
        media_type=r.headers.get("content-type", "application/octet-stream"),
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/export")
async def export(user: User = Depends(get_current_user)):
    """导出该用户 wiki/ 目录为 zip（Obsidian 可用）。"""
    data = await KbService.export_zip(user.email)
    safe_email = user.email.replace("@", "_at_")
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="wiki-{safe_email}.zip"'},
    )


@router.get("/raw/{file_path:path}")
async def get_raw_file(
    file_path: str, user: User = Depends(get_current_user)
):
    """下载用户原始文件（raw/ 目录下的已上传文件/抓取 html）。"""
    ws = WikiWorkspace(user.email)
    target = (ws.user_home / file_path).resolve()
    root = ws.user_home.resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=403, detail="路径不合法")
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target, filename=target.name)


@router.get("/jobs")
async def list_jobs(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    offset = (page - 1) * page_size
    total = await WikiRepository.count_jobs(db, user.id)
    jobs = await WikiRepository.list_jobs(db, user.id, limit=page_size, offset=offset)
    return {
        "items": [
            {
                "id": j.id,
                "type": j.type,
                "status": j.status,
                "error": j.error,
                "created_at": j.created_at,
                "started_at": j.started_at,
                "finished_at": j.finished_at,
            }
            for j in jobs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
