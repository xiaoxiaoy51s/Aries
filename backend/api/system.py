"""系统级操作：调出原生文件夹选择对话框、打开路径。"""
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/system", tags=["system"])


class SelectDirectoryResponse(BaseModel):
    path: Optional[str] = None
    cancelled: bool = True
    error: Optional[str] = None


class OpenPathRequest(BaseModel):
    path: str


class OpenPathResponse(BaseModel):
    ok: bool
    path: str
    error: Optional[str] = None


def _open_path_in_explorer(target: Path) -> None:
    resolved = target.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"路径不存在: {resolved}")

    open_target = resolved if resolved.is_dir() else resolved.parent
    if sys.platform == "win32":
        os.startfile(str(open_target))  # noqa: S606
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(open_target)])  # noqa: S603
        return
    subprocess.Popen(["xdg-open", str(open_target)])  # noqa: S603


@router.post("/open-path", response_model=OpenPathResponse)
def open_path(body: OpenPathRequest) -> OpenPathResponse:
    """在系统文件管理器中打开文件或目录所在位置。"""
    raw = (body.path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="路径不能为空")
    try:
        _open_path_in_explorer(Path(raw))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        return OpenPathResponse(ok=False, path=raw, error=str(exc))
    return OpenPathResponse(ok=True, path=raw)


@router.post("/select-directory", response_model=SelectDirectoryResponse)
def select_directory() -> SelectDirectoryResponse:
    """弹出系统原生文件夹选择对话框（Windows / macOS / Linux）。

    使用 tkinter 在子线程中调用，避免阻塞 FastAPI 事件循环。
    tkinter 是 Python 标准库，无需额外安装。
    """
    result = {"path": None, "cancelled": True, "error": None}

    def _ask():
        try:
            import tkinter as tk
            from tkinter import filedialog

            # 隐藏主窗口
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            try:
                # Windows 上让对话框置顶
                root.wm_attributes("-topmost", 1)
            except Exception:
                pass

            path = filedialog.askdirectory(
                title="选择工作目录",
                mustexist=True,
            )
            if path:
                result["path"] = os.path.abspath(path)
                result["cancelled"] = False

            root.destroy()
        except Exception as e:
            result["error"] = str(e)
            print(f"[system] select_directory failed: {e}", file=sys.stderr)

    # 必须在子线程跑 tkinter，避免阻塞
    t = threading.Thread(target=_ask, daemon=True)
    t.start()
    t.join(timeout=600)  # 10 分钟超时

    return SelectDirectoryResponse(**result)
