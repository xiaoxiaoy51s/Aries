from fastapi import APIRouter, HTTPException
import shutil

from utils.skills_manager import discover_skills, get_skill_by_folder_name, SKILLS_ROOT

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
async def list_skills():
    """返回所有技能列表。"""
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


@router.delete("/{folder_name}")
async def delete_skill(folder_name: str):
    """删除技能目录。"""
    entry = get_skill_by_folder_name(folder_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"技能 {folder_name} 不存在")
    try:
        shutil.rmtree(str(entry.skill_path))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"删除失败: {exc}") from exc
    return {"success": True, "folder_name": folder_name}