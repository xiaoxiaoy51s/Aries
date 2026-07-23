"""文档文本抽取工具：支持 PDF / Word / Excel / PPTX 文件，抽取纯文本供 AI 通读。

设计目标：无向量化模型时，"暴力阅读全部内容"。
docx / xlsx / pptx → officecli view <file> text（含图片描述、表格数据）
pdf              → pypdf 抽取纯文本（保持兼容）
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# 支持的文档扩展名（小写，含点）
SUPPORTED_DOC_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".xlsm"}


def _find_officecli() -> str | None:
    """从 env.json / PATH 查找 officecli 路径"""
    try:
        from utils.env_config import get_env_runtime
        info = get_env_runtime("officecli")
        if info and info.get("path"):
            exe = Path(info["path"])
            if exe.exists():
                return str(exe)
    except Exception:
        pass
    # fallback: PATH
    for name in ("officecli", "officecli-win-x64"):
        import shutil
        exe = shutil.which(name)
        if exe:
            return exe
    return None


def _officecli_view(path: Path) -> str:
    """使用 officecli view <file> text 抽取纯文本。

    依赖：需先安装 officecli 并写入 env.json（通过环境检测 / DevEnv 设置页）。
    """
    exe = _find_officecli()
    if not exe:
        raise ValueError(
            "未找到 officecli，请在设置页面安装或配置后重试。"
        )

    try:
        proc = subprocess.run(
            [exe, "view", str(path), "text"],
            capture_output=True, text=True, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            raise ValueError(f"officecli 解析失败: {stderr or f'exit code {proc.returncode}'}")

        text = (proc.stdout or "").strip()
        if not text:
            raise ValueError("officecli 未返回任何文本内容（可能为空文档或纯图片）")
        return text
    except subprocess.TimeoutExpired:
        raise ValueError("officecli 解析超时（60 秒）")
    except FileNotFoundError:
        raise ValueError("officecli 可执行文件未找到")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"officecli 执行失败: {exc}")


def is_supported_document(path: Path | str) -> bool:
    """判断文件是否为可解析的文档类型。"""
    ext = Path(path).suffix.lower()
    return ext in SUPPORTED_DOC_EXTENSIONS


def extract_text(path: Path | str) -> str:
    """根据扩展名分发到对应解析器，返回抽取出的纯文本。

    失败时抛出 ValueError（含可读的失败原因），由调用方转成错误响应。
    """
    p = Path(path)
    ext = p.suffix.lower()

    if ext == ".pdf":
        return _extract_pdf(p)
    if ext in (".docx", ".pptx", ".xlsx", ".xlsm"):
        return _officecli_view(p)
    if ext in (".doc", ".xls"):
        raise ValueError(
            f"不支持旧版 .{ext.lstrip('.')} 格式，请先用 LibreOffice 转换为 .{'docx' if ext == '.doc' else 'xlsx'} 后重试"
        )
    raise ValueError(f"不支持的文档类型: {ext}")


def _extract_pdf(path: Path) -> str:
    """使用 pypdf 抽取 PDF 全部文本，按页输出。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("缺少依赖 pypdf，请先安装: pip install pypdf")

    try:
        reader = PdfReader(str(path))
        parts: list[str] = []
        for i, page in enumerate(reader.pages, 1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                text = ""
                logger.warning(f"PDF 第 {i} 页文本抽取失败: {exc}")
            parts.append(f"--- 第 {i} 页 ---")
            parts.append(text)
        result = "\n".join(parts).strip()
        if not result:
            raise ValueError("PDF 未抽取到任何文本（可能是扫描件/纯图片，需要 OCR）")
        return result
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"PDF 解析失败: {exc}")
