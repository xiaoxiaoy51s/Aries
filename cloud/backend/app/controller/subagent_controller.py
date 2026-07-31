"""子 Agent 管理 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.engine import subagent_manager as mgr
from app.interceptor.auth_interceptor import get_current_user
from app.model.user import User

router = APIRouter(prefix="/api/subagents", tags=["subagents"])


class SubagentPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = ""
    enabled: bool = True
    allowed_skills: list[str] = Field(default_factory=list)
    allowed_mcps: list[str] = Field(default_factory=list)
    system_prompt: str = ""
    avatar: str = ""


class MainEnabledRequest(BaseModel):
    enabled: bool


class AgentsConfigUpdate(BaseModel):
    main_enabled: list[str] | None = None


@router.get("")
async def list_subagents(user: User = Depends(get_current_user)):
    mgr.ensure_agents_config(user.email)
    entries = mgr.discover_subagents(user.email, apply_main_filter=False)
    return {"subagents": [e.to_api_dict() for e in entries]}


@router.get("/config")
async def get_config(user: User = Depends(get_current_user)):
    cfg = mgr.ensure_agents_config(user.email)
    return cfg


@router.put("/config")
async def update_config(req: AgentsConfigUpdate, user: User = Depends(get_current_user)):
    return mgr.save_agents_config(user.email, main_enabled=req.main_enabled)


@router.get("/{name}")
async def get_subagent(name: str, user: User = Depends(get_current_user)):
    entry = mgr.get_subagent_by_name(name, user.email)
    if not entry:
        raise HTTPException(status_code=404, detail="子 Agent 不存在")
    return entry.to_api_dict()


@router.get("/{name}/icon")
async def get_subagent_icon(name: str, user: User = Depends(get_current_user)):
    entry = mgr.get_subagent_by_name(name, user.email)
    if not entry or not entry.icon_path or not entry.icon_path.exists():
        raise HTTPException(status_code=404, detail="无头像")
    return FileResponse(entry.icon_path)


@router.post("")
async def create_subagent(req: SubagentPayload, user: User = Depends(get_current_user)):
    try:
        entry = mgr.save_subagent(user.email, req.model_dump())
        return entry.to_api_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/{name}")
async def update_subagent(name: str, req: SubagentPayload, user: User = Depends(get_current_user)):
    existing = mgr.get_subagent_by_name(name, user.email)
    if not existing:
        raise HTTPException(status_code=404, detail="子 Agent 不存在")
    if existing.scope != "private":
        raise HTTPException(status_code=400, detail="公共子 Agent 不可直接编辑，请新建同名私有副本")
    payload = req.model_dump()
    payload["name"] = name
    try:
        entry = mgr.save_subagent(user.email, payload)
        return entry.to_api_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{name}")
async def delete_subagent(name: str, user: User = Depends(get_current_user)):
    existing = mgr.get_subagent_by_name(name, user.email)
    if not existing:
        raise HTTPException(status_code=404, detail="子 Agent 不存在")
    if existing.scope != "private":
        raise HTTPException(status_code=400, detail="公共子 Agent 不可删除")
    ok = mgr.delete_subagent(user.email, name)
    if not ok:
        raise HTTPException(status_code=404, detail="子 Agent 不存在")
    return {"success": True}


@router.put("/{name}/main-enabled")
async def set_main_enabled(
    name: str,
    req: MainEnabledRequest,
    user: User = Depends(get_current_user),
):
    try:
        entry = mgr.set_main_enabled(user.email, name, req.enabled)
        return entry.to_api_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
