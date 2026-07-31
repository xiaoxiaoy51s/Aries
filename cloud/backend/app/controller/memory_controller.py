from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.interceptor.auth_interceptor import get_current_user
from app.model.user import User
from app.service.memory_service import MemoryService

router = APIRouter(prefix="/api/memory", tags=["memory"])


# ============ DTO ============

class SaveMemoryRequest(BaseModel):
    content: str = ""


# ============ 全局记忆 ============

@router.get("/global")
async def get_global_memory(user: User = Depends(get_current_user)):
    """读取全局记忆 user_profile.md"""
    content = MemoryService.read_global_memory(user.email)
    return {
        "success": True,
        "content": content,
        "exists": bool(content),
    }


@router.post("/global")
async def save_global_memory(req: SaveMemoryRequest, user: User = Depends(get_current_user)):
    """保存全局记忆 user_profile.md"""
    result = MemoryService.write_global_memory(user.email, req.content)
    return result


# ============ 项目记忆列表 ============

@router.get("/projects")
async def list_project_memories(user: User = Depends(get_current_user)):
    """列出各 workspace 的项目记忆文件状态"""
    items = MemoryService.list_project_memories(user.email)
    return {"success": True, "projects": items}


# ============ 项目记忆读写 ============

@router.get("/project/{workspace_name}")
async def get_project_memory(workspace_name: str, user: User = Depends(get_current_user)):
    """读取指定 workspace 的项目记忆 memory.md"""
    try:
        content = MemoryService.read_project_memory(user.email, workspace_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "success": True,
        "workspace": workspace_name,
        "content": content,
        "exists": bool(content),
    }


@router.post("/project/{workspace_name}")
async def save_project_memory(
    workspace_name: str,
    req: SaveMemoryRequest,
    user: User = Depends(get_current_user),
):
    """保存指定 workspace 的项目记忆 memory.md"""
    try:
        result = MemoryService.write_project_memory(user.email, workspace_name, req.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result
