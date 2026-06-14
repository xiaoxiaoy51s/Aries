from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.skills_manager import discover_skills
from db.skill_status import set_skill_status

router = APIRouter(prefix="/api/skills", tags=["skills"])


class SkillStatusUpdate(BaseModel):
    enabled: bool


@router.get("")
async def list_skills():
    """返回所有技能列表（含启用状态）。"""
    entries = discover_skills()
    return {"skills": [e.to_api_dict() for e in entries]}


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
    set_skill_status(folder_name, body.enabled)
    return {"folder_name": folder_name, "enabled": body.enabled}
