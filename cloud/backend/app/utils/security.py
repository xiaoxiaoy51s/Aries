from datetime import datetime, timedelta

import jwt
from passlib.context import CryptContext

from app.config.settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def mask_secret(value: str, visible_prefix: int = 4, visible_suffix: int = 4) -> str:
    """脱敏敏感字符串，保留首尾少量字符，中间用 * 替代。"""
    if not value:
        return ""
    if len(value) <= visible_prefix + visible_suffix:
        return "*" * len(value)
    hidden_len = len(value) - visible_prefix - visible_suffix
    return value[:visible_prefix] + "*" * hidden_len + value[-visible_suffix:]


def is_masked_secret(value: str) -> bool:
    """判断是否为脱敏占位值（含 * 且非用户新输入的完整密钥）。"""
    return bool(value) and "*" in value
