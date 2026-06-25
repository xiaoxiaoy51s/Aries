"""内置插件管理 API

GET    /api/plugins          列出所有内置插件
PUT    /api/plugins/toggle   开关某个插件
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.plugin_manager import discover_plugins, set_plugin_enabled, sync_plugins

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


class PluginToggleRequest(BaseModel):
    kind: str       # skills / tools / agents / mcps
    name: str       # 插件名
    enabled: bool


@router.get("")
async def list_plugins():
    """返回所有内置插件及其开关状态。"""
    return {"plugins": [e.to_api_dict() for e in discover_plugins()]}


@router.put("/toggle")
async def toggle_plugin(req: PluginToggleRequest):
    """开关某个内置插件。"""
    valid_kinds = ("skills", "tools", "agents", "mcps")
    if req.kind not in valid_kinds:
        raise HTTPException(status_code=400, detail=f"kind 必须是 {valid_kinds} 之一")
    set_plugin_enabled(req.kind, req.name, req.enabled)
    return {"success": True, "kind": req.kind, "name": req.name, "enabled": req.enabled}


@router.post("/sync")
async def sync_now():
    """手动触发同步。"""
    counts = sync_plugins()
    return {"success": True, "counts": counts}
