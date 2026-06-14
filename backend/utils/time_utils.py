"""统一时间工具：全链路使用系统本地时间（与日志、界面一致）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def local_now() -> datetime:
    """当前本地时间（naive datetime，用于计算）。"""
    return datetime.now().astimezone().replace(tzinfo=None)


def local_now_iso() -> str:
    """当前本地时间，ISO 字符串（无时区后缀），用于数据库存储与比较。"""
    return local_now().isoformat(timespec="microseconds")


def normalize_local_iso(value: str) -> str:
    """将任意 ISO 时间字符串规范为本地 ISO（无时区后缀）。"""
    if not value or not str(value).strip():
        return value
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        # 无时区后缀：视为本地时间（datetime-local / 数据库存储格式）
        return dt.isoformat(timespec="microseconds")
    return dt.astimezone().replace(tzinfo=None).isoformat(timespec="microseconds")


def parse_local_iso(value: str) -> datetime:
    """解析本地 ISO 字符串为 naive datetime。"""
    return datetime.fromisoformat(normalize_local_iso(value))


def local_now_str() -> str:
    """当前本地时间，用于日志（与 logging 默认 asctime 一致）。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def local_iso_to_display(value: str) -> str:
    """本地 ISO → 可读字符串，用于日志展示。"""
    if not value or not str(value).strip():
        return ""
    try:
        dt = datetime.fromisoformat(normalize_local_iso(value))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return str(value)


def local_now_plus_seconds_iso(seconds: int) -> str:
    return (local_now() + timedelta(seconds=seconds)).isoformat(timespec="microseconds")


def local_now_minus(*, minutes: int = 0, seconds: int = 0) -> str:
    return (local_now() - timedelta(minutes=minutes, seconds=seconds)).isoformat(timespec="microseconds")


def utc_naive_to_local_iso(value: str) -> str:
    """将旧库中按 UTC 存储的无时区 ISO 转为本地 ISO（一次性迁移用）。"""
    if not value or not str(value).strip():
        return value
    s = str(value).strip().replace("Z", "")
    dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    return dt.astimezone().replace(tzinfo=None).isoformat(timespec="microseconds")
