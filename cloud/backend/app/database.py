import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config.settings import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,
    pool_size=10,
    max_overflow=20,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Bot / Agent 专用事件循环需要独立的数据库连接池（asyncpg 连接绑定 loop）
_loop_session_makers: dict[int, async_sessionmaker] = {}


def async_session_for_loop() -> async_sessionmaker:
    """返回绑定到当前事件循环的 session 工厂（供 bot/agent 线程使用）。"""
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    if loop_id not in _loop_session_makers:
        loop_engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.APP_DEBUG,
            pool_size=3,
            max_overflow=5,
        )
        _loop_session_makers[loop_id] = async_sessionmaker(
            loop_engine, class_=AsyncSession, expire_on_commit=False
        )
    return _loop_session_makers[loop_id]


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    """启动时自动建表（开发阶段使用，生产环境建议用 Alembic 迁移）"""
    import app.model.user  # noqa: F401
    import app.model.session  # noqa: F401
    import app.model.scheduled_task  # noqa: F401
    import app.model.wiki  # noqa: F401

    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 用户名允许重复，唯一性只约束邮箱；清理历史 unique 约束/索引
        await conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key"))
        await conn.execute(text("DROP INDEX IF EXISTS users_username_key"))
        # 旧版 unique=True 留下的是 UNIQUE INDEX ix_users_username，必须先删再重建普通索引
        await conn.execute(text("DROP INDEX IF EXISTS ix_users_username"))
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_users_username ON users (username)")
        )
        # 平台会话 ID 改为 {email}__qq__ 等形式，加宽列避免邮箱过长截断
        try:
            await conn.execute(
                text("ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_session_id_fkey")
            )
            await conn.execute(text("ALTER TABLE sessions ALTER COLUMN id TYPE VARCHAR(255)"))
            await conn.execute(
                text("ALTER TABLE messages ALTER COLUMN session_id TYPE VARCHAR(255)")
            )
            await conn.execute(
                text(
                    "ALTER TABLE messages ADD CONSTRAINT messages_session_id_fkey "
                    "FOREIGN KEY (session_id) REFERENCES sessions(id)"
                )
            )
            await conn.execute(
                text("ALTER TABLE scheduled_tasks ALTER COLUMN session_id TYPE VARCHAR(255)")
            )
        except Exception:
            # 非 Postgres 或已加宽时忽略
            pass
        try:
            await conn.execute(
                text(
                    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS workspace_dir "
                    "VARCHAR(200) DEFAULT 'default'"
                )
            )
            await conn.execute(
                text(
                    "UPDATE sessions SET workspace_dir = 'default' "
                    "WHERE workspace_dir IS NULL OR workspace_dir = ''"
                )
            )
        except Exception:
            pass
