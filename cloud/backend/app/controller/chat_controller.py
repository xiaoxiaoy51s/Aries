from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.interceptor.auth_interceptor import get_current_user
from app.model.user import User
from app.service.chat_service import ChatService
from app.service.session_search_service import SessionSearchService
from app.service.session_service import SessionService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/chat", tags=["chat"])


class SendRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = ""
    images: list[str] | None = None
    agent_name: Optional[str] = None
    workspace_dir: Optional[str] = None
    skills: list[str] | None = None
    use_kb: bool = False


class SessionResponse(BaseModel):
    id: str
    user_id: int
    title: str
    workspace_dir: str
    is_pinned: bool
    created_at: datetime

    class Config:
        from_attributes = True


class RenameRequest(BaseModel):
    title: str


class PinRequest(BaseModel):
    is_pinned: bool


class WorkspaceRequest(BaseModel):
    workspace_dir: str


# ============ 对话接口 ============

@router.post("/stream")
async def stream(
    req: SendRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """流式对话接口（SSE），输出 reasoning + content"""
    async def sse_generator():
        async for chunk in ChatService.chat_stream(
            db,
            user.email,
            user.id,
            req.session_id,
            req.message,
            images=req.images,
            as_agent=(req.agent_name or "").strip(),
            workspace_dir=(req.workspace_dir or "").strip() or None,
            skills=req.skills,
            use_kb=req.use_kb,
        ):
            yield chunk

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ============ 会话管理接口 ============

@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions = await SessionService.list_sessions(db, user.id)
    return [SessionResponse.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    messages = await SessionService.get_messages(db, session_id)
    return messages


@router.put("/sessions/{session_id}/title")
async def rename_session(
    session_id: str,
    req: RenameRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await SessionService.rename_session(db, session_id, user.id, req.title)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}


@router.put("/sessions/{session_id}/pin")
async def toggle_pin(
    session_id: str,
    req: PinRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await SessionService.toggle_pin(db, session_id, user.id, req.is_pinned)
    return {"status": "ok"}


@router.put("/sessions/{session_id}/workspace")
async def set_session_workspace(
    session_id: str,
    req: WorkspaceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await SessionService.set_workspace(
            db, session_id, user.id, user.email, req.workspace_dir
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "workspace_dir": req.workspace_dir.strip()}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await SessionService.delete_session(db, session_id, user.id, user.email)
    return {"status": "ok"}


@router.get("/search")
async def search_messages(
    q: str,
    limit: int = 30,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """在用户 JSONL 聊天日志中搜索消息文本（ripgrep）。"""
    results = await SessionSearchService.search_user_messages(
        db,
        user.id,
        user.email,
        q,
        limit=limit,
    )
    return {"query": q.strip(), "results": results}
