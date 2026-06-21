"""Subagent CRUD API

提供前端 UI 与主 Agent 共用的 Subagent 管理接口。
所有读接口返回结果中 `available` 字段表示该 subagent 当前是否可被主 Agent 路由。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from utils.session_logger import SUBAGENT_LOG_ROOT, read_jsonl_events
from utils.subagent_manager import (
    delete_subagent,
    discover_subagents,
    get_subagent_by_name,
    save_subagent,
    set_subagent_enabled,
)
from utils.subagent_runtime import (
    cancel_subagent as runtime_cancel_subagent,
    list_running_subagents,
)

router = APIRouter(prefix="/api/subagents", tags=["subagents"])


class SubagentPayload(BaseModel):
    name: str
    description: str = ""
    model: str = ""
    fallback_model: str = "default"
    enabled: bool = True
    allowed_skills: list[str] = Field(default_factory=list)
    allowed_mcps: list[str] = Field(default_factory=list)
    system_prompt: str = ""


class SubagentStatusUpdate(BaseModel):
    enabled: bool


@router.get("")
async def list_subagents() -> dict[str, Any]:
    entries = discover_subagents()
    return {"subagents": [e.to_api_dict() for e in entries]}


@router.get("/log")
async def read_subagent_log(path: str = Query(..., description="子 Agent JSONL 日志路径")) -> dict[str, Any]:
    """读取子 Agent 独立 JSONL 日志的事件列表。

    出于安全考虑，路径必须位于 ~/.Aries/session/sub_agent/ 之下。
    """
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="path 不能为空")

    try:
        target = Path(path).expanduser().resolve()
        root = SUBAGENT_LOG_ROOT.resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"路径无效：{exc}") from exc

    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="拒绝访问：路径必须位于子 Agent 日志目录之下") from exc

    if not target.is_file():
        raise HTTPException(status_code=404, detail="日志文件不存在")

    events = read_jsonl_events(str(target))
    return {"path": str(target), "events": events}


@router.get("/runtime/running")
async def list_running_subagent_tasks() -> dict[str, Any]:
    """返回当前正在运行的子 Agent task_id 列表。"""
    return {"task_ids": list_running_subagents()}


@router.post("/runtime/{task_id}/cancel")
async def cancel_running_subagent(task_id: str) -> dict[str, Any]:
    """请求取消正在运行的子 Agent。

    成功设置 cancel_event 后返回 ok=True；任务已结束或不存在返回 ok=False。
    """
    ok = runtime_cancel_subagent(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"子 Agent {task_id} 不在运行中")
    return {"task_id": task_id, "ok": True}


@router.get("/{name}")
async def get_subagent_detail(name: str) -> dict[str, Any]:
    entry = get_subagent_by_name(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Subagent {name} 不存在")
    return entry.to_api_dict()


@router.put("/{name}")
async def upsert_subagent(name: str, payload: SubagentPayload) -> dict[str, Any]:
    if payload.name != name:
        raise HTTPException(status_code=400, detail="路径 name 与请求体 name 不一致")
    try:
        entry = save_subagent(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return entry.to_api_dict()


@router.post("")
async def create_subagent(payload: SubagentPayload) -> dict[str, Any]:
    try:
        entry = save_subagent(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return entry.to_api_dict()


@router.delete("/{name}")
async def remove_subagent(name: str) -> dict[str, Any]:
    try:
        removed = delete_subagent(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail=f"Subagent {name} 不存在")
    return {"name": name, "removed": True}


@router.put("/{name}/status")
async def update_subagent_status(name: str, body: SubagentStatusUpdate) -> dict[str, Any]:
    try:
        entry = set_subagent_enabled(name, body.enabled)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return entry.to_api_dict()
