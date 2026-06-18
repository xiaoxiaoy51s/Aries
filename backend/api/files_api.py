"""文件浏览器 API: 列出目录、读取文件内容。"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/files", tags=["files"])


def _normalize_work_dir(work_dir: str | None) -> str:
    if work_dir and work_dir.strip():
        return str(Path(work_dir).expanduser().resolve())
    return str(Path.cwd())


@router.get("/list")
async def list_files(
    work_dir: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """列出指定路径下的文件和目录。"""
    base = Path(_normalize_work_dir(work_dir))
    target = base
    if path:
        target = base / path
    target = target.resolve()
    # 安全检查: 确保在 base 下
    if not str(target).startswith(str(base)):
        return {"entries": [], "error": "路径越界"}

    if not target.exists():
        return {"entries": [], "error": "路径不存在"}
    if not target.is_dir():
        return {"entries": [], "error": "不是目录"}

    entries: list[dict[str, Any]] = []
    try:
        for item in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            rel = str(item.relative_to(base)).replace("\\", "/")
            entries.append({
                "name": item.name,
                "path": rel,
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else 0,
            })
    except PermissionError:
        return {"entries": [], "error": "权限不足"}

    return {"entries": entries}


@router.get("/read")
async def read_file(
    work_dir: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """读取指定文件的内容。"""
    base = Path(_normalize_work_dir(work_dir))
    if not path:
        return {"content": "", "error": "缺少路径参数"}
    target = (base / path).resolve()
    if not str(target).startswith(str(base)):
        return {"content": "", "error": "路径越界"}
    if not target.exists() or not target.is_file():
        return {"content": "", "error": "文件不存在"}

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"content": content}
    except Exception as e:
        return {"content": "", "error": str(e)}
