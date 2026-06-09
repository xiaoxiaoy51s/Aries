"""系统级操作：调出原生文件夹选择对话框。"""
import os
import sys
import threading
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/system", tags=["system"])


class SelectDirectoryResponse(BaseModel):
    path: Optional[str] = None
    cancelled: bool = True
    error: Optional[str] = None


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
