from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.skills_manager import discover_skills, get_skill_by_folder_name, set_skill_enabled

router = APIRouter(prefix="/api/skills", tags=["skills"])


class SkillStatusUpdate(BaseModel):
    enabled: bool


@router.get("")
async def list_skills():
    """返回所有技能列表（含启用状态）。"""
    entries = discover_skills()
    return {"skills": [e.to_api_dict() for e in entries]}


@router.get("/{folder_name}")
async def get_skill_detail(folder_name: str):
    """返回技能详情（含 SKILL.md 全文）。"""
    entry = get_skill_by_folder_name(folder_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"技能 {folder_name} 不存在")
    return {
        "folder_name": entry.folder_name,
        "name": entry.name,
        "description": entry.description,
        "enabled": entry.enabled,
        "skill_path": str(entry.skill_path),
        "skill_md_path": str(entry.skill_md_path),
        "content": entry.content,
    }


@router.put("/{folder_name}/status")
async def update_skill_status(folder_name: str, body: SkillStatusUpdate):
    """更新单个技能的启用状态。"""
    # 验证技能存在
    found = None
    for entry in discover_skills():
        if entry.folder_name == folder_name:
            found = entry
            break
    if found is None:
        raise HTTPException(status_code=404, detail=f"技能 {folder_name} 不存在")
    try:
        set_skill_enabled(folder_name, body.enabled)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"folder_name": folder_name, "enabled": body.enabled}
