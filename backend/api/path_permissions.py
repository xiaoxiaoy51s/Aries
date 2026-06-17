from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from db.path_permissions import (
    add_permission,
    remove_permission,
    list_permissions,
)

router = APIRouter(prefix="/path-permissions", tags=["path-permissions"])


class PermissionCreate(BaseModel):
    path: str
    type: str  # 'whitelist' or 'blacklist'


@router.get("/")
def get_permissions():
    """获取所有路径权限规则。"""
    return {"permissions": list_permissions()}


@router.post("/")
def create_permission(payload: PermissionCreate):
    """添加路径权限规则。"""
    if payload.type not in ("whitelist", "blacklist"):
        return {"success": False, "error": "type 必须是 whitelist 或 blacklist"}
    result = add_permission(payload.path, payload.type)
    return result


@router.delete("/{path:path}")
def delete_permission(path: str):
    """删除路径权限规则。"""
    return remove_permission(path)
