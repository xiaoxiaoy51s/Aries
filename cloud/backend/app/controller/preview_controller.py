"""公开预览端点：无需认证访问工作目录内的文件。

用于 HTML 页面预览与分享链接。URL 格式：
  /api/preview/{email}/{workspace_name}/{file_path}

邮箱作为用户标识直接定位 ~/.Aries/{email}/workspaces/{workspace_name}/。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.tools.sandbox import (
    normalize_user_email,
    resolve_workspace_path,
    validate_workspace_name,
)

router = APIRouter(prefix="/api/preview", tags=["preview"])


@router.get("/{email}/{workspace_name}/{file_path:path}")
async def preview_workspace_file(email: str, workspace_name: str, file_path: str):
    """公开预览工作目录文件（无需登录）。"""
    raw_path = (file_path or "").strip()
    if not raw_path or raw_path in (".", "./"):
        raise HTTPException(status_code=400, detail="文件路径不能为空")

    try:
        name = validate_workspace_name(workspace_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    workspace = Path.home() / ".Aries" / normalize_user_email(email) / "workspaces" / name
    if not workspace.is_dir():
        raise HTTPException(status_code=404, detail="工作目录不存在")

    target, err = resolve_workspace_path(workspace, raw_path)
    if err or target is None:
        raise HTTPException(status_code=400, detail=err or "路径无效")
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="不是文件")

    return FileResponse(
        path=str(target),
        filename=target.name,
        content_disposition_type="inline",
    )
