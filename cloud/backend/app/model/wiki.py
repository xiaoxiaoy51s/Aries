"""知识库任务数据模型。

知识库文档以纯文件系统形式存储在 ~/.Aries/{email}/wiki/ 下（文件夹由 AI 组织），
不再使用数据库表记录页面与向量，仅保留异步任务队列。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.time_utils import local_now


class KbJob(Base):
    """知识库异步任务（ingest_text / ingest_file / ingest_link）。"""

    __tablename__ = "kb_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # ingest_text|ingest_file|ingest_link
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|done|failed
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=local_now)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
