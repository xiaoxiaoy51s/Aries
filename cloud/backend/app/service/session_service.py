from sqlalchemy.ext.asyncio import AsyncSession

from app.exception.auth_exception import SessionNotFoundError
from app.model.session import Session, Message
from app.repository.session_repository import SessionRepository, MessageRepository
from app.tools.sandbox import ensure_workspace
from app.utils.session_logger import (
    read_jsonl_events,
    reconstruct_from_events,
    delete_session_log_files,
)


class SessionService:
    """会话业务逻辑层"""

    @staticmethod
    async def _get_owned_session(db: AsyncSession, session_id: str, user_id: int) -> Session:
        session = await SessionRepository.find_by_id(db, session_id)
        if not session or session.user_id != user_id:
            raise SessionNotFoundError()
        return session

    @staticmethod
    async def create_session(
        db: AsyncSession,
        session_id: str,
        user_id: int,
        title: str = "新对话",
        *,
        user_email: str = "",
        workspace_dir: str = "default",
    ) -> Session:
        ws = (workspace_dir or "default").strip() or "default"
        if user_email:
            ensure_workspace(user_email, ws)
        return await SessionRepository.create(
            db,
            id=session_id,
            user_id=user_id,
            title=title,
            workspace_dir=ws,
        )

    @staticmethod
    async def list_sessions(db: AsyncSession, user_id: int) -> list[Session]:
        return await SessionRepository.list_by_user(db, user_id)

    @staticmethod
    async def get_session(db: AsyncSession, session_id: str) -> Session | None:
        return await SessionRepository.find_by_id(db, session_id)

    @staticmethod
    async def rename_session(
        db: AsyncSession,
        session_id: str,
        user_id: int,
        title: str,
    ) -> None:
        await SessionService._get_owned_session(db, session_id, user_id)
        clean_title = (title or "").strip()
        if not clean_title:
            raise ValueError("标题不能为空")
        if len(clean_title) > 200:
            clean_title = clean_title[:200]
        await SessionRepository.update_title(db, session_id, clean_title)

    @staticmethod
    async def set_workspace(
        db: AsyncSession,
        session_id: str,
        user_id: int,
        user_email: str,
        workspace_dir: str,
    ) -> None:
        await SessionService._get_owned_session(db, session_id, user_id)
        ws = (workspace_dir or "").strip()
        if not ws:
            raise ValueError("工作目录名称不能为空")
        ensure_workspace(user_email, ws)
        await SessionRepository.update_workspace_dir(db, session_id, ws)

    @staticmethod
    async def toggle_pin(
        db: AsyncSession,
        session_id: str,
        user_id: int,
        is_pinned: bool,
    ) -> None:
        await SessionService._get_owned_session(db, session_id, user_id)
        await SessionRepository.toggle_pin(db, session_id, is_pinned)

    @staticmethod
    async def delete_session(
        db: AsyncSession,
        session_id: str,
        user_id: int,
        user_email: str,
    ) -> None:
        await SessionService._get_owned_session(db, session_id, user_id)
        messages = await MessageRepository.list_by_session(db, session_id)
        log_paths = [m.log_path for m in messages if m.log_path]
        await SessionRepository.delete(db, session_id)
        delete_session_log_files(user_email, session_id, log_paths)

    @staticmethod
    async def delete_by_workspace(
        db: AsyncSession,
        user_id: int,
        user_email: str,
        workspace_name: str,
    ) -> None:
        """删除工作目录下的所有会话。"""
        sessions = await SessionRepository.list_by_workspace(db, user_id, workspace_name)
        for s in sessions:
            messages = await MessageRepository.list_by_session(db, s.id)
            log_paths = [m.log_path for m in messages if m.log_path]
            await SessionRepository.delete(db, s.id)
            delete_session_log_files(user_email, s.id, log_paths)

    @staticmethod
    async def rename_workspace(
        db: AsyncSession,
        user_id: int,
        old_name: str,
        new_name: str,
    ) -> None:
        """批量更新工作目录名下所有 session 的 workspace_dir。"""
        await SessionRepository.update_workspace_by_name(db, user_id, old_name, new_name)

    @staticmethod
    async def get_messages(db: AsyncSession, session_id: str) -> list[dict]:
        """获取会话的所有消息，返回原始 JSONL 事件列表以保持事件顺序。

        assistant 消息同时返回:
          - events: 原始 JSONL 事件列表（按时间顺序，前端据此渲染 blocks）
          - content / reasoning_content / token_usage / model / duration_ms:
            兼容性字段（由事件重建）
        """
        messages = await MessageRepository.list_by_session(db, session_id)
        result = []
        for msg in messages:
            entry = {
                "id": msg.id,
                "role": msg.role,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "log_path": msg.log_path,
            }
            if msg.log_path:
                events = read_jsonl_events(msg.log_path)
                content = reconstruct_from_events(events)
                if msg.role == "user":
                    entry["content"] = content["user_content"]
                    entry["image_urls"] = content["image_urls"]
                else:
                    # 返回原始事件列表，前端按顺序渲染 reasoning/tool/text blocks
                    entry["events"] = events
                    entry["content"] = content["assistant_content"]
                    entry["reasoning_content"] = content["reasoning_content"]
                    entry["token_usage"] = content["token_usage"]
                    entry["model"] = content["model"]
                    entry["duration_ms"] = content["duration_ms"]
            else:
                entry["content"] = ""
                entry["reasoning_content"] = ""
                entry["image_urls"] = []
                entry["token_usage"] = {}
                entry["model"] = ""
                if msg.role == "assistant":
                    entry["events"] = []
            result.append(entry)
        return result
