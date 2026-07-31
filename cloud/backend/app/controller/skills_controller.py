"""技能管理 API。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.engine import skills_manager as mgr
from app.interceptor.auth_interceptor import get_current_user
from app.model.user import User
from app.service.skill_compliance import check_compliance

router = APIRouter(prefix="/api/skills", tags=["skills"])


class SkillPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = ""
    body: str = ""
    enabled: bool = True
    avatar: str = ""


class MainEnabledRequest(BaseModel):
    enabled: bool


class SkillsConfigUpdate(BaseModel):
    main_enabled: list[str] | None = None


@router.get("")
async def list_skills(user: User = Depends(get_current_user)):
    mgr.ensure_skills_config(user.email)
    entries = mgr.discover_skills(user.email, apply_main_filter=False)
    return {"skills": [e.to_api_dict() for e in entries]}


@router.get("/config")
async def get_config(user: User = Depends(get_current_user)):
    return mgr.ensure_skills_config(user.email)


@router.put("/config")
async def update_config(req: SkillsConfigUpdate, user: User = Depends(get_current_user)):
    return mgr.save_skills_config(user.email, main_enabled=req.main_enabled)


@router.get("/{name}")
async def get_skill(name: str, user: User = Depends(get_current_user)):
    entry = mgr.get_skill_by_name(name, user.email)
    if not entry:
        raise HTTPException(status_code=404, detail="技能不存在")
    return entry.to_api_dict(include_content=True)


@router.get("/{name}/icon")
async def get_skill_icon(name: str, user: User = Depends(get_current_user)):
    entry = mgr.get_skill_by_name(name, user.email)
    if not entry or not entry.icon_path or not entry.icon_path.exists():
        raise HTTPException(status_code=404, detail="无头像")
    return FileResponse(entry.icon_path)


@router.post("")
async def create_skill(req: SkillPayload, user: User = Depends(get_current_user)):
    try:
        entry = mgr.save_skill(user.email, req.model_dump())
        return entry.to_api_dict(include_content=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/upload")
async def upload_skill(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """上传技能包 zip，自动做合规检测后保存。"""
    # 1. 读取并校验文件
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="压缩包过大（上限 20MB）")
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持 .zip 格式")

    # 2. 解压到临时目录
    try:
        skill_dir, skill_name = mgr.extract_skill_zip(raw, user.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # 3. 合规检测
    try:
        compliance = await check_compliance(user.email, skill_dir)
    except Exception as e:
        mgr.cleanup_temp_dir(skill_dir)
        raise HTTPException(status_code=500, detail=f"合规检测失败: {e}") from e

    # 4. 如果不通过，返回检测结果但不保存
    if not compliance.get("passed", False):
        mgr.cleanup_temp_dir(skill_dir)
        return {
            "success": False,
            "compliance": compliance,
            "skill": None,
        }

    # 5. 保存技能
    try:
        entry = mgr.save_skill_from_dir(user.email, skill_dir, skill_name)
    except ValueError as e:
        mgr.cleanup_temp_dir(skill_dir)
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        mgr.cleanup_temp_dir(skill_dir)

    return {
        "success": True,
        "compliance": compliance,
        "skill": entry.to_api_dict(include_content=True),
    }


@router.put("/{name}")
async def update_skill(name: str, req: SkillPayload, user: User = Depends(get_current_user)):
    existing = mgr.get_skill_by_name(name, user.email)
    if not existing:
        raise HTTPException(status_code=404, detail="技能不存在")
    if existing.scope != "private":
        raise HTTPException(status_code=400, detail="官方技能不可直接编辑，请新建同名私有副本")
    payload = req.model_dump()
    payload["name"] = name
    try:
        entry = mgr.save_skill(user.email, payload)
        return entry.to_api_dict(include_content=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{name}")
async def delete_skill(name: str, user: User = Depends(get_current_user)):
    existing = mgr.get_skill_by_name(name, user.email)
    if not existing:
        raise HTTPException(status_code=404, detail="技能不存在")
    if existing.scope != "private":
        raise HTTPException(status_code=400, detail="官方技能不可删除")
    ok = mgr.delete_skill(user.email, name)
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
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
