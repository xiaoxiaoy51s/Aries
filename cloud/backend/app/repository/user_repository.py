from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.user import User


class UserRepository:
    """用户数据访问层"""

    @staticmethod
    async def find_by_email(db: AsyncSession, email: str) -> User | None:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    @staticmethod
    async def find_by_username(db: AsyncSession, username: str) -> User | None:
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    @staticmethod
    async def find_by_id(db: AsyncSession, user_id: int) -> User | None:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, **kwargs) -> User:
        user = User(**kwargs)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user
