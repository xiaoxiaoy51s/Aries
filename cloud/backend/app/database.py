from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config.settings import settings

engine = create_async_engine(settings.DATABASE_URL, echo=settings.APP_DEBUG)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    """启动时自动建表（开发阶段使用，生产环境建议用 Alembic 迁移）"""
    # 确保模型被导入，Base.metadata 才能发现表定义
    import app.model.user  # noqa: F401
    import app.model.session  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
