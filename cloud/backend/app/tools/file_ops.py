"""文件管理工具：增删改查 + ripgrep 全局搜索。

工具列表：
1. search_file - 用 ripgrep 搜索文件内容 search_file - 用 ripgrep 搜索文件内容
2. read_file - 读取文件内容
3. write_file - 写入/创建文件
4. list_files - 列出目录内容
5. delete_file - 删除文件或目录

所有操作限制在用户工作区内。
ripgrep 自动管理：PATH 有 rg 则用；没有则自动下载到 ~/.Aries/bin/rg。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.tools.sandbox import get_tool_workspace, resolve_sandbox_path, is_under_paths, get_allowed_skill_roots, get_wiki_root


def _get_workspace(context: dict[str, Any] | None) -> tuple[Any, str]:
    workspace, err = get_tool_workspace(context)
    if err or workspace is None:
        return None, err or "无法确定工作目录"
    return workspace, ""


def _resolve_path(
    workspace: Path,
    rel_path: str,
    *,
    user_email: str = "",
    allow_skills: bool = True,
) -> Path | None:
    """解析路径：工作区相对路径，或 skills 下的绝对/~路径。"""
    resolved, err = resolve_sandbox_path(
        workspace,
        rel_path,
        user_email=user_email,
        allow_skills=allow_skills,
    )
    if err or resolved is None:
        return None
    return resolved


def _is_skill_path(path: Path, user_email: str) -> bool:
    return is_under_paths(path, get_allowed_skill_roots(user_email))


def _is_wiki_path(path: Path, user_email: str) -> bool:
    return is_under_paths(path, [get_wiki_root(user_email)])

_cached_rg: str | None = None

# ripgrep 版本和下载地址
_RG_VERSION = "14.1.1"
_RG_DOWNLOADS = {
    "linux": f"https://github.com/BurntSushi/ripgrep/releases/download/{_RG_VERSION}/ripgrep-{_RG_VERSION}-x86_64-unknown-linux-musl.tar.gz",
    "win32": f"https://github.com/BurntSushi/ripgrep/releases/download/{_RG_VERSION}/ripgrep-{_RG_VERSION}-x86_64-pc-windows-msvc.zip",
    "darwin": f"https://github.com/BurntSushi/ripgrep/releases/download/{_RG_VERSION}/ripgrep-{_RG_VERSION}-x86_64-apple-darwin.tar.gz",
}


def _get_bin_dir() -> Path:
    """获取本地 bin 目录：~/.Aries/bin/"""
    bin_dir = Path.home() / ".Aries" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    return bin_dir


def _download_rg() -> str:
    """下载 ripgrep 二进制到 ~/.Aries/bin/，返回路径。"""
    import platform
    import zipfile

    platform_key = sys.platform
    url = _RG_DOWNLOADS.get(platform_key)
    if not url:
        # arm64 Linux
        if platform_key == "linux" and platform.machine() == "aarch64":
            url = f"https://github.com/BurntSushi/ripgrep/releases/download/{_RG_VERSION}/ripgrep-{_RG_VERSION}-aarch64-unknown-linux-gnu.tar.gz"
        else:
            return ""

    bin_dir = _get_bin_dir()
    rg_name = "rg.exe" if platform_key == "win32" else "rg"
    rg_path = bin_dir / rg_name

    if rg_path.exists():
        return str(rg_path)

    try:
        # 下载
        tmp_file = bin_dir / f"rg_download.{platform_key}"
        urllib.request.urlretrieve(url, str(tmp_file))

        # 解压
        if platform_key == "win32":
            with zipfile.ZipFile(str(tmp_file), "r") as zf:
                for member in zf.namelist():
                    if member.endswith("rg.exe"):
                        with zf.open(member) as src, open(str(rg_path), "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        break
        else:
            with tarfile.open(str(tmp_file), "r:gz") as tf:
                for member in tf.getmembers():
                    if member.name.endswith("/rg") and member.isfile():
                        member.name = os.path.basename(member.name)
                        tf.extract(member, str(bin_dir))
                        break

        tmp_file.unlink(missing_ok=True)

        # 设置可执行权限
        if platform_key != "win32":
            rg_path.chmod(0o755)

        if rg_path.exists():
            return str(rg_path)
    except Exception:
        pass

    return ""


def find_rg() -> str:
    """查找 ripgrep。优先 PATH，其次 ~/.Aries/bin/rg，最后自动下载。"""
    global _cached_rg
    if _cached_rg is not None:
        return _cached_rg

    # 1. PATH 中查找
    rg = shutil.which("rg")
    if rg:
        _cached_rg = rg
        return rg

    # 2. 本地 bin 目录
    bin_dir = _get_bin_dir()
    rg_name = "rg.exe" if sys.platform == "win32" else "rg"
    local_rg = bin_dir / rg_name
    if local_rg.exists():
        _cached_rg = str(local_rg)
        return _cached_rg

    # 3. Windows 上查找仓库自带的 rg.exe
    if sys.platform == "win32":
        current = Path(__file__).resolve()
        for parent in [current.parent] + list(current.parents):
            candidate = parent / "bin" / "rg.exe"
            if candidate.exists():
                _cached_rg = str(candidate)
                return _cached_rg
            candidate2 = parent / "backend" / "bin" / "rg.exe"
            if candidate2.exists():
                _cached_rg = str(candidate2)
                return _cached_rg

    # 4. 自动下载
    downloaded = _download_rg()
    _cached_rg = downloaded
    return _cached_rg


def find_officecli() -> str:
    """查找 officecli。优先 PATH，找不到返回空字符串。"""
    return shutil.which("officecli") or ""


# Office 文档扩展名 -> 走 officecli 提取文本
_OFFICE_EXTS = {".docx", ".xlsx", ".pptx"}
# 图片扩展名 -> 返回标记，由 chat_service 转成 multimodal image_url
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_IMAGE_MIMES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}


async def _read_office_file(file_path: Path, display_path: str) -> str:
    """用 officecli 提取 Office 文档（docx/xlsx/pptx）的文本内容。"""
    cli = find_officecli()
    if not cli:
        return "错误：读取 Office 文档需要 officecli，但服务器未安装。请让管理员安装 officecli。"
    try:
        import asyncio
        result = await asyncio.to_thread(
            subprocess.run,
            [cli, "view", str(file_path), "text"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        return f"读取失败（officecli）：{e}"
    output = result.stdout.strip()
    if not output:
        return f"(空文档或无文本内容: {display_path})"
    max_out = settings.SHELL_MAX_OUTPUT
    if len(output) > max_out:
        output = output[:max_out] + "\n...(输出已截断)"
    return output


# ============ 工具 Schema ============

TOOL_SCHEMA_SEARCH = {
    "type": "function",
    "function": {
        "name": "search_file",
        "description": (
            "在工作区内搜索文件内容（底层使用 ripgrep 高性能引擎）。"
            "支持正则表达式搜索，返回匹配的文件路径、行号和上下文内容。"
            "适用于查找函数定义、变量使用、特定代码模式等。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "搜索关键词或正则表达式。",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "搜索范围路径。支持三种形式：\n"
                        "1. 相对路径（如 src/、./）：相对于当前工作目录。\n"
                        "2. wiki/ 前缀（如 wiki/编程/Python/）：搜索知识库指定目录。\n"
                        "3. 绝对路径：仅限工作目录或知识库目录内的路径。\n"
                        "留空则搜索整个工作目录（不含知识库）。"
                    ),
                    "default": "",
                },
                "glob": {
                    "type": "string",
                    "description": "文件过滤模式，如 *.py, *.js, **/*.ts。默认 *（所有文件）。",
                    "default": "*",
                },
                "output_mode": {
                    "type": "string",
                    "description": "输出模式：content（显示匹配行及上下文，默认）、files（仅返回匹配的文件路径列表）、count（仅返回匹配数量统计）。",
                    "enum": ["content", "files", "count"],
                    "default": "content",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "返回匹配行前后各多少行作为上下文。仅 output_mode=content 时生效。默认 2。",
                    "default": 2,
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "是否区分大小写。默认 false。",
                    "default": False,
                },
                "max_results": {
                    "type": "integer",
                    "description": "最多返回多少处匹配。默认 50。",
                    "default": 50,
                },
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
    },
}

TOOL_SCHEMA_READ = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "读取工作区内文件的内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "文件路径。支持三种形式：\n"
                        "1. 相对路径（如 src/main.py）：相对于当前工作目录。\n"
                        "2. wiki/ 前缀（如 wiki/编程/Python/笔记.md）：读取知识库文件。\n"
                        "3. 绝对路径：仅限工作目录或知识库目录内的路径。"
                    ),
                },
                "start_line": {
                    "type": "integer",
                    "description": "起始行号（从 1 开始），默认 1",
                    "default": 1,
                },
                "end_line": {
                    "type": "integer",
                    "description": "结束行号，默认读到文件末尾",
                    "default": 0,
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
}

TOOL_SCHEMA_WRITE = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "写入或创建文件。如果文件已存在则覆盖，不存在则创建（含父目录）。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "文件路径。支持三种形式：\n"
                        "1. 相对路径（如 src/main.py）：相对于当前工作目录。\n"
                        "2. wiki/ 前缀（如 wiki/编程/Python/笔记.md）：写入知识库文件。\n"
                        "3. 绝对路径：仅限工作目录或知识库目录内的路径。"
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "文件内容",
                },
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
}

TOOL_SCHEMA_LIST = {
    "type": "function",
    "function": {
        "name": "list_files",
        "description": "列出工作区内指定目录的文件和子目录。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "目录路径。支持三种形式：\n"
                        "1. 相对路径（如 src/）：相对于当前工作目录，留空为工作目录根。\n"
                        "2. wiki/ 前缀（如 wiki/编程/）：列出知识库目录。\n"
                        "3. 绝对路径：仅限工作目录或知识库目录内的路径。"
                    ),
                    "default": "",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "是否递归列出所有子目录",
                    "default": False,
                },
            },
            "additionalProperties": False,
        },
    },
}

TOOL_SCHEMA_DELETE = {
    "type": "function",
    "function": {
        "name": "delete_file",
        "description": "删除工作区内的文件或目录。目录会被递归删除。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "要删除的文件或目录路径。支持三种形式：\n"
                        "1. 相对路径（如 src/old.py）：相对于当前工作目录。\n"
                        "2. wiki/ 前缀（如 wiki/编程/旧笔记.md）：删除知识库文件。\n"
                        "3. 绝对路径：仅限工作目录或知识库目录内的路径。"
                    ),
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
}


# ============ 辅助函数 ============

# _resolve_path / _is_skill_path 定义见文件顶部

async def search_file(
    pattern: str,
    path: str = "",
    glob: str = "*",
    output_mode: str = "content",
    context_lines: int = 2,
    case_sensitive: bool = False,
    max_results: int = 50,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    """用 ripgrep 搜索文件内容。"""
    user_email = (context or {}).get("user_email", "")
    if not user_email:
        return "错误：无法确定用户工作区"

    workspace, ws_err = _get_workspace(context)
    if ws_err:
        return f"错误：{ws_err}"

    rg = find_rg()
    if not rg:
        return "错误：未找到 ripgrep (rg)。Linux 请运行 apt install ripgrep，Windows 请确保 rg.exe 在 PATH 中。"

    # workspace 已在上方解析

    # 解析搜索路径
    if path:
        search_dir = _resolve_path(workspace, path, user_email=user_email)
        if not search_dir:
            return "错误：路径无效或超出工作区/技能目录范围"
        if not search_dir.exists():
            return f"错误：目录不存在 {path}"
    else:
        search_dir = workspace

    # 构建 rg 命令
    cmd = [rg]
    if not case_sensitive:
        cmd.append("-i")
    cmd.append("--no-heading")
    cmd.append("--line-number")
    cmd.append("--color=never")

    if output_mode == "files":
        cmd.append("--files-with-matches")
    elif output_mode == "count":
        cmd.append("--count")

    if output_mode == "content" and context_lines > 0:
        cmd.extend(["-C", str(context_lines)])

    cmd.extend(["-m", str(max_results)])
    cmd.extend(["-g", glob])
    cmd.append(pattern)
    cmd.append(str(search_dir))

    try:
        import asyncio
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=30
        )
    except Exception as e:
        return f"搜索失败：{e}"

    output = result.stdout.strip()
    if not output:
        return f'未找到匹配 "{pattern}" 的内容'

    # 截断输出
    max_out = settings.SHELL_MAX_OUTPUT
    if len(output) > max_out:
        output = output[:max_out] + f"\n...(输出已截断，共 {len(output)} 字符)"

    # rg 返回码 0=有匹配, 1=无匹配, 2=错误
    return output if output else f'未找到匹配 "{pattern}" 的内容'


async def read_file(
    path: str,
    start_line: int = 1,
    end_line: int = 0,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    """读取文件内容。"""
    user_email = (context or {}).get("user_email", "")
    if not user_email:
        return "错误：无法确定用户工作区"

    workspace, ws_err = _get_workspace(context)
    if ws_err:
        return f"错误：{ws_err}"

    file_path = _resolve_path(workspace, path, user_email=user_email)
    if not file_path:
        return "错误：路径无效或超出工作区/技能目录范围"
    if not file_path.exists():
        return f"错误：文件不存在 {path}"
    if not file_path.is_file():
        return f"错误：不是文件 {path}"

    suffix = file_path.suffix.lower()

    # Office 文档：走 officecli 提取文本
    if suffix in _OFFICE_EXTS:
        return await _read_office_file(file_path, path)

    # 图片：返回 JSON 标记，由 chat_service 转成 multimodal image_url
    if suffix in _IMAGE_EXTS:
        import json
        return json.dumps({
            "__image_ref__": True,
            "path": str(file_path),
            "mime": _IMAGE_MIMES[suffix],
            "display": path,
        }, ensure_ascii=False)

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"读取失败：{e}"

    lines = content.split("\n")
    start = max(1, start_line) - 1
    end = len(lines) if end_line <= 0 else min(end_line, len(lines))

    selected = lines[start:end]
    # 加行号
    numbered = []
    for i, line in enumerate(selected, start=start + 1):
        numbered.append(f"{i:>4} | {line}")

    result = "\n".join(numbered)
    max_out = settings.SHELL_MAX_OUTPUT
    if len(result) > max_out:
        result = result[:max_out] + f"\n...(输出已截断)"
    return result if result else "(空文件)"


async def write_file(
    path: str,
    content: str,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    """写入文件。"""
    user_email = (context or {}).get("user_email", "")
    if not user_email:
        return "错误：无法确定用户工作区"

    workspace, ws_err = _get_workspace(context)
    if ws_err:
        return f"错误：{ws_err}"

    file_path = _resolve_path(workspace, path, user_email=user_email, allow_skills=False)
    if not file_path:
        return "错误：路径无效或超出工作区范围"
    if len(content.encode("utf-8")) > settings.SHELL_MAX_FILE_SIZE:
        return f"错误：文件内容过大（{len(content)} 字节，上限 {settings.SHELL_MAX_FILE_SIZE} 字节）"

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    except Exception as e:
        return f"写入失败：{e}"

    return f"已写入 {path}（{len(content)} 字节，{content.count(chr(10)) + 1} 行）"


async def list_files(
    path: str = "",
    recursive: bool = False,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    """列出目录内容。"""
    user_email = (context or {}).get("user_email", "")
    if not user_email:
        return "错误：无法确定用户工作区"

    workspace, ws_err = _get_workspace(context)
    if ws_err:
        return f"错误：{ws_err}"

    target = _resolve_path(workspace, path or ".", user_email=user_email)
    if not target:
        return "错误：路径无效或超出工作区/技能目录范围"
    if not target.exists():
        return f"错误：目录不存在 {path}"
    if not target.is_dir():
        return f"错误：不是目录 {path}"

    base = target if (_is_skill_path(target, user_email) or _is_wiki_path(target, user_email)) else workspace
    lines = []
    if recursive:
        for root, dirs, files in os.walk(target):
            rel_root = os.path.relpath(root, base)
            if rel_root == ".":
                rel_root = ""
            for d in sorted(dirs):
                p = os.path.join(rel_root, d) if rel_root else d
                lines.append(f"  [DIR]  {p}/")
            for f in sorted(files):
                p = os.path.join(rel_root, f) if rel_root else f
                size = os.path.getsize(os.path.join(root, f))
                lines.append(f"  [FILE] {p} ({size} bytes)")
    else:
        for item in sorted(target.iterdir()):
            rel = os.path.relpath(item, base)
            if item.is_dir():
                lines.append(f"  [DIR]  {rel}/")
            else:
                size = item.stat().st_size
                lines.append(f"  [FILE] {rel} ({size} bytes)")

    return "\n".join(lines) if lines else "(空目录)"


async def delete_file(
    path: str,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    """删除文件或目录。"""
    user_email = (context or {}).get("user_email", "")
    if not user_email:
        return "错误：无法确定用户工作区"

    workspace, ws_err = _get_workspace(context)
    if ws_err:
        return f"错误：{ws_err}"

    target = _resolve_path(workspace, path, user_email=user_email, allow_skills=False)
    if not target:
        return "错误：路径无效或超出工作区范围（禁止删除技能目录）"
    if not target.exists():
        return f"错误：路径不存在 {path}"
    # 不允许删除工作区根目录或知识库根目录
    if target == workspace:
        return "错误：不允许删除工作区根目录"
    if _is_wiki_path(target, user_email) and target == get_wiki_root(user_email):
        return "错误：不允许删除知识库根目录"

    try:
        if target.is_dir():
            shutil.rmtree(target)
            return f"已删除目录 {path}"
        else:
            target.unlink()
            return f"已删除文件 {path}"
    except Exception as e:
        return f"删除失败：{e}"
