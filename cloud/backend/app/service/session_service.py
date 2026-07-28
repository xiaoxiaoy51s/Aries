from sqlalchemy.ext.asyncio import AsyncSession

from app.model.session import Session, Message
from app.repository.session_repository import SessionRepository, MessageRepository
from app.utils.session_logger import read_jsonl_events, reconstruct_from_events


class SessionService:
    """会话业务逻辑层"""

    @staticmethod
    async def create_session(db: AsyncSession, session_id: str, user_id: int, title: str = "新对话") -> Session:
        return await SessionRepository.create(
            db, id=session_id, user_id=user_id, title=title
        )

    @staticmethod
    async def list_sessions(db: AsyncSession, user_id: int) -> list[Session]:
        return await SessionRepository.list_by_user(db, user_id)

    @staticmethod
    async def get_session(db: AsyncSession, session_id: str) -> Session | None:
        return await SessionRepository.find_by_id(db, session_id)

    @staticmethod
    async def rename_session(db: AsyncSession, session_id: str, title: str) -> None:
        await SessionRepository.update_title(db, session_id, title)

    @staticmethod
    async def toggle_pin(db: AsyncSession, session_id: str, is_pinned: bool) -> None:
        await SessionRepository.toggle_pin(db, session_id, is_pinned)

    @staticmethod
    async def delete_session(db: AsyncSession, session_id: str) -> None:
        await SessionRepository.delete(db, session_id)

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
