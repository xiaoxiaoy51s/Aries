"""Memory API: 用户自定义约束（rules.md）的读取、保存和 AI 润色。"""
from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from memory.agent_memory import (
    get_role_rules_path,
    read_role_rules,
    write_role_rules,
)
from models.model_manager import resolve_active_model_config
from prompt.init_agent_memory import INIT_AGENT_MEMORY_PROMPT
from prompt.role_prompts import ROLE_GUIDE, ROLE_POLISH_SYSTEM_PROMPT
from utils.url_utils import normalize_base_url

router = APIRouter(prefix="/memory", tags=["memory"])


class SaveRulesRequest(BaseModel):
    work_dir: Optional[str] = None
    content: str = ""


class PolishRulesRequest(BaseModel):
    work_dir: Optional[str] = None
    content: str = ""
    baseUrl: str = ""
    apiKey: str = ""
    model: str = ""


@router.get("/rules")
async def get_rules(work_dir: Optional[str] = None) -> dict:
    """读取用户自定义约束 rules.md"""
    content = read_role_rules(work_dir)
    path = get_role_rules_path(work_dir)
    return {
        "success": True,
        "content": content,
        "file_path": str(path),
        "exists": bool(content),
    }


@router.post("/rules")
async def save_rules(req: SaveRulesRequest) -> dict:
    """保存用户自定义约束 rules.md"""
    result = write_role_rules(req.work_dir, req.content)
    return result


@router.get("/guide")
async def get_guide() -> dict:
    """获取 rules.md 的填写说明"""
    return {
        "success": True,
        "guide": ROLE_GUIDE,
    }


@router.get("/init-prompt")
async def get_init_prompt() -> dict:
    """获取生成 Agent 记忆的 prompt 模板"""
    return {
        "success": True,
        "prompt": INIT_AGENT_MEMORY_PROMPT,
    }



@router.post("/rules/polish")
async def polish_rules(req: PolishRulesRequest) -> dict:
    """AI 润色用户输入的 rules 草稿"""
    if not req.content.strip():
        return {"success": False, "error": "内容为空", "content": ""}

    base_url, api_key, model = resolve_active_model_config(
        base_url=req.baseUrl, api_key=req.apiKey, model=req.model
    )
    if not base_url or not api_key or not model:
        raise HTTPException(status_code=400, detail="未配置模型 API，请先在设置中配置 baseUrl、apiKey 和 model")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": ROLE_POLISH_SYSTEM_PROMPT},
            {"role": "user", "content": f"请润色以下 rules.md 草稿：\n\n{req.content}"},
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{normalize_base_url(base_url)}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.text)

        result = response.json()
        polished = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {
            "success": True,
            "content": polished.strip(),
        }
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="AI 润色超时，请稍后重试")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 润色失败: {e}")
