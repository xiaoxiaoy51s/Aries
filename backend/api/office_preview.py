"""Office 文档预览 API：通过 officecli watch 子进程提供高保真文档预览。

流程：
1. 前端传入文件路径
2. 后端用 env_config 找到已安装的 officecli
3. 启动 officecli watch <file> --port <port> 子进程
4. 返回 HTTP 预览 URL，前端用 iframe 嵌入
5. 组件卸载时调用 stop 停止子进程
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import signal
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from utils.env_config import get_env_runtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/office", tags=["office"])
_OFFICE_CLI_DEFAULT_PORT = 26315

# 活动预览进程缓存 {file_path: {proc, port, cancel}}
_active_previews: dict[str, dict] = {}


async def _find_officecli() -> str:
    """从 env.json / PATH 查找 officecli 可执行文件路径"""
    env_info = get_env_runtime("officecli")
    if env_info and env_info.get("path"):
        exe = Path(env_info["path"])
        if exe.exists():
            return str(exe)
    # fallback: shutil.which
    import shutil
    exe = shutil.which("officecli") or shutil.which("officecli-win-x64")
    if exe:
        return exe
    raise HTTPException(status_code=404, detail="OFFICECLI_NOT_FOUND")


def _find_free_port() -> int:
    """找一个可用端口（简短重试）"""
    import socket
    for port in range(_OFFICE_CLI_DEFAULT_PORT, _OFFICE_CLI_DEFAULT_PORT + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return _OFFICE_CLI_DEFAULT_PORT


class StartPreviewRequest(BaseModel):
    file_path: str
    workspace: str | None = None


class StopPreviewRequest(BaseModel):
    file_path: str


@router.post("/preview/start")
async def start_preview(req: StartPreviewRequest) -> dict:
    """启动 officecli watch 子进程，返回预览 URL"""
    exe = await _find_officecli()

    # 解析完整文件路径
    file_path = Path(req.file_path)
    if not file_path.is_absolute():
        if req.workspace:
            file_path = Path(req.workspace) / req.file_path
    file_path = file_path.resolve()

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")

    ext = file_path.suffix.lower()
    if ext not in (".docx", ".xlsx", ".pptx"):
        raise HTTPException(status_code=400, detail=f"不支持的文档类型: {ext}")

    cache_key = str(file_path)

    # 已有预览进程则直接返回
    existing = _active_previews.get(cache_key)
    if existing:
        proc = existing.get("proc")
        if proc and proc.returncode is None:
            return {
                "url": f"http://127.0.0.1:{existing['port']}/",
                "port": existing["port"],
                "cached": True,
            }
        # 进程已退出，清理后重新启动
        _active_previews.pop(cache_key, None)

    port = _find_free_port()

    try:
        proc = await asyncio.create_subprocess_exec(
            exe, "watch", str(file_path), "--port", str(port),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="OFFICECLI_NOT_FOUND")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动 officecli 失败: {e}")

    # 等待服务就绪（轮询端口）
    import socket
    for _ in range(30):  # 最多等 15 秒
        await asyncio.sleep(0.5)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
    else:
        # 超时未就绪，杀掉进程
        try:
            proc.kill()
        except Exception:
            pass
        stderr = ""
        try:
            stderr = (await proc.communicate(timeout=3))[1].decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"OFFICECLI_PORT_TIMEOUT: {stderr}")

    _active_previews[cache_key] = {"proc": proc, "port": port}

    logger.info(f"[office-preview] started for {file_path.name} on port {port}")
    return {"url": f"http://127.0.0.1:{port}/", "port": port, "cached": False}


@router.post("/preview/stop")
async def stop_preview(req: StopPreviewRequest) -> dict:
    """停止 officecli watch 子进程"""
    file_path = Path(req.file_path)
    cache_key = str(file_path.resolve()) if file_path.is_absolute() else str(file_path)

    entry = _active_previews.pop(cache_key, None)
    if not entry:
        # 尝试通过 unwatch 命令停止
        exe = await _find_officecli()
        try:
            proc = await asyncio.create_subprocess_exec(
                exe, "unwatch", str(file_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            await asyncio.wait_for(proc.wait(), timeout=5)
        except Exception:
            pass
        return {"stopped": False, "reason": "no_active_process"}

    proc = entry.get("proc")
    if proc and proc.returncode is None:
        try:
            if os.name == "nt":
                proc.terminate()
            else:
                proc.send_signal(signal.SIGTERM)
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
        except Exception:
            pass

    logger.info(f"[office-preview] stopped for {Path(cache_key).name}")
    return {"stopped": True}


# ---- 原始文件服务（PDF / 非 officecli 文件） ----

def _normalize_work_dir(work_dir: str | None) -> str:
    """统一 work_dir 格式，去除尾部斜杠"""
    if not work_dir:
        return ""
    return work_dir.replace("\\", "/").rstrip("/")


@router.get("/raw")
async def serve_raw_file(
    work_dir: str | None = None,
    path: str | None = None,
) -> FileResponse:
    """原始文件服务：返回文件字节流（用于 PDF iframe 嵌入）。

    Usage: <iframe src="/api/office/raw?work_dir=...&path=..."></iframe>
    """
    if not path:
        raise HTTPException(status_code=400, detail="缺少 path 参数")

    base = Path(_normalize_work_dir(work_dir)) if work_dir else Path.cwd()
    target = (base / path).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise HTTPException(status_code=403, detail="路径越界")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    mime_type, _ = mimetypes.guess_type(str(target))
    if not mime_type:
        mime_type = "application/octet-stream"

    return FileResponse(
        path=str(target),
        media_type=mime_type,
        content_disposition_type="inline",
    )
