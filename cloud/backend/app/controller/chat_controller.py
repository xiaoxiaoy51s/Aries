from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.interceptor.auth_interceptor import get_current_user
from app.model.user import User
from app.service.chat_service import ChatService
from app.service.session_service import SessionService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/chat", tags=["chat"])


class SendRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


class SessionResponse(BaseModel):
    id: str
    user_id: int
    title: str
    is_pinned: bool
    created_at: datetime

    class Config:
        from_attributes = True


class RenameRequest(BaseModel):
    title: str


class PinRequest(BaseModel):
    is_pinned: bool


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
            db, user.email, user.id, req.session_id, req.message
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
    await SessionService.rename_session(db, session_id, req.title)
    return {"status": "ok"}


@router.put("/sessions/{session_id}/pin")
async def toggle_pin(
    session_id: str,
    req: PinRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await SessionService.toggle_pin(db, session_id, req.is_pinned)
    return {"status": "ok"}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await SessionService.delete_session(db, session_id)
    return {"status": "ok"}
