from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from db.path_permissions import (
    add_permission,
    remove_permission,
    list_permissions,
)
from utils.app_setting import (
    APPROVAL_MODES,
    get_approval_mode,
    set_approval_mode,
)

router = APIRouter(prefix="/path-permissions", tags=["path-permissions"])


class PermissionCreate(BaseModel):
    path: str
    type: str  # 'whitelist' or 'blacklist'


class ApprovalModeUpdate(BaseModel):
    mode: str  # 'request' | 'review' | 'full'


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


@router.get("/approval-mode")
def get_approval_mode_api():
    """获取全局批准模式（request / review / full）。"""
    return {"mode": get_approval_mode(), "available": list(APPROVAL_MODES)}


@router.put("/approval-mode")
def set_approval_mode_api(payload: ApprovalModeUpdate):
    """设置全局批准模式，落盘到 ~/.Aries/config/setting.json。"""
    return set_approval_mode(payload.mode)
