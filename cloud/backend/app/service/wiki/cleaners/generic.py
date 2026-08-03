"""通用清洗器（未识别平台时兜底）。"""
from __future__ import annotations

from app.service.wiki.cleaners.base import BaseCleaner


class GenericCleaner(BaseCleaner):
    platform = "generic"
    NOISE: set[str] = set()
    BODY_SELECTORS = ("article", "main")
