"""定时任务 ORM 模型。

参照 backend/db/scheduled_task.py 的字段定义，适配 SQLAlchemy async。
"""
from datetime import datetime

from sqlalchemy import Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.time_utils import local_now_iso


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    task_content: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_at: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    schedule_type: Mapped[str] = mapped_column(String(20), default="once")
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_delete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(32), default=local_now_iso)
    updated_at: Mapped[str] = mapped_column(String(32), default=local_now_iso)
    executed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
