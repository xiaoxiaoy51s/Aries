"""系统级操作：调出原生文件夹选择对话框、打开路径、打开网址。"""
import os
import subprocess
import sys
import webbrowser
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


class OpenUrlRequest(BaseModel):
    url: str


class OpenUrlResponse(BaseModel):
    ok: bool
    url: str
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


@router.post("/open-url", response_model=OpenUrlResponse)
def open_url(body: OpenUrlRequest) -> OpenUrlResponse:
    """在系统默认浏览器中打开网址。"""
    url = (body.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL 不能为空")
    try:
        webbrowser.open(url)
    except Exception as exc:
        return OpenUrlResponse(ok=False, url=url, error=str(exc))
    return OpenUrlResponse(ok=True, url=url)


class HomePathResponse(BaseModel):
    home: str
    pets_dir: str
    work_dir: str


@router.get("/home-path", response_model=HomePathResponse)
def home_path() -> HomePathResponse:
    """返回系统用户主目录及常用子目录的实际路径。"""
    home = str(Path("~").expanduser().resolve())
    sep = "\\" if sys.platform == "win32" else "/"
    return HomePathResponse(
        home=home,
        pets_dir=f"{home}{sep}.Aries{sep}pets",
        work_dir=f"{home}{sep}.Aries{sep}work_dir",
    )


@router.post("/select-directory", response_model=SelectDirectoryResponse)
def select_directory() -> SelectDirectoryResponse:
    """弹出系统原生文件夹选择对话框（Windows / macOS / Linux）。"""
    import platform
    result = {"path": None, "cancelled": True, "error": None}

    # Windows 使用 PowerShell 弹出文件夹选择对话框
    if platform.system() == "Windows":
        try:
            # 使用 PowerShell 的 System.Windows.Forms 来选择文件夹，并置顶显示
            # RootFolder 设置为 "我的电脑"，可以看到所有磁盘
            ps_script = '''
Add-Type -AssemblyName System.Windows.Forms
$form = New-Object System.Windows.Forms.Form
$form.TopMost = $true
$form.WindowState = "Minimized"
$form.Show()
$form.Hide()
$folder = New-Object System.Windows.Forms.FolderBrowserDialog
$folder.Description = "选择文件夹"
$folder.ShowNewFolderButton = $true
$folder.RootFolder = "MyComputer"
$result = $folder.ShowDialog($form)
$form.Close()
if ($result -eq "OK") {
    Write-Output $folder.SelectedPath
}
'''
            proc = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = proc.stdout.strip()
            if output:
                result["path"] = os.path.abspath(output)
                result["cancelled"] = False
            if proc.stderr:
                result["error"] = proc.stderr.strip()
        except subprocess.TimeoutExpired:
            result["error"] = "选择超时"
        except Exception as e:
            result["error"] = str(e)
        return SelectDirectoryResponse(**result)

    # macOS / Linux 使用 zenity 或 tkinter
    try:
        if platform.system() == "Linux":
            # Linux 尝试使用 zenity
            proc = subprocess.run(
                ["zenity", "--file-selection", "--directory", "--title=选择文件夹"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                result["path"] = os.path.abspath(proc.stdout.strip())
                result["cancelled"] = False
            return SelectDirectoryResponse(**result)
    except FileNotFoundError:
        pass
    except Exception as e:
        result["error"] = str(e)

    # 最后尝试 tkinter（macOS 或 Linux 没有 zenity）
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        path = filedialog.askdirectory(
            title="选择文件夹",
            mustexist=True,
        )
        if path:
            result["path"] = os.path.abspath(path)
            result["cancelled"] = False

        root.destroy()
    except Exception as e:
        result["error"] = str(e)

    return SelectDirectoryResponse(**result)
