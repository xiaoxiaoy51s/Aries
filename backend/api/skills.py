from typing import Any

from fastapi import APIRouter, HTTPException
import shutil

from engine.skills_manager import discover_skills, get_skill_by_folder_name
from engine.plugin_manager import discover_plugins

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _plugin_skill_entry_to_api(plugin: Any) -> dict:
    """把内置插件 skill 转为 skills API 需要的格式。"""
    return {
        "folder_name": plugin.name,
        "name": plugin.display_name,
        "description": plugin.description,
        "path": plugin.target_path,
        "enabled": plugin.enabled,
        "group": "builtin",
    }


@router.get("")
async def list_skills():
    """返回所有技能列表（用户 skills + 内置插件 skills）。"""
    entries = discover_skills()
    result = [e.to_api_dict() for e in entries]

    try:
        for plugin in discover_plugins():
            if plugin.kind == "skills":
                result.append(_plugin_skill_entry_to_api(plugin))
    except Exception:
        pass

    return {"skills": result}


@router.get("/{folder_name}")
async def get_skill_detail(folder_name: str):
    """返回技能详情（含 SKILL.md 全文）。"""
    entry = get_skill_by_folder_name(folder_name)
    if entry is not None:
        return {
            "folder_name": entry.folder_name,
            "name": entry.name,
            "description": entry.description,
            "enabled": entry.enabled,
            "skill_path": str(entry.skill_path),
            "skill_md_path": str(entry.skill_md_path),
            "content": entry.content,
        }

    # 查找内置插件 skill
    try:
        from pathlib import Path
        from engine.skills_manager import parse_skill_markdown
        for plugin in discover_plugins():
            if plugin.kind == "skills" and plugin.name == folder_name:
                target = Path(plugin.target_path)
                skill_md = target / "SKILL.md"
                if not skill_md.is_file():
                    skill_md = target / "skill.md"
                if not skill_md.is_file():
                    continue
                parsed = parse_skill_markdown(skill_md, default_name=plugin.name)
                return {
                    "folder_name": plugin.name,
                    "name": parsed["name"],
                    "description": parsed["description"],
                    "enabled": plugin.enabled,
                    "skill_path": str(target),
                    "skill_md_path": str(skill_md),
                    "content": parsed["content"],
                }
    except Exception:
        pass

    raise HTTPException(status_code=404, detail=f"技能 {folder_name} 不存在")


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
