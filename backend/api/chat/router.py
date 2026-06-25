"""聊天 API 路由"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.modes import resolve_confirmation, clear_todos

from .models import (
    ChatRequest,
    VisionRequest,
    StopChatRequest,
    ConfirmToolRequest,
    ClearTodosRequest,
    TempChatRequest,
)
from .chat import stream_chat, chat_completions, temp_chat
from .vision import chat_vision
from .background import (
    stop_chat_handler,
    chat_status_handler,
    resume_chat_handler,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/completions")
async def chat_completions_endpoint(request: ChatRequest, http_request: Request):
    return await chat_completions(request, http_request)


@router.post("/stop")
async def stop_chat(body: StopChatRequest):
    session_id = (body.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id 不能为空")
    return await stop_chat_handler(session_id)


@router.get("/status/{session_id}")
async def chat_status(session_id: str):
    """检查该 session 是否有正在运行的后台任务。"""
    return await chat_status_handler(session_id)


@router.get("/resume/{session_id}")
async def resume_chat(session_id: str, http_request: Request):
    """前端切回对话时恢复 SSE 流，从 session queue 中继续读取后台任务的事件。"""
    return await resume_chat_handler(session_id, http_request)


@router.post("/vision")
async def chat_vision_endpoint(request: VisionRequest, http_request: Request):
    return await chat_vision(request, http_request)


@router.get("/sessions/recent")
async def get_recent_sessions(limit: int = 30):
    from db.chat import list_recent_sessions
    sessions = list_recent_sessions(limit=limit)
    return sessions


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, limit: int = 100):
    from db.chat import get_session_messages as get_messages
    messages = get_messages(session_id, limit=limit)
    return messages


@router.post("/confirm-tool")
async def confirm_tool(req: ConfirmToolRequest):
    ok = resolve_confirmation(req.tool_call_id, req.confirmed)
    if not ok:
        raise HTTPException(status_code=404, detail="未找到待确认的工具调用")
    return {"status": "ok", "confirmed": req.confirmed}


@router.post("/clear-todos")
async def clear_todos_endpoint(req: ClearTodosRequest):
    ok = clear_todos(req.session_id)
    if not ok:
        raise HTTPException(status_code=400, detail="session_id 无效")
    return {"status": "ok"}


@router.get("/todos/{session_id}")
async def get_todos_endpoint(session_id: str):
    from utils.todo_store import get_todos as store_get_todos
    todos = store_get_todos(session_id)
    return {"status": "ok", "todos": todos}


@router.post("/temp")
async def temp_chat_endpoint(req: TempChatRequest, http_request: Request):
    """临时对话：加载 session 上下文 + 临时消息，流式返回，不存 DB。"""
    return await temp_chat(req, http_request)