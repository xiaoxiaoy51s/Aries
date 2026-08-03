"""链接正文图片的提取与下载。

- 从 HTML 提取正文图片 URL（含 data-src 懒加载），过滤装饰图（图标/头像/二维码）。
- 并发下载到 raw/links/{name}_imgs/，供溯源与 playwright 兜底复用。
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from app.config.settings import settings

_IMG_URL_RE = re.compile(r'<img[^>]+(?:data-src|src)=["\']([^"\']+)["\']', re.IGNORECASE)
_IMG_SUFFIX = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
# URL 特征命中即视为装饰图，跳过
_DECOR_HINTS = (
    "icon", "emoji", "avatar", "logo", "qr", "qrcode", "share", "close",
    "delete", "arrow", "bg_", "sprite", "loading", "placeholder",
)


def extract_img_urls(html: str, limit: int | None = None) -> list[str]:
    """从 HTML 提取正文图片 URL（去重、过滤 data: 与装饰图）。"""
    limit = limit or settings.KB_OCR_MAX_IMAGES
    urls: list[str] = []
    for m in _IMG_URL_RE.findall(html or ""):
        u = m.strip()
        low = u.lower()
        if not u or low.startswith("data:") or any(h in low for h in _DECOR_HINTS):
            continue
        if u not in urls:
            urls.append(u)
    return urls[:limit]


async def download_images(urls: list[str], dest_dir: Path) -> list[Path]:
    """并发下载图片到 dest_dir，返回成功下载的本地路径列表。"""
    import httpx

    dest_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    sem = asyncio.Semaphore(4)

    async def _dl(i: int, u: str) -> None:
        async with sem:
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=8.0, read=15.0), trust_env=False,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"},
                ) as client:
                    resp = await client.get(u)
                if resp.status_code != 200 or len(resp.content) < 1024:
                    return
                suffix = Path(u.split("?")[0]).suffix.lower()
                if suffix not in _IMG_SUFFIX:
                    suffix = ".jpg"
                p = dest_dir / f"img_{i + 1:03d}{suffix}"
                await asyncio.to_thread(p.write_bytes, resp.content)
                saved.append(p)
            except Exception:
                pass

    await asyncio.gather(*[_dl(i, u) for i, u in enumerate(urls)])
    return saved
