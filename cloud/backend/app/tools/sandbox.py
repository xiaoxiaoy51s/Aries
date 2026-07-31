"""Shell 命令沙箱：按用户工作目录隔离 + 危险命令拦截。

目录结构：
  ~/.Aries/{email}/workspaces/{name}/   会话工作目录（AI shell / 读写文件）
  ~/.Aries/{email}/upload/              用户通用上传目录
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from app.config.settings import settings


# ============ 危险命令黑名单 ============

_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r'rm\s+-[^\s]*r[^\s]*f[^\s]*\s+/(?:\s|$|[*])', "删除根目录"),
    (r'rm\s+-[^\s]*f[^\s]*r[^\s]*\s+/(?:\s|$|[*])', "删除根目录"),
    (r'rm\s+-rf\s+~(?:\s|$)', "删除家目录"),
    (r'rm\s+-rf\s+\*', "通配删除"),
    (r'rm\s+-rf\s+\.(?:\s|$)', "删除当前目录"),
    (r'\bdd\b.*\bof\s*=\s*/dev/', "写入磁盘设备"),
    (r'\bmkfs\b', "格式化文件系统"),
    (r'\bfdisk\b', "磁盘分区操作"),
    (r'\bparted\b', "磁盘分区操作"),
    (r':\s*\(\)\s*\{.*:.*\|.*:.*&.*\}', "Fork 炸弹"),
    (r'\bvisudo\b', "修改 sudoers"),
    (r'\bsystemctl\b', "系统服务管理"),
    (r'\bservice\b.*\b(start|stop|restart|enable|disable)\b', "系统服务管理"),
    (r'\bshutdown\b', "关机"),
    (r'\breboot\b', "重启"),
    (r'\binit\s+\d', "切换运行级别"),
    (r'curl\s+.*\|\s*(sh|bash|zsh)\b', "管道执行远程脚本"),
    (r'wget\s+.*\|\s*(sh|bash|zsh)\b', "管道执行远程脚本"),
    (r'>\s*/dev/[sh]d', "写入磁盘设备"),
    (r'\bapt(?:-get)?\s+(install|remove|purge|upgrade)\b', "系统包管理"),
    (r'\byum\s+(install|remove)\b', "系统包管理"),
    (r'\bdnf\s+(install|remove)\b', "系统包管理"),
    (r'\bchmod\s+777\s+/(?:\s|$)', "根目录开放权限"),
    (r'\bchown\s+.*\s+/(?:etc|var|root|home|usr)(?:\s|$)', "修改系统目录属主"),
    (r'\bkillall\b', "批量杀进程"),
    (r'\bkill\s+-9\s+-1\b', "杀死所有进程"),
    (r'\bcrontab\b', "修改定时任务"),
    (r'\bmount\b', "挂载文件系统"),
    (r'\bumount\b', "卸载文件系统"),
    (r'\bssh-keygen\b', "生成 SSH 密钥"),
    (r'>\s*~?/?\.ssh/authorized_keys', "修改 SSH 授权密钥"),
]

_WORKSPACE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af]{1,64}$")


def validate_command(command: str) -> tuple[bool, str]:
    """校验命令安全性。"""
    if not command or not command.strip():
        return False, "空命令"
    for pattern, desc in _DANGEROUS_PATTERNS:
        if re.search(pattern, command.strip(), re.IGNORECASE):
            return False, f"危险命令被拦截（{desc}）"
    return True, ""


# ============ 路径管理 ============

def normalize_user_email(user_email: str) -> str:
    email = (user_email or "").strip()
    return email or "_anonymous"


def get_user_home(user_email: str) -> Path:
    """~/.Aries/{email}/"""
    home = Path.home() / ".Aries" / normalize_user_email(user_email)
    home.mkdir(parents=True, exist_ok=True)
    return home


def get_upload_dir(user_email: str) -> Path:
    """~/.Aries/{email}/upload/"""
    path = get_user_home(user_email) / "upload"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_workspaces_root(user_email: str) -> Path:
    """~/.Aries/{email}/workspaces/"""
    path = get_user_home(user_email) / "workspaces"
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_workspace_name(name: str) -> str:
    clean = (name or "").strip()
    if not clean:
        raise ValueError("工作目录名称不能为空")
    if clean in (".", "..") or "/" in clean or "\\" in clean:
        raise ValueError("工作目录名称不合法")
    if not _WORKSPACE_NAME_RE.match(clean):
        raise ValueError("工作目录名称仅允许字母、数字、下划线、连字符及中文")
    return clean


def ensure_workspace(user_email: str, workspace_name: str) -> Path:
    """创建并返回 ~/.Aries/{email}/workspaces/{name}/"""
    name = validate_workspace_name(workspace_name)
    path = get_workspaces_root(user_email) / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_workspace_path(user_email: str, workspace_name: str) -> Path:
    """返回工作目录路径（不存在时不创建）。"""
    name = validate_workspace_name(workspace_name)
    return get_workspaces_root(user_email) / name


def list_workspaces(user_email: str) -> list[dict[str, Any]]:
    """列出用户所有工作目录。"""
    root = get_workspaces_root(user_email)
    items: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue
        try:
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "path": str(entry),
                "modified_at": stat.st_mtime,
            })
        except OSError:
            continue
    return items


def get_tool_workspace(context: dict[str, Any] | None) -> tuple[Path | None, str]:
    """从工具 context 解析当前会话工作目录。"""
    ctx = context or {}
    user_email = (ctx.get("user_email") or "").strip()
    workspace_dir = (ctx.get("workspace_dir") or "default").strip() or "default"
    if not user_email:
        return None, "无法确定用户（context 中无 user_email）"
    try:
        return ensure_workspace(user_email, workspace_dir), ""
    except ValueError as exc:
        return None, str(exc)


def resolve_workspace_path(workspace: Path, path: str) -> tuple[Path | None, str]:
    """解析工作目录内的相对路径，禁止逃逸。"""
    raw = (path or "").strip()
    if not raw or raw in (".", "./"):
        return workspace, ""

    if os.path.isabs(raw) or raw.startswith("~") or (len(raw) > 1 and raw[1] == ":"):
        return None, "仅允许工作目录内的相对路径"

    parts = Path(raw).parts
    if ".." in parts:
        return None, "不允许路径穿越（..）"

    resolved = (workspace / raw).resolve()
    try:
        resolved.relative_to(workspace.resolve())
    except ValueError:
        return None, "路径超出当前工作目录范围"
    return resolved, ""


def validate_working_dir(workspace: Path, working_dir: str) -> tuple[bool, str, Path]:
    """验证 shell working_dir 子目录。"""
    if not working_dir:
        return True, "", workspace
    resolved, err = resolve_workspace_path(workspace, working_dir)
    if err or resolved is None:
        return False, err or "路径无效", workspace
    if resolved.exists() and not resolved.is_dir():
        return False, f"不是目录：{working_dir}", workspace
    resolved.mkdir(parents=True, exist_ok=True)
    return True, "", resolved


def get_allowed_skill_roots(user_email: str = "") -> list[Path]:
    """技能目录（只读）。"""
    roots: list[Path] = []
    shared = Path.home() / ".Aries" / "skills"
    roots.append(shared)
    email = normalize_user_email(user_email)
    if email != "_anonymous":
        roots.append(Path.home() / ".Aries" / email / "skills")
    return roots


def is_under_paths(target: Path, roots: list[Path]) -> bool:
    resolved = target.resolve()
    for root in roots:
        try:
            if not root.exists():
                continue
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def resolve_skill_read_path(
    user_email: str,
    path: str,
) -> tuple[Path | None, str]:
    """解析技能目录下的只读路径。"""
    raw = (path or "").strip()
    if not raw:
        return None, "路径不能为空"
    expanded = Path(os.path.expanduser(raw))
    if not expanded.is_absolute() and not raw.startswith("~"):
        return None, "技能路径需为绝对路径"
    resolved = expanded.resolve()
    if is_under_paths(resolved, get_allowed_skill_roots(user_email)):
        return resolved, ""
    return None, "路径超出技能目录范围"


# 兼容旧调用（逐步废弃）
def get_user_workspace(user_email: str) -> Path:
    return ensure_workspace(user_email, "default")


def resolve_sandbox_path(
    workspace: Path,
    path: str,
    *,
    user_email: str = "",
    allow_skills: bool = True,
) -> tuple[Path | None, str]:
    """解析路径：优先工作目录相对路径，可选技能绝对路径（只读）。"""
    raw = (path or "").strip()
    if not raw or raw in (".", "./"):
        return workspace, ""

    if allow_skills and (raw.startswith("~") or os.path.isabs(raw) or (len(raw) > 1 and raw[1] == ":")):
        skill_path, err = resolve_skill_read_path(user_email, raw)
        if skill_path:
            return skill_path, ""
        if err:
            return None, err

    return resolve_workspace_path(workspace, raw)


def cleanup_stale_workspaces(max_age_days: int | None = None) -> int:
    """清理超过 max_age_days 未修改且未被会话引用的工作目录（可选）。"""
    days = max_age_days if max_age_days is not None else getattr(settings, "WORKSPACE_CLEANUP_DAYS", 365)
    if days <= 0:
        return 0
    cutoff = time.time() - days * 86400
    count = 0
    aries = Path.home() / ".Aries"
    if not aries.exists():
        return 0
    for user_dir in aries.iterdir():
        if not user_dir.is_dir() or user_dir.name in ("plugins", "skills"):
            continue
        ws_root = user_dir / "workspaces"
        if not ws_root.is_dir():
            continue
        for ws_dir in ws_root.iterdir():
            if not ws_dir.is_dir() or ws_dir.name == "default":
                continue
            try:
                if ws_dir.stat().st_mtime >= cutoff:
                    continue
                shutil.rmtree(ws_dir, ignore_errors=True)
                count += 1
            except OSError:
                continue
    return count


def cleanup_all_workspaces() -> int:
    """兼容旧清理入口：改为 TTL 清理。"""
    return cleanup_stale_workspaces()


# ============ Windows bash 查找 ============

_cached_bash: str | None = None


def find_bash() -> str:
    global _cached_bash
    if _cached_bash is not None:
        return _cached_bash

    if sys.platform == "win32":
        git_path = shutil.which("git")
        if git_path:
            git_bash = Path(git_path).parent.parent / "bin" / "bash.exe"
            if git_bash.exists():
                _cached_bash = str(git_bash)
                return _cached_bash
        for path in [r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"]:
            if os.path.exists(path):
                _cached_bash = path
                return _cached_bash

    _cached_bash = ""
    return _cached_bash


# ============ 后台进程管理 ============

_bg_processes: dict[int, dict] = {}


def register_bg_process(pid: int, command: str, workspace: Path, session_id: str = "") -> None:
    _bg_processes[pid] = {
        "command": command,
        "workspace": str(workspace),
        "session_id": session_id,
    }


def list_bg_processes() -> list[dict]:
    result = []
    for pid, info in _bg_processes.items():
        result.append({
            "pid": pid,
            "command": info["command"],
            "running": _is_process_alive(pid),
        })
    return result


def unregister_bg_process(pid: int) -> None:
    _bg_processes.pop(pid, None)


def cleanup_session_processes(session_id: str) -> int:
    if not session_id:
        return 0
    killed = 0
    to_remove = []
    for pid, info in _bg_processes.items():
        if info.get("session_id") == session_id:
            if _is_process_alive(pid):
                try:
                    kill_process(pid)
                except Exception:
                    pass
            killed += 1
            to_remove.append(pid)
    for pid in to_remove:
        _bg_processes.pop(pid, None)
    return killed


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def kill_process(pid: int) -> bool:
    try:
        os.killpg(os.getpgid(pid), 9)
    except (OSError, ProcessLookupError):
        try:
            os.kill(pid, 9)
        except (OSError, ProcessLookupError):
            return False
    unregister_bg_process(pid)
    return True
