"""文件浏览器 API: 列出目录、读取文件内容。"""
from __future__ import annotations

import asyncio
import base64
import mimetypes
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/files", tags=["files"])

# 图片扩展名（可通过浏览器 <img> 直接预览）
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico"}

# 已知的二进制文件扩展名（非图片，无法在文本编辑器中正常显示）
BINARY_EXTENSIONS = {
    ".class", ".jar", ".war", ".ear", ".exe", ".dll", ".so", ".dylib",
    ".bin", ".dat", ".db", ".sqlite", ".pyc", ".pyo", ".o", ".a",
    ".zip", ".gz", ".tar", ".bz2", ".7z", ".rar", ".xz",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flv", ".mkv",
    ".wasm", ".pak",
}


def _normalize_work_dir(work_dir: str | None) -> str:
    if work_dir and work_dir.strip():
        path = Path(work_dir).expanduser().resolve()
    else:
        path = Path.home() / ".Aries" / "work_dir"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


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
    """读取指定文件的内容。

    - 图片文件：返回 base64 编码 + mime 类型，前端用 <img> 预览
    - 其他二进制文件：返回 is_binary 标记，不返回内容
    - 文本文件：返回 UTF-8 文本内容
    """
    base = Path(_normalize_work_dir(work_dir))
    if not path:
        return {"content": "", "error": "缺少路径参数"}
    target = (base / path).resolve()
    if not str(target).startswith(str(base)):
        return {"content": "", "error": "路径越界"}
    if not target.exists() or not target.is_file():
        return {"content": "", "error": "文件不存在"}

    ext = target.suffix.lower()

    # 图片文件：返回 base64
    if ext in IMAGE_EXTENSIONS:
        try:
            raw = target.read_bytes()
            mime = mimetypes.guess_type(str(target))[0] or "image/png"
            return {
                "is_image": True,
                "content": base64.b64encode(raw).decode("ascii"),
                "mime": mime,
                "size": len(raw),
            }
        except Exception as e:
            return {"content": "", "error": str(e)}

    # 其他二进制文件：不返回内容
    if ext in BINARY_EXTENSIONS:
        try:
            size = target.stat().st_size
            return {
                "is_binary": True,
                "content": "",
                "size": size,
                "file_type": ext,
            }
        except Exception as e:
            return {"content": "", "error": str(e)}

    # 文本文件：读取 UTF-8 内容
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"content": content}
    except Exception as e:
        return {"content": "", "error": str(e)}


class DeleteRequest(BaseModel):
    work_dir: str
    path: str


class RenameRequest(BaseModel):
    work_dir: str
    path: str
    new_name: str


@router.delete("/delete")
async def delete_file(req: DeleteRequest) -> dict[str, Any]:
    """删除文件或目录。"""
    import shutil

    base = Path(_normalize_work_dir(req.work_dir))
    target = (base / req.path).resolve()
    if not str(target).startswith(str(base)):
        return {"error": "路径越界"}
    if not target.exists():
        return {"error": "文件不存在"}
    if target == base:
        return {"error": "不能删除工作目录根"}

    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


@router.put("/rename")
async def rename_file(req: RenameRequest) -> dict[str, Any]:
    """重命名文件或目录。"""
    base = Path(_normalize_work_dir(req.work_dir))
    target = (base / req.path).resolve()
    if not str(target).startswith(str(base)):
        return {"error": "路径越界"}
    if not target.exists():
        return {"error": "文件不存在"}

    new_name = req.new_name.strip()
    if not new_name or "/" in new_name or "\\" in new_name:
        return {"error": "新文件名无效"}

    new_target = target.parent / new_name
    if new_target == target:
        return {"ok": True, "new_path": req.path}
    if new_target.exists():
        return {"error": "目标名称已存在"}

    try:
        target.rename(new_target)
        rel = str(new_target.relative_to(base)).replace("\\", "/")
        return {"ok": True, "new_path": rel}
    except Exception as e:
        return {"error": str(e)}


class OpenInEditorRequest(BaseModel):
    work_dir: str | None = None
    editor: str = "vscode"  # vscode | explorer


@router.post("/open-in-editor")
async def open_in_editor(req: OpenInEditorRequest) -> dict[str, Any]:
    """用外部编辑器（VSCode）或系统文件管理器打开工作目录。"""
    base = Path(_normalize_work_dir(req.work_dir))
    if not base.exists():
        return {"error": "工作目录不存在"}

    try:
        if req.editor == "vscode":
            # 优先使用 code 命令行（VSCode 安装时通常会注册到 PATH）
            code_bin = shutil.which("code") or shutil.which("code.cmd")
            if code_bin:
                subprocess.Popen(
                    [code_bin, str(base)],
                    shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                return {"ok": True, "editor": "vscode"}
            return {"error": "未找到 VSCode（请确保已安装并将 code 命令加入 PATH）"}
        elif req.editor == "explorer":
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(base)], shell=False)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(base)])
            else:
                subprocess.Popen(["xdg-open", str(base)])
            return {"ok": True, "editor": "explorer"}
        else:
            return {"error": f"不支持的编辑器: {req.editor}"}
    except Exception as e:
        return {"error": str(e)}
