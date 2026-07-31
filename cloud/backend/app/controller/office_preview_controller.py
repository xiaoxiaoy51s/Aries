"""Office 文档预览 API：通过 officecli watch 子进程提供高保真文档预览。

流程：
1. 前端传入文件路径
2. 后端查找 officecli 可执行文件
3. 启动 officecli watch <file> --port <port> 子进程
4. 返回 HTTP 预览 URL，前端用 iframe 嵌入
5. 组件卸载时调用 stop 停止子进程
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import shutil
import signal
import socket
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.interceptor.auth_interceptor import get_current_user
from app.model.user import User
from app.tools.sandbox import (
    get_workspaces_root,
    resolve_workspace_path,
    validate_workspace_name,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/office", tags=["office"])
_OFFICE_CLI_DEFAULT_PORT = 26315

# 活动预览进程缓存 {file_path: {proc, port}}
_active_previews: dict[str, dict] = {}


def _find_officecli() -> str:
    """查找 officecli 可执行文件路径"""
    exe = shutil.which("officecli") or shutil.which("officecli-win-x64")
    if exe:
        return exe
    raise HTTPException(status_code=404, detail="OFFICECLI_NOT_FOUND")


def _find_free_port() -> int:
    """找一个可用端口"""
    for port in range(_OFFICE_CLI_DEFAULT_PORT, _OFFICE_CLI_DEFAULT_PORT + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return _OFFICE_CLI_DEFAULT_PORT


class StartPreviewRequest(BaseModel):
    workspace: str
    path: str


class StopPreviewRequest(BaseModel):
    workspace: str
    path: str


@router.post("/preview/start")
async def start_preview(
    req: StartPreviewRequest,
    user: User = Depends(get_current_user),
):
    """启动 officecli watch 子进程，返回预览 URL"""
    exe = _find_officecli()

    # 解析完整文件路径
    workspace_root = get_workspaces_root(user.email)
    workspace = workspace_root / validate_workspace_name(req.workspace)
    target, err = resolve_workspace_path(workspace, req.path)
    if err or target is None:
        raise HTTPException(status_code=400, detail=err or "路径无效")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {req.path}")
    if not target.is_file():
        raise HTTPException(status_code=400, detail=f"不是文件: {req.path}")

    ext = target.suffix.lower()
    if ext not in (".docx", ".xlsx", ".pptx"):
        raise HTTPException(status_code=400, detail=f"不支持的文档类型: {ext}")

    cache_key = str(target)

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
        _active_previews.pop(cache_key, None)

    port = _find_free_port()

    try:
        proc = await asyncio.create_subprocess_exec(
            exe, "watch", str(target), "--port", str(port),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="OFFICECLI_NOT_FOUND")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动 officecli 失败: {e}")

    # 等待服务就绪（轮询端口）
    for _ in range(30):
        await asyncio.sleep(0.5)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
    else:
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

    logger.info(f"[office-preview] started for {target.name} on port {port}")
    return {"url": f"http://127.0.0.1:{port}/", "port": port, "cached": False}


@router.post("/preview/stop")
async def stop_preview(
    req: StopPreviewRequest,
    user: User = Depends(get_current_user),
):
    """停止 officecli watch 子进程"""
    workspace_root = get_workspaces_root(user.email)
    workspace = workspace_root / validate_workspace_name(req.workspace)
    target, err = resolve_workspace_path(workspace, req.path)
    if err or target is None:
        return {"stopped": False, "reason": "invalid_path"}

    cache_key = str(target.resolve())

    entry = _active_previews.pop(cache_key, None)
    if not entry:
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

    logger.info(f"[office-preview] stopped for {target.name}")
    return {"stopped": True}


@router.get("/raw")
async def serve_raw_file(
    workspace: str,
    path: str,
    user: User = Depends(get_current_user),
) -> FileResponse:
    """原始文件服务：返回文件字节流（用于 PDF iframe 嵌入）。"""
    workspace_root = get_workspaces_root(user.email)
    ws = workspace_root / validate_workspace_name(workspace)
    target, err = resolve_workspace_path(ws, path)
    if err or target is None:
        raise HTTPException(status_code=400, detail=err or "路径无效")
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
