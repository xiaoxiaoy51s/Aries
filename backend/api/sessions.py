from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from db.chat import (
    save_message,
    update_message,
    get_session_messages,
    list_recent_sessions,
    delete_session,
    get_conversation_history,
    get_recent_messages,
)
from db.database import get_connection
from db.sessions import (
    upsert_session,
    get_session as get_session_meta,
    list_sessions as list_session_meta,
    delete_session_meta,
)
from utils.session_logger import resolve_message_log_events

router = APIRouter(prefix="/sessions", tags=["sessions"])


class MessageCreate(BaseModel):
    session_id: str
    role: str
    content: str
    reasoning_content: Optional[str] = None
    image_path: Optional[str] = None
    message_snapshot_json: Optional[str] = None


class MessageUpdate(BaseModel):
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    image_path: Optional[str] = None
    message_snapshot_json: Optional[str] = None


class SessionMetaUpdate(BaseModel):
    title: Optional[str] = None
    work_dir: Optional[str] = None


@router.get("/")
def list_sessions(limit: int = 30):
    """列出所有会话，合并 sessions 表元数据 + 最后一条用户消息作为预览。"""
    meta_map = {m["session_id"]: m for m in list_session_meta(limit=limit * 2)}
    recent = list_recent_sessions(limit=limit)

    # 以 sessions 表里的会话为主，但补上最近消息列表里没在 sessions 表里的
    seen = set()
    items: list[dict] = []
    for s in recent:
        sid = s["session_id"]
        seen.add(sid)
        meta = meta_map.get(sid, {})
        items.append({
            "session_id": sid,
            "title": meta.get("title") or s.get("last_user_message") or "",
            "work_dir": meta.get("work_dir", ""),
            "created_at": meta.get("created_at") or s.get("created_at") or "",
            "updated_at": meta.get("updated_at") or s.get("created_at") or "",
            "last_user_message": s.get("last_user_message") or "",
        })

    # 补 sessions 表里没有消息记录的（理论上不应出现，但兜底）
    for sid, m in meta_map.items():
        if sid in seen:
            continue
        items.append({
            "session_id": sid,
            "title": m.get("title", ""),
            "work_dir": m.get("work_dir", ""),
            "created_at": m.get("created_at", ""),
            "updated_at": m.get("updated_at", ""),
            "last_user_message": "",
        })

    # 按 updated_at 倒序
    items.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)
    items = items[:limit]
    return {"sessions": items, "total": len(items)}


@router.get("/projects")
def list_projects():
    """按 work_dir 去重分组，返回项目（工作目录）列表及其下的 session。"""
    meta_list = list_session_meta(limit=1000)

    # 按 work_dir 分组（排除 __project_mimoclaw__ 这种配置项）
    projects: dict[str, list[dict]] = {}
    for m in meta_list:
        sid = m.get("session_id", "")
        wd = m.get("work_dir", "")
        if sid.startswith("__") and sid.endswith("__"):
            continue  # 跳过系统配置项
        if not wd:
            wd = "__default__"  # 无工作目录的归到默认项目
        projects.setdefault(wd, []).append({
            "session_id": sid,
            "title": (m.get("title") or "").strip()[:18],
            "created_at": m.get("created_at", ""),
            "updated_at": m.get("updated_at", ""),
        })

    # 组装返回结构
    result = []
    for wd, sessions in sorted(projects.items(), key=lambda x: x[1][0].get("updated_at", ""), reverse=True):
        name = "New project" if wd == "__default__" else wd.replace("\\", "/").rstrip("/").split("/")[-1]
        result.append({
            "work_dir": wd if wd != "__default__" else "",
            "name": name,
            "sessions": sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True),
        })
    return {"projects": result, "total": len(result)}


@router.get("/{session_id}")
def get_session_detail(session_id: str):
    meta = get_session_meta(session_id) or {
        "session_id": session_id, "title": "", "work_dir": "",
        "created_at": "", "updated_at": "",
    }
    last_msg = get_recent_messages(session_id, limit=1)
    if last_msg:
        meta["last_message"] = last_msg[0]
    return meta


@router.put("/{session_id}")
def update_session_meta_api(session_id: str, payload: SessionMetaUpdate):
    upsert_session(
        session_id=session_id,
        title=payload.title,
        work_dir=payload.work_dir,
    )
    return {"success": True, "session_id": session_id}


@router.get("/{session_id}/messages")
def get_messages(session_id: str, limit: int = 100):
    messages = get_session_messages(session_id, limit=limit)
    return {
        "session_id": session_id,
        "messages": messages,
        "total": len(messages),
    }


@router.get("/{session_id}/history")
def get_history(session_id: str, limit: int = 20, user_only: bool = False):
    history = get_conversation_history(session_id, limit=limit, user_only=user_only)
    return {
        "session_id": session_id,
        "history": history,
    }


@router.post("/messages")
def create_message(message: MessageCreate):
    message_id = save_message(
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        reasoning_content=message.reasoning_content,
        image_path=message.image_path,
        message_snapshot_json=message.message_snapshot_json,
    )
    # 自动建/更新 session 元数据：用第一条 user 消息作为标题（18 字 + 省略号）
    if message.role == "user":
        first_user = get_recent_messages(message.session_id, limit=1)
        if first_user and first_user[0]["id"] == message_id:
            raw = (message.content or "").strip().replace("\n", " ")
            title = raw[:18] + ("…" if len(raw) > 18 else "")
            upsert_session(
                session_id=message.session_id,
                title=title or "新对话",
            )
        else:
            upsert_session(session_id=message.session_id)
    return {
        "success": True,
        "message_id": message_id,
    }


@router.put("/messages/{message_id}")
def update_message_api(message_id: int, message: MessageUpdate):
    update_message(
        message_id,
        content=message.content,
        reasoning_content=message.reasoning_content,
        image_path=message.image_path,
        message_snapshot_json=message.message_snapshot_json,
    )
    return {
        "success": True,
        "message_id": message_id,
    }


@router.delete("/{session_id}")
def delete_session_api(session_id: str):
    delete_session(session_id)
    delete_session_meta(session_id)
    return {"success": True, "message": "会话已删除"}


@router.get("/messages/{message_id}/jsonl")
def get_message_jsonl(message_id: int):
    """返回消息的 JSONL 事件（思考、工具、回复）。message_snapshot_json 存文件路径。"""
    conn = get_connection()
    row = conn.execute(
        "SELECT message_snapshot_json FROM chat_messages WHERE id = ?",
        (message_id,),
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="消息不存在")

    snapshot_field = row[0] if row[0] else None
    events = resolve_message_log_events(snapshot_field)
    jsonl_path = snapshot_field if snapshot_field and str(snapshot_field).endswith(".jsonl") else None
    return {"message_id": message_id, "jsonl_path": jsonl_path, "events": events}
