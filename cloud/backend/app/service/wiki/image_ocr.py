"""图片/PDF 内嵌图片的文字识别（视觉大模型，OpenAI 兼容接口 + base64）。

知识库链接提取流程调用：
- 微信文章：playwright 渲染页面 -> PDF -> 按页提取文本 + 识别 PDF 内嵌图片文字（穿插）
- 其他平台（小红书等）：cleaner 提取结构化 meta，图片 URL 下载后用本模块 OCR 识别

配置与 image-ocr skill 共用 ~/.Aries/ocr_config.json：
    {"api_key": "...", "base_url": "...", "model": "qwen-vl-ocr", "timeout": 120}
未配置 / 未安装 PyMuPDF / 识别失败时静默返回空，不影响主流程。
"""
from __future__ import annotations

import asyncio
import base64
import json
import tempfile
from pathlib import Path

from app.config.settings import settings

_HOME = Path.home()
DEFAULT_CONFIG = _HOME / ".Aries" / "ocr_config.json"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
}

_IMG_SUFFIX = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

_PROMPT = "请仅输出图像中的文本内容。"


def load_config(config_path: str | Path | None = None) -> dict:
    """读取旧版配置文件（~/.Aries/ocr_config.json）；缺失或解析失败返回空 dict。"""
    p = Path(config_path) if config_path else DEFAULT_CONFIG
    if not p.exists():
        return {}
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


async def get_ocr_cfg(user_email: str = "") -> dict:
    """获取 OCR 模型配置（不写死在代码里）。

    优先读模型管理中 type=ocr 的激活模型（apiKey/baseUrl/model），
    未配置时回退旧版 ~/.Aries/ocr_config.json 以兼容历史配置。
    """
    if user_email:
        try:
            from app.service.model_config_service import ModelConfigService

            model = await ModelConfigService.get_active_model(user_email, model_type="ocr")
            if model:
                return {
                    "api_key": model.apiKey,
                    "base_url": model.baseUrl,
                    "model": model.model,
                    "timeout": 120,
                }
        except Exception:
            pass
    return load_config()


def _extract_pages(pdf_path: Path, out_dir: Path) -> list[dict]:
    """PyMuPDF 按页提取文本与内嵌图片，返回 [{page, text, images: [Path]}]。

    图片按页面顺序排列（过滤过小的图标/装饰图），文本为每页可见文字。
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return []
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        out_dir = pdf_path.parent
    pages: list[dict] = []
    try:
        doc = fitz.open(pdf_path)
        for pno in range(len(doc)):
            page = doc[pno]
            text = page.get_text("text").strip()
            imgs: list[Path] = []
            for info in page.get_images(full=True):
                xref = info[0]
                base = doc.extract_image(xref)
                w = base.get("width", 0) or 0
                h = base.get("height", 0) or 0
                if w < 32 or h < 32:
                    continue
                ext = base.get("ext", "png") or "png"
                out = out_dir / f"p{pno + 1}_img{xref}.{ext}"
                out.write_bytes(base["image"])
                imgs.append(out)
            pages.append({"page": pno + 1, "text": text, "images": imgs})
        doc.close()
    except Exception:
        return []
    return pages


def ocr_image(path: Path, cfg: dict) -> str:
    """视觉模型识别单张图片（OpenAI 兼容接口 + base64），失败返回空。"""
    import httpx

    api_key = (cfg.get("api_key") or "").strip()
    base_url = (cfg.get("base_url") or "").rstrip("/")
    model = (cfg.get("model") or "").strip()
    if not api_key or not model:
        return ""
    endpoint = base_url + "/chat/completions"
    mime = _MIME.get(path.suffix.lower(), "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": _PROMPT},
                ],
            }
        ],
    }
    resp = httpx.post(
        endpoint,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=cfg.get("timeout", 120),
        trust_env=False,  # 忽略环境变量代理（本地代理失效时直连）
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


async def pdf_content_text(
    pdf_path: Path, max_images: int | None = None, user_email: str = ""
) -> str:
    """按页提取 PDF 文本，并把每页内嵌图片的 OCR 文字穿插在对应页面之后。

    返回整体文本，顺序与 PDF 页面一致（图片与正文交叉）。OCR 模型未配置时
    仅返回各页文本（跳过 OCR），仍可用；未安装 PyMuPDF 或提取失败返回空。
    """
    cfg = await get_ocr_cfg(user_email)
    limit = max_images or settings.KB_OCR_MAX_IMAGES
    has_vision = bool(cfg.get("api_key") and cfg.get("model"))

    def _run() -> str:
        out_dir = pdf_path.parent / f"{pdf_path.stem}_imgs"
        pages = _extract_pages(pdf_path, out_dir)
        if not pages:
            return ""
        parts: list[str] = []
        img_count = 0
        for pg in pages:
            seg: list[str] = []
            if pg["text"]:
                seg.append(pg["text"])
            for img in pg["images"]:
                if img_count >= limit:
                    break
                img_count += 1
                text = ""
                if has_vision:
                    try:
                        text = ocr_image(img, cfg)
                    except Exception:
                        continue
                if text and text.strip():
                    seg.append(f"[图片]\n{text.strip()}")
            if seg:
                parts.append("\n\n".join(seg))
        return "\n\n".join(parts)

    return await asyncio.to_thread(_run)


async def ocr_urls_text(urls: list[str], max_images: int | None = None, user_email: str = "") -> str:
    """下载外部图片 URL 并识别文字，返回拼接文本（每张图一段）。

    用于非微信平台（小红书等）：cleaner 提取的正文图片 URL 列表，逐张下载
    （trust_env=False 绕过失效代理）后交给视觉模型识别。OCR 模型未配置时返回空。
    """
    cfg = await get_ocr_cfg(user_email)
    if not (cfg.get("api_key") and cfg.get("model")):
        return ""
    limit = max_images or settings.KB_OCR_MAX_IMAGES

    def _run() -> str:
        import httpx

        parts: list[str] = []
        with tempfile.TemporaryDirectory(prefix="kb_ocr_urls_") as td:
            for i, u in enumerate(urls[:limit]):
                try:
                    resp = httpx.get(
                        u,
                        timeout=25.0,
                        follow_redirects=True,
                        trust_env=False,
                        headers={"User-Agent": _UA},
                    )
                    if resp.status_code != 200 or len(resp.content) < 1024:
                        continue
                    suffix = Path(u.split("?")[0]).suffix.lower()
                    if suffix not in _IMG_SUFFIX:
                        suffix = ".jpg"
                    p = Path(td) / f"img_{i + 1:03d}{suffix}"
                    p.write_bytes(resp.content)
                    text = ocr_image(p, cfg)
                    if text and text.strip():
                        parts.append(f"[图片 {i + 1}]\n{text.strip()}")
                except Exception:
                    continue
        return "\n\n".join(parts)

    return await asyncio.to_thread(_run)
