from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.interceptor.auth_interceptor import get_current_user
from app.model.user import User
from app.service.session_service import SessionService
from app.service.workspace_service import WorkspaceService

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class CreateWorkspaceRequest(BaseModel):
    name: str


class UploadToWorkspaceRequest(BaseModel):
    path: str = ""


class RenameFileRequest(BaseModel):
    path: str
    new_name: str


class SaveFileContentRequest(BaseModel):
    path: str
    content: str


class CreateEntryRequest(BaseModel):
    path: str
    is_dir: bool = False


class RenameWorkspaceRequest(BaseModel):
    new_name: str


@router.get("")
async def list_workspaces(user: User = Depends(get_current_user)):
    """列出用户所有工作目录。"""
    return {"workspaces": WorkspaceService.list_user_workspaces(user.email)}


@router.post("")
async def create_workspace(
    req: CreateWorkspaceRequest,
    user: User = Depends(get_current_user),
):
    """新建工作目录 ~/.Aries/{email}/workspaces/{name}/"""
    try:
        ws = WorkspaceService.create_workspace(user.email, req.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ws


@router.get("/{workspace_name}/files")
async def list_workspace_files(
    workspace_name: str,
    path: str = "",
    user: User = Depends(get_current_user),
):
    """列出工作目录内文件。"""
    try:
        files = WorkspaceService.list_files(user.email, workspace_name, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"workspace": workspace_name, "path": path or ".", "files": files}


@router.post("/{workspace_name}/files")
async def upload_to_workspace(
    workspace_name: str,
    path: str = "",
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """上传文件到工作目录。"""
    try:
        result = await WorkspaceService.save_upload_to_workspace(
            user.email, workspace_name, path, file
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.post("/{workspace_name}/files/create")
async def create_workspace_entry(
    workspace_name: str,
    req: CreateEntryRequest,
    user: User = Depends(get_current_user),
):
    """在工作目录内创建空文件或文件夹。"""
    try:
        result = WorkspaceService.create_entry(
            user.email, workspace_name, req.path, req.is_dir
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.get("/{workspace_name}/files/download")
async def download_workspace_file(
    workspace_name: str,
    path: str,
    user: User = Depends(get_current_user),
):
    """从工作目录下载文件。"""
    try:
        target = WorkspaceService.resolve_download_path(user.email, workspace_name, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return FileResponse(path=str(target), filename=target.name)


@router.get("/{workspace_name}/files/read")
async def read_workspace_file(
    workspace_name: str,
    path: str,
    user: User = Depends(get_current_user),
):
    """读取工作目录文件内容（文本返回原文，二进制返回 base64）。"""
    import base64
    import mimetypes

    try:
        target = WorkspaceService.resolve_download_path(user.email, workspace_name, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    mime, _ = mimetypes.guess_type(target.name)
    mime = mime or "application/octet-stream"
    is_image = mime.startswith("image/")
    is_binary = mime not in (
        "text/plain", "text/html", "text/css", "text/javascript",
        "application/json", "application/xml", "application/javascript",
        "text/xml", "text/csv", "application/x-yaml", "text/yaml",
    ) and not is_image and not mime.startswith("text/")

    raw = target.read_bytes()

    if is_image or is_binary:
        return {
            "is_image": is_image,
            "is_binary": is_binary,
            "mime": mime,
            "content": base64.b64encode(raw).decode("ascii"),
            "size": len(raw),
            "file_type": target.suffix.lstrip("."),
        }

    return {
        "is_image": False,
        "is_binary": False,
        "mime": mime,
        "content": raw.decode("utf-8", errors="replace"),
        "size": len(raw),
    }


@router.delete("/{workspace_name}/files")
async def delete_workspace_file(
    workspace_name: str,
    path: str,
    user: User = Depends(get_current_user),
):
    """删除工作目录内文件或子目录。"""
    try:
        WorkspaceService.delete_workspace_file(user.email, workspace_name, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}


@router.put("/{workspace_name}/files/rename")
async def rename_workspace_file(
    workspace_name: str,
    req: RenameFileRequest,
    user: User = Depends(get_current_user),
):
    """重命名工作目录内文件或子目录（仅改名，不移动）。"""
    try:
        result = WorkspaceService.rename_workspace_file(user.email, workspace_name, req.path, req.new_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.put("/{workspace_name}/files/content")
async def save_workspace_file_content(
    workspace_name: str,
    req: SaveFileContentRequest,
    user: User = Depends(get_current_user),
):
    """保存文本内容到工作目录内文件。"""
    try:
        result = WorkspaceService.save_file_content(
            user.email, workspace_name, req.path, req.content
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


# ============ 工作目录管理（目录重命名 / 删除，联同 session） ============


@router.put("/{workspace_name}/rename")
async def rename_workspace(
    workspace_name: str,
    req: RenameWorkspaceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重命名工作目录（目录重命名 + 批量更新名下 session 的 workspace_dir）。"""
    new_name = req.new_name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="新名称不能为空")
    try:
        WorkspaceService.rename_workspace(user.email, workspace_name, new_name)
        await SessionService.rename_workspace(db, user.id, workspace_name, new_name)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "new_name": new_name}


@router.delete("/{workspace_name}")
async def delete_workspace(
    workspace_name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除工作目录（删除目录文件 + 删除名下所有 session）。"""
    try:
        WorkspaceService.delete_workspace(user.email, workspace_name)
        await SessionService.delete_by_workspace(db, user.id, user.email, workspace_name)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}


# ============ 通用 upload 目录 ============

upload_router = APIRouter(prefix="/api/upload", tags=["upload"])


@upload_router.get("")
async def list_uploads(user: User = Depends(get_current_user)):
    return {"files": WorkspaceService.list_upload_files(user.email)}


@upload_router.post("")
async def upload_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """上传到 ~/.Aries/{email}/upload/"""
    try:
        result = await WorkspaceService.save_upload_to_upload_dir(user.email, file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@upload_router.get("/download")
async def download_upload(
    path: str,
    user: User = Depends(get_current_user),
):
    try:
        target = WorkspaceService.resolve_upload_download(user.email, path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return FileResponse(path=str(target), filename=target.name)
