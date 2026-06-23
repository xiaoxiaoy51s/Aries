"""Main Agent Config API - 主 Agent 配置管理

前端通过这些 API 读取/保存 ~/.Aries/agent/main_agent.json
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from utils.main_agent_config import (
    load_main_agent_config,
    save_main_agent_config,
    ensure_main_agent_config_exists,
)

router = APIRouter(prefix="/main-agent", tags=["main-agent"])


class MainAgentConfigUpdate(BaseModel):
    allowed_skills: list[str] = []
    allowed_mcps: list[str] = []


@router.get("/config")
async def get_main_agent_config():
    """读取主 Agent 配置。"""
    ensure_main_agent_config_exists()
    return load_main_agent_config()


@router.put("/config")
async def update_main_agent_config(config: MainAgentConfigUpdate):
    """保存主 Agent 配置。"""
    data = config.model_dump()
    save_main_agent_config(data)
    return {"success": True, "data": load_main_agent_config()}
