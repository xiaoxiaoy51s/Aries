"""文件浏览器 API: 列出目录、读取文件内容、语法诊断（对齐 VS Code MarkerService）。"""
from __future__ import annotations

import ast
import asyncio
import base64
import json
import mimetypes
import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/files", tags=["files"])

# 图片扩展名（可通过浏览器 <img> 直接预览）
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico"}

# 已知的二进制文件扩展名（非图片，无法在文本编辑器中正常显示）
BINARY_EXTENSIONS = {
    ".class", ".jar", ".war", ".ear", ".exe", ".dll", ".so", ".dylib",
    ".bin", ".dat", ".db", ".sqlite", ".pyc", ".pyo", ".o", ".a",
    ".zip", ".gz", ".tar", ".bz2", ".7z", ".rar", ".xz",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flv", ".mkv",
    ".wasm", ".pak",
}


def _normalize_work_dir(work_dir: str | None) -> str:
    if work_dir and work_dir.strip():
        path = Path(work_dir).expanduser().resolve()
    else:
        path = Path.home() / ".Aries" / "work_dir"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


@router.get("/list")
async def list_files(
    work_dir: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """列出指定路径下的文件和目录。"""
    base = Path(_normalize_work_dir(work_dir))
    target = base
    if path:
        target = base / path
    target = target.resolve()
    # 安全检查: 确保在 base 下
    if not str(target).startswith(str(base)):
        return {"entries": [], "error": "路径越界"}

    if not target.exists():
        return {"entries": [], "error": "路径不存在"}
    if not target.is_dir():
        return {"entries": [], "error": "不是目录"}

    entries: list[dict[str, Any]] = []
    try:
        for item in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            rel = str(item.relative_to(base)).replace("\\", "/")
            entries.append({
                "name": item.name,
                "path": rel,
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else 0,
            })
    except PermissionError:
        return {"entries": [], "error": "权限不足"}

    return {"entries": entries}


@router.get("/read")
async def read_file(
    work_dir: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """读取指定文件的内容。

    - 图片文件：返回 base64 编码 + mime 类型，前端用 <img> 预览
    - 其他二进制文件：返回 is_binary 标记，不返回内容
    - 文本文件：返回 UTF-8 文本内容
    """
    base = Path(_normalize_work_dir(work_dir))
    if not path:
        return {"content": "", "error": "缺少路径参数"}
    target = (base / path).resolve()
    if not str(target).startswith(str(base)):
        return {"content": "", "error": "路径越界"}
    if not target.exists() or not target.is_file():
        return {"content": "", "error": "文件不存在"}

    ext = target.suffix.lower()

    # 图片文件：返回 base64
    if ext in IMAGE_EXTENSIONS:
        try:
            raw = target.read_bytes()
            mime = mimetypes.guess_type(str(target))[0] or "image/png"
            return {
                "is_image": True,
                "content": base64.b64encode(raw).decode("ascii"),
                "mime": mime,
                "size": len(raw),
            }
        except Exception as e:
            return {"content": "", "error": str(e)}

    # 其他二进制文件：不返回内容
    if ext in BINARY_EXTENSIONS:
        try:
            size = target.stat().st_size
            return {
                "is_binary": True,
                "content": "",
                "size": size,
                "file_type": ext,
            }
        except Exception as e:
            return {"content": "", "error": str(e)}

    # 文本文件：读取 UTF-8 内容
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"content": content}
    except Exception as e:
        return {"content": "", "error": str(e)}


class DeleteRequest(BaseModel):
    work_dir: str
    path: str


class RenameRequest(BaseModel):
    work_dir: str
    path: str
    new_name: str


@router.delete("/delete")
async def delete_file(req: DeleteRequest) -> dict[str, Any]:
    """删除文件或目录。"""
    import shutil

    base = Path(_normalize_work_dir(req.work_dir))
    target = (base / req.path).resolve()
    if not str(target).startswith(str(base)):
        return {"error": "路径越界"}
    if not target.exists():
        return {"error": "文件不存在"}
    if target == base:
        return {"error": "不能删除工作目录根"}

    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


class RevertFileRequest(BaseModel):
    file_path: str
    content: str  # 要恢复的内容（previous_content）


@router.post("/revert")
async def revert_file(req: RevertFileRequest) -> dict[str, Any]:
    """将文件内容恢复到指定内容（用于产物区域的回退功能）。"""
    if not req.file_path:
        return {"error": "file_path 不能为空"}
    try:
        target = Path(req.file_path)
        if not target.exists():
            return {"error": f"文件不存在: {target}"}
        target.write_text(req.content, encoding="utf-8")
        return {"ok": True, "file_path": str(target)}
    except Exception as e:
        return {"error": str(e)}


# ─── 语法诊断（对齐 VS Code MarkerService / Monaco setModelMarkers） ───

_DIAGNOSTIC_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".jsonc": "json",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
}

# Monaco MarkerSeverity: Hint=1, Info=2, Warning=4, Error=8
_MONACO_SEVERITY = {
    "error": 8,
    "warning": 4,
    "info": 2,
    "hint": 1,
}


def _lint_pyflakes(content: str) -> list[dict[str, Any]]:
    """使用 pyflakes 进行 Python 语法/逻辑诊断（快，无 import 解析）。"""
    try:
        from pyflakes.api import check
        from pyflakes.reporter import Reporter
    except ImportError:
        return _lint_python_ast(content)

    markers: list[dict[str, Any]] = []

    class CaptureReporter(Reporter):
        def unexpectedError(self, filename, msg):  # type: ignore
            pass
        def syntaxError(self, filename, msg, lineno, offset, text):  # type: ignore
            markers.append({
                "startLineNumber": lineno or 1,
                "startColumn": (offset or 0) + 1,
                "endLineNumber": lineno or 1,
                "endColumn": (offset or 0) + 2,
                "message": f"[语法错误] {msg}",
                "severity": 8,
                "code": "syntax-error",
            })
        def flake(self, message):  # type: ignore
            markers.append({
                "startLineNumber": message.lineno,
                "startColumn": message.col,
                "endLineNumber": message.lineno,
                "endColumn": message.col + 1,
                "message": str(message.message),
                "severity": 4 if "warning" in type(message).__name__.lower() else 2,
                "code": type(message).__name__,
            })

    try:
        check(content, "buffer", CaptureReporter())
    except Exception:
        pass  # fallback to ast
        return _lint_python_ast(content)

    return markers


def _lint_python_ast(content: str) -> list[dict[str, Any]]:
    """使用 Python ast 模块做基础语法检查（零依赖）。"""
    markers: list[dict[str, Any]] = []
    try:
        ast.parse(content)
    except SyntaxError as e:
        lineno = e.lineno or 1
        offset = (e.offset or 0) + 1
        markers.append({
            "startLineNumber": lineno,
            "startColumn": offset,
            "endLineNumber": lineno,
            "endColumn": offset + 1,
            "message": f"[语法错误] {e.msg}",
            "severity": 8,
            "code": "syntax-error",
        })
    return markers


def _lint_javascript(content: str, ext: str) -> list[dict[str, Any]]:
    """使用 Node.js --check 做 JS 语法诊断。"""
    markers: list[dict[str, Any]] = []

    # 对 TypeScript 不做 Node --check（不支持），返回空
    if ext in (".ts", ".tsx"):
        return markers

    node = shutil.which("node")
    if not node:
        return markers

    try:
        proc = subprocess.run(
            [node, "--check", "--stdin"],
            input=content,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            # 解析 Node.js 错误输出格式: "path:line:col: error message"
            for line in stderr.split("\n"):
                line = line.strip()
                # 匹配标准格式: 文件名:行号:列号: 错误信息
                match = re.match(r".+:(\d+):(\d+):\s*(.+)", line)
                if match:
                    lineno = int(match.group(1))
                    col = int(match.group(2))
                    msg = match.group(3).strip()
                    markers.append({
                        "startLineNumber": lineno,
                        "startColumn": col,
                        "endLineNumber": lineno,
                        "endColumn": col + 1,
                        "message": f"[SyntaxError] {msg}",
                        "severity": 8,
                        "code": "js-syntax-error",
                    })
    except Exception:
        pass

    return markers


def _lint_json(content: str) -> list[dict[str, Any]]:
    """使用 Python json 模块做 JSON 语法诊断。"""
    markers: list[dict[str, Any]] = []
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        lineno = e.lineno
        col = e.colno
        markers.append({
            "startLineNumber": lineno,
            "startColumn": col,
            "endLineNumber": lineno,
            "endColumn": col + 1,
            "message": f"[JSON Error] {e.msg}",
            "severity": 8,
            "code": "json-syntax-error",
        })
    return markers


def _run_diagnostics(content: str, ext: str) -> list[dict[str, Any]]:
    """根据文件扩展名选择合适的诊断器。"""
    lang = _DIAGNOSTIC_LANGUAGES.get(ext)

    if lang == "python":
        return _lint_pyflakes(content)
    elif lang == "javascript":
        return _lint_javascript(content, ext)
    elif lang == "json":
        return _lint_json(content)
    # HTML/CSS/YAML/Markdown: 不做深层诊断，返回空
    return []


@router.get("/diagnostics")
async def get_diagnostics(
    work_dir: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """对指定文件运行语法诊断，返回 Monaco 兼容的 marker 数组。

    返回值格式对齐 Monaco Editor 的 IMarkerData：
    ```json
    {
      "markers": [
        {
          "startLineNumber": 1,
          "startColumn": 5,
          "endLineNumber": 1,
          "endColumn": 10,
          "message": "错误描述",
          "severity": 8,
          "code": "error-code"
        }
      ]
    }
    ```
    severity: 1=Hint, 2=Info, 4=Warning, 8=Error
    """
    base = Path(_normalize_work_dir(work_dir))
    if not path:
        return {"markers": []}
    target = (base / path).resolve()
    if not str(target).startswith(str(base)):
        return {"markers": []}
    if not target.exists() or not target.is_file():
        return {"markers": []}

    ext = target.suffix.lower()
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        markers = _run_diagnostics(content, ext)
        return {"markers": markers}
    except Exception:
        return {"markers": []}


class SaveFileRequest(BaseModel):
    work_dir: str
    path: str
    content: str


@router.put("/save")
async def save_file(req: SaveFileRequest) -> dict[str, Any]:
    """保存文件内容。"""
    base = Path(_normalize_work_dir(req.work_dir))
    target = (base / req.path).resolve()
    if not str(target).startswith(str(base)):
        return {"error": "路径越界"}
    if not target.exists() or not target.is_file():
        return {"error": "文件不存在"}
    try:
        target.write_text(req.content, encoding="utf-8")
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


@router.put("/rename")
async def rename_file(req: RenameRequest) -> dict[str, Any]:
    """重命名文件或目录。"""
    base = Path(_normalize_work_dir(req.work_dir))
    target = (base / req.path).resolve()
    if not str(target).startswith(str(base)):
        return {"error": "路径越界"}
    if not target.exists():
        return {"error": "文件不存在"}

    new_name = req.new_name.strip()
    if not new_name or "/" in new_name or "\\" in new_name:
        return {"error": "新文件名无效"}

    new_target = target.parent / new_name
    if new_target == target:
        return {"ok": True, "new_path": req.path}
    if new_target.exists():
        return {"error": "目标名称已存在"}

    try:
        target.rename(new_target)
        rel = str(new_target.relative_to(base)).replace("\\", "/")
        return {"ok": True, "new_path": rel}
    except Exception as e:
        return {"error": str(e)}


class OpenInEditorRequest(BaseModel):
    work_dir: str | None = None
    path: str | None = None
    editor: str = "vscode"  # vscode | vscode-file | explorer | explorer-file


@router.post("/open-in-editor")
async def open_in_editor(req: OpenInEditorRequest) -> dict[str, Any]:
    """用外部编辑器（VSCode）或系统文件管理器打开工作目录/文件。

    editor 取值:
    - vscode      : 在 VSCode 中打开工作目录
    - vscode-file : 在 VSCode 中打开单个文件
    - explorer    : 在资源管理器中打开工作目录
    - explorer-file: 在资源管理器中选中并高亮指定文件/文件夹
    """
    base = Path(_normalize_work_dir(req.work_dir))
    if not base.exists():
        return {"error": "工作目录不存在"}

    target = base
    if req.path:
        target = (base / req.path).resolve()
        if not str(target).startswith(str(base)):
            return {"error": "路径越界"}
        if not target.exists():
            return {"error": "路径不存在"}

    try:
        if req.editor in ("vscode", "vscode-file"):
            code_bin = shutil.which("code") or shutil.which("code.cmd")
            if not code_bin:
                return {"error": "未找到 VSCode（请确保已安装并将 code 命令加入 PATH）"}
            args = [code_bin]
            if req.editor == "vscode-file" and target != base:
                # 打开文件，并在可能时定位到首行
                args.append(f"{target}:1")
            else:
                args.append(str(target))
            subprocess.Popen(
                args,
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            return {"ok": True, "editor": req.editor}
        elif req.editor == "explorer":
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(target)], shell=False)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
            return {"ok": True, "editor": "explorer"}
        elif req.editor == "explorer-file":
            if sys.platform == "win32":
                # /select 参数会在资源管理器中打开并高亮指定项
                subprocess.Popen(["explorer", "/select,", str(target)], shell=False)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(target)])
            else:
                # Linux 下没有统一的高亮方案，退回到打开父目录
                subprocess.Popen(["xdg-open", str(target.parent)])
            return {"ok": True, "editor": "explorer-file"}
        else:
            return {"error": f"不支持的编辑器: {req.editor}"}
    except Exception as e:
        return {"error": str(e)}
