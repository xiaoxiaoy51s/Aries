"""playwright 渲染抓取：兜底 JS 渲染页（小红书/知乎等静态抓不到正文的场景）。

仅在 httpx 静态抓取判空（_looks_like_js_page）时使用：
- headless chromium 打开页面，滚动触发懒加载；
- 从候选选择器提取正文文本，同时收集正文图片 URL（过滤装饰图）；
- 返回渲染后的 HTML 供溯源。

图片下载：小红书 xhscdn 等图床有严格防盗链（httpx / JS fetch / API request 均 403），
只有浏览器原生 <img> 请求能成功。因此下载采用「监听 response 事件」方式，
把浏览器自己成功下载的图片响应体截获保存，天然复用页面 cookies/请求头。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.config.settings import settings
from app.service.wiki.cleaners import get_cleaner

# 装饰图 URL 特征（头像/图标/logo/二维码等），与 ocr.extract_img_urls 保持同一思路
_DECOR_HINTS = (
    "icon", "emoji", "avatar", "logo", "qr", "qrcode", "share", "close",
    "delete", "arrow", "bg_", "sprite", "loading", "placeholder",
)

_IMG_SUFFIX = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


async def fetch_rendered(
    url: str,
    timeout: float = 45.0,
    download_dir: Path | None = None,
    platform: str = "",
) -> tuple[str, str, list[str], list[Path]]:
    """用 headless chromium 打开 url，返回 (正文文本, 渲染后 HTML, 正文图片 URL, 下载的图片路径)。

    platform 决定正文候选选择器（取自 cleaners 包对应平台的 BODY_SELECTORS）。
    传入 download_dir 时，通过监听浏览器原生图片请求，把成功下载的正文图片
    保存到该目录（可绕过 xhscdn 等防盗链）。未安装 playwright 或浏览器缺失时
    返回 ("", "", [], [])，由调用方降级处理。
    """
    selectors = get_cleaner(platform).body_selectors
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "", "", [], []

    saved: list[Path] = []
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception:
            return "", "", [], []
        try:
            ctx = await browser.new_context(
                user_agent=_UA,
                viewport={"width": 1280, "height": 2000},
                locale="zh-CN",
            )
            page = await ctx.new_page()

            # 截获浏览器成功下载的正文图片响应体
            captured: list[tuple[str, bytes]] = []
            pending: list[asyncio.Task] = []

            async def _capture(resp) -> None:
                try:
                    if resp.status != 200 or resp.request.resource_type != "image":
                        return
                    u = resp.url
                    low = u.lower()
                    if not low.startswith("http") or any(h in low for h in _DECOR_HINTS):
                        return
                    body = await resp.body()
                    if body and len(body) >= 1024:
                        captured.append((u, body))
                except Exception:
                    pass

            def _on_response(resp) -> None:
                task = asyncio.ensure_future(_capture(resp))
                pending.append(task)

            page.on("response", _on_response)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            except Exception:
                pass  # 超时/重定向失败仍尝试提取已有 DOM
            try:
                await page.wait_for_selector(",".join(_CANDIDATE_SELECTORS), timeout=15000)
            except Exception:
                pass
            # 滚动触发图片懒加载
            try:
                await page.evaluate(
                    "async () => { const t = document.scrollingElement || document.body;"
                    " for (let i = 0; i < 30; i++) { t.scrollTop += 500;"
                    " await new Promise(r => setTimeout(r, 200)); } t.scrollTop = 0; }"
                )
                await page.wait_for_timeout(1500)
            except Exception:
                pass

            text = ""
            for sel in selectors:
                try:
                    t = (await page.inner_text(sel)).strip()
                except Exception:
                    continue
                if len(t) > len(text):
                    text = t

            img_urls: list[str] = []
            try:
                imgs = await page.eval_on_selector_all(
                    "img", "els => els.map(e => e.dataset.src || e.src || '')"
                )
                seen: set[str] = set()
                for u in imgs:
                    u = u.strip()
                    low = u.lower()
                    if (
                        not u
                        or not low.startswith("http")
                        or low.startswith("data:")
                        or any(h in low for h in _DECOR_HINTS)
                        or u in seen
                    ):
                        continue
                    seen.add(u)
                    img_urls.append(u)
            except Exception:
                pass

            html = ""
            try:
                html = await page.content()
            except Exception:
                pass

            # 等待截获任务完成，再落盘（避免浏览器关闭时任务被取消）
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if download_dir and captured:
                download_dir.mkdir(parents=True, exist_ok=True)
                # 按页面 img 出现顺序落盘，保证与正文图片顺序一致
                order = {u: i for i, u in enumerate(img_urls)}
                captured.sort(key=lambda c: order.get(c[0], 9999))
                for i, (u, body) in enumerate(captured[: settings.KB_OCR_MAX_IMAGES]):
                    suffix = Path(u.split("?")[0]).suffix.lower()
                    if suffix not in _IMG_SUFFIX:
                        suffix = ".jpg"
                    p = download_dir / f"img_{i + 1:03d}{suffix}"
                    try:
                        await asyncio.to_thread(p.write_bytes, body)
                        saved.append(p)
                    except Exception:
                        pass
        finally:
            await browser.close()
    return text, html, img_urls[: settings.KB_OCR_MAX_IMAGES], saved


async def fetch_rendered_pdf(
    url: str,
    timeout: float = 45.0,
    save_path: Path | None = None,
) -> Path | None:
    """用 headless chromium 渲染页面并保存为 PDF，返回 PDF 路径。

    用于「渲染后 PDF -> markitdown」的稳定正文提取：PDF 是页面完整渲染快照，
    能拿到 JS 渲染后的全部可见内容，不依赖平台清洗器。生成前仅做轻量通用 DOM
    清理（移除脚本/样式/导航等非正文节点），不做平台级文本清洗。
    未安装 playwright 或浏览器缺失 / PDF 生成失败时返回 None，由调用方降级。
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None

    if save_path is None:
        return None
    save_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception:
            return None
        try:
            ctx = await browser.new_context(
                user_agent=_UA,
                viewport={"width": 1280, "height": 2000},
                locale="zh-CN",
            )
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            except Exception:
                pass  # 超时/重定向失败仍尝试用已有 DOM 生成 PDF
            # 滚动触发懒加载，确保长页正文就绪
            try:
                await page.evaluate(
                    "async () => { const t = document.scrollingElement || document.body;"
                    " for (let i = 0; i < 30; i++) { t.scrollTop += 500;"
                    " await new Promise(r => setTimeout(r, 200)); } t.scrollTop = 0; }"
                )
                await page.wait_for_timeout(1500)
            except Exception:
                pass
            # 轻量通用 DOM 清理（非平台特定）：移除明显的非正文节点
            try:
                await page.evaluate(
                    "() => document.querySelectorAll("
                    "'script,style,noscript,nav,header,footer,aside,iframe,form,svg'"
                    ").forEach(e => e.remove())"
                )
            except Exception:
                pass
            try:
                await page.pdf(path=str(save_path), print_background=True, format="A4")
            except Exception:
                return None
        finally:
            await browser.close()

    if save_path.exists() and save_path.stat().st_size > 0:
        return save_path
    return None
