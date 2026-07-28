from datetime import datetime

from sqlalchemy import Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    avatar: Mapped[str] = mapped_column(String(500), default="")
    registration_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    membership_level: Mapped[int] = mapped_column(Integer, default=0)  # 0=免费 1=基础 2=专业
    gender: Mapped[int] = mapped_column(Integer, default=0)  # 0=未知 1=男 2=女
    role_type: Mapped[int] = mapped_column(Integer, default=0)  # 0=用户 1=管理员
    status: Mapped[int] = mapped_column(Integer, default=1)  # 0=禁用 1=正常
    signature: Mapped[str] = mapped_column(Text, default="")
