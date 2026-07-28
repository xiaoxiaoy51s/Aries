from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.session import Session, Message


class SessionRepository:
    """会话数据访问层"""

    @staticmethod
    async def create(db: AsyncSession, **kwargs) -> Session:
        session = Session(**kwargs)
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    @staticmethod
    async def find_by_id(db: AsyncSession, session_id: str) -> Session | None:
        result = await db.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_user(db: AsyncSession, user_id: int) -> list[Session]:
        result = await db.execute(
            select(Session)
            .where(Session.user_id == user_id)
            .order_by(desc(Session.is_pinned), desc(Session.created_at))
        )
        return list(result.scalars().all())

    @staticmethod
    async def update_title(db: AsyncSession, session_id: str, title: str) -> None:
        await db.execute(
            update(Session).where(Session.id == session_id).values(title=title)
        )
        await db.commit()

    @staticmethod
    async def toggle_pin(db: AsyncSession, session_id: str, is_pinned: bool) -> None:
        await db.execute(
            update(Session).where(Session.id == session_id).values(is_pinned=is_pinned)
        )
        await db.commit()

    @staticmethod
    async def delete(db: AsyncSession, session_id: str) -> None:
        # 先删消息，再删会话
        msgs = await db.execute(select(Message).where(Message.session_id == session_id))
        for msg in msgs.scalars().all():
            await db.delete(msg)
        result = await db.execute(select(Session).where(Session.id == session_id))
        session = result.scalar_one_or_none()
        if session:
            await db.delete(session)
        await db.commit()


class MessageRepository:
    """消息数据访问层"""

    @staticmethod
    async def create(db: AsyncSession, **kwargs) -> Message:
        message = Message(**kwargs)
        db.add(message)
        await db.commit()
        await db.refresh(message)
        return message

    @staticmethod
    async def list_by_session(db: AsyncSession, session_id: str) -> list[Message]:
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def update_log_path(db: AsyncSession, message_id: int, log_path: str) -> None:
        await db.execute(
            update(Message).where(Message.id == message_id).values(log_path=log_path)
        )
        await db.commit()
