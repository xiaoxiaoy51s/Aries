"""Shell 命令沙箱：工作区隔离 + 危险命令拦截 + bwrap 支持。

设计要点：
1. 每个用户有独立工作区（~/.Aries/workspaces/{email_hash}/），AI 只能在此目录内操作。
2. 危险命令通过正则黑名单拦截（rm -rf /、dd、mkfs、fork bomb 等）。
3. 优先使用 bwrap（bubblewrap）创建 mount namespace 实现目录隔离；
   不可用时回退到 cd + HOME 限制 + PATH 白名单。
4. 路径逃逸检测：阻止通过 ../ 或绝对路径访问工作区外的文件。
5. 后台进程通过 nohup + PID 追踪，可查询状态/输出/停止。
6. 跨平台支持：Windows 上自动查找 Git Bash / WSL 的 bash。
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Optional

from app.config.settings import settings


# ============ 危险命令黑名单 ============

# 完全禁止的命令模式（不区分大小写）
_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # rm -rf 根目录 / 家目录 / 通配
    (r'rm\s+-[^\s]*r[^\s]*f[^\s]*\s+/(?:\s|$|[*])', "删除根目录"),
    (r'rm\s+-[^\s]*f[^\s]*r[^\s]*\s+/(?:\s|$|[*])', "删除根目录"),
    (r'rm\s+-rf\s+~(?:\s|$)', "删除家目录"),
    (r'rm\s+-rf\s+\*', "通配删除"),
    (r'rm\s+-rf\s+\.(?:\s|$)', "删除当前目录"),
    # 磁盘破坏
    (r'\bdd\b.*\bof\s*=\s*/dev/', "写入磁盘设备"),
    (r'\bmkfs\b', "格式化文件系统"),
    (r'\bfdisk\b', "磁盘分区操作"),
    (r'\bparted\b', "磁盘分区操作"),
    # fork bomb
    (r':\s*\(\)\s*\{.*:.*\|.*:.*&.*\}', "Fork 炸弹"),
    # 系统级操作
    (r'\bvisudo\b', "修改 sudoers"),
    (r'\bsystemctl\b', "系统服务管理"),
    (r'\bservice\b.*\b(start|stop|restart|enable|disable)\b', "系统服务管理"),
    (r'\bshutdown\b', "关机"),
    (r'\breboot\b', "重启"),
    (r'\binit\s+\d', "切换运行级别"),
    # 管道执行远程脚本
    (r'curl\s+.*\|\s*(sh|bash|zsh)\b', "管道执行远程脚本"),
    (r'wget\s+.*\|\s*(sh|bash|zsh)\b', "管道执行远程脚本"),
    # 写入设备文件
    (r'>\s*/dev/[sh]d', "写入磁盘设备"),
    # 包管理器安装（防止安装恶意软件）
    (r'\bapt(?:-get)?\s+(install|remove|purge|upgrade)\b', "系统包管理"),
    (r'\byum\s+(install|remove)\b', "系统包管理"),
    (r'\bdnf\s+(install|remove)\b', "系统包管理"),
    (r'\bpip\s+install\b', "Python 包安装"),
    (r'\bpip3\s+install\b', "Python 包安装"),
    # 危险权限
    (r'\bchmod\s+777\s+/(?:\s|$)', "根目录开放权限"),
    (r'\bchown\s+.*\s+/(?:etc|var|root|home|usr)(?:\s|$)', "修改系统目录属主"),
    # 进程大规模杀死
    (r'\bkillall\b', "批量杀进程"),
    (r'\bpkill\b(?!\s+.*-f\s+.*node)', "批量杀进程"),
    (r'\bkill\s+-9\s+-1\b', "杀死所有进程"),
    # crontab 修改
    (r'\bcrontab\b', "修改定时任务"),
    # 挂载/卸载
    (r'\bmount\b', "挂载文件系统"),
    (r'\bumount\b', "卸载文件系统"),
    # SSH 密钥操作
    (r'\bssh-keygen\b', "生成 SSH 密钥"),
    (r'>\s*~?/?\.ssh/authorized_keys', "修改 SSH 授权密钥"),
]

# 路径逃逸模式：检测可能跳出工作区的路径引用
_ESCAPE_PATTERNS = [
    r'/etc/',
    r'/var/',
    r'/root/',
    r'/boot/',
    r'/proc/',
    r'/sys/',
    r'/dev/(?!null|tty|urandom|zero)',
    r'/home/(?!.*workspace)',  # /home 下非工作区路径
    r'/opt/',
    r'/usr/local/',
    r'/snap/',
]


def validate_command(command: str) -> tuple[bool, str]:
    """校验命令安全性。

    Returns:
        (is_safe, reason) — is_safe=True 时 reason 为空。
    """
    if not command or not command.strip():
        return False, "空命令"

    cmd = command.strip()

    # 1. 危险命令黑名单
    for pattern, desc in _DANGEROUS_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return False, f"危险命令被拦截（{desc}）"

    # 2. 路径逃逸检测（仅在非 bwrap 模式下生效，bwrap 模式靠 mount namespace 隔离）
    if not has_bwrap():
        for pattern in _ESCAPE_PATTERNS:
            if re.search(pattern, cmd):
                return False, f"路径逃逸被拦截：命令引用了工作区外的系统路径"

    return True, ""


# ============ 工作区管理 ============

def get_workspace_root() -> Path:
    """获取所有用户工作区的根目录。"""
    root = Path(os.path.expanduser(settings.WORKSPACE_ROOT))
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_user_workspace(user_email: str) -> Path:
    """获取或创建指定用户的工作区目录。

    用 email 的 md5 前 12 位作为目录名，避免特殊字符。
    """
    email_hash = hashlib.md5(user_email.encode("utf-8")).hexdigest()[:12]
    ws = get_workspace_root() / email_hash
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def cleanup_all_workspaces() -> int:
    """清理所有用户工作区内容（保留目录结构）。

    每日凌晨 4 点调用，释放服务器空间。
    Returns: 清理的目录数。
    """
    root = get_workspace_root()
    count = 0
    for user_dir in root.iterdir():
        if not user_dir.is_dir():
            continue
        # 删除工作区内所有内容，保留目录本身
        for item in user_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                try:
                    item.unlink()
                except OSError:
                    pass
        count += 1
    return count


# ============ 跨平台 bash 查找 ============

_cached_bash: str | None = None
_cached_is_wsl: bool | None = None


def find_bash() -> str:
    """查找 bash 可执行文件路径。

    优先级：
    1. Windows 上通过 git 安装路径找 Git Bash（最兼容）
    2. Windows 上常见 Git Bash 安装路径
    3. PATH 中的 bash（Linux/Mac 或 Windows WSL bash）
    4. WSL 的 wsl.exe
    """
    global _cached_bash
    if _cached_bash:
        return _cached_bash

    if sys.platform == "win32":
        # 1. 通过 git 安装路径查找 Git Bash
        git_path = shutil.which("git")
        if git_path:
            # git 通常在 <git_root>/cmd/git.exe，bash 在 <git_root>/bin/bash.exe
            git_root = Path(git_path).parent.parent
            git_bash = git_root / "bin" / "bash.exe"
            if git_bash.exists():
                _cached_bash = str(git_bash)
                return _cached_bash

        # 2. 常见 Git Bash 路径
        for path in [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ]:
            if os.path.exists(path):
                _cached_bash = path
                return _cached_bash

        # 3. PATH 中的 bash（可能是 WSL bash: C:\WINDOWS\system32\bash.exe）
        bash = shutil.which("bash")
        if bash:
            _cached_bash = bash
            return _cached_bash

        # 4. WSL
        wsl = shutil.which("wsl")
        if wsl:
            _cached_bash = wsl
            return _cached_bash

    # Linux/Mac
    bash = shutil.which("bash")
    if bash:
        _cached_bash = bash
        return bash

    _cached_bash = "bash"
    return "bash"


def is_wsl_bash() -> bool:
    """判断当前 bash 是否通过 WSL 调用。

    WSL bash 包括：
    - C:\WINDOWS\system32\bash.exe（WSL Bash Launcher）
    - wsl.exe
    """
    global _cached_is_wsl
    if _cached_is_wsl is not None:
        return _cached_is_wsl

    if sys.platform != "win32":
        _cached_is_wsl = False
        return False

    bash = find_bash()
    bash_lower = bash.lower().replace("\\", "/")
    _cached_is_wsl = bash_lower.endswith("wsl.exe") or "system32/bash.exe" in bash_lower
    return _cached_is_wsl


def _to_bash_path(path: Path) -> str:
    """将路径转换为 bash 兼容格式。

    - Git Bash：C:\\Users\\... -> C:/Users/...（正斜杠即可）
    - WSL：C:\\Users\\... -> /mnt/c/Users/...
    - Linux/Mac：原样返回
    """
    path_str = str(path)
    if sys.platform != "win32":
        return path_str

    if is_wsl_bash():
        # WSL 路径转换：C:\Users\... -> /mnt/c/Users/...
        path_str = path_str.replace("\\", "/")
        if len(path_str) >= 2 and path_str[1] == ":":
            drive = path_str[0].lower()
            path_str = f"/mnt/{drive}{path_str[2:]}"
        return path_str
    else:
        # Git Bash：正斜杠即可
        return path_str.replace("\\", "/")


# ============ bwrap 沙箱 ============

def has_bwrap() -> bool:
    """检测系统是否安装 bubblewrap。"""
    return shutil.which("bwrap") is not None


def build_command_args(
    command: str,
    workspace: Path,
    timeout: int = 30,
    background: bool = False,
    env_extra: dict[str, str] | None = None,
) -> list[str]:
    """构建安全执行的命令参数。

    bwrap 可用时：创建 mount namespace，工作区挂载为 /workspace，系统目录只读绑定。
    不可用时：cd 到工作区 + 设置 HOME + 限制 PATH。

    跨平台：Windows 上自动使用 Git Bash 或 WSL，路径自动转换。

    Args:
        command: 用户要执行的 shell 命令
        workspace: 工作区绝对路径
        timeout: 超时秒数（仅同步模式）
        background: 是否后台运行
        env_extra: 额外环境变量
    """
    bash = find_bash()
    ws_str = _to_bash_path(workspace)
    env_vars = {
        "HOME": ws_str,
        "TERM": "xterm-256color",
        "LANG": "C.UTF-8",
        "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    }
    if env_extra:
        env_vars.update(env_extra)

    # 构造 env 前缀
    env_prefix = " ".join(f'{k}="{v}"' for k, v in env_vars.items())

    # WSL 调用需要加 bash 前缀
    wsl_prefix = ["bash"] if is_wsl_bash() else []

    if has_bwrap() and not background:
        # bwrap 沙箱：mount namespace 隔离
        args = [
            "bwrap",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind-try", "/lib", "/lib",
            "--ro-bind-try", "/lib64", "/lib64",
            "--ro-bind-try", "/bin", "/bin",
            "--ro-bind-try", "/sbin", "/sbin",
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            "--bind", ws_str, "/workspace",
            "--chdir", "/workspace",
            "--die-with-parent",
            "--new-session",
        ]
        # 网络：允许网络访问（AI 需要联网能力）
        # 不加 --unshare-net 即可保持网络共享

        # 设置环境变量 + 超时
        inner = f"cd /workspace && {env_prefix} timeout {timeout} bash -c {_shell_quote(command)}"
        args += ["bash", "-c", inner]
        return args

    elif has_bwrap() and background:
        # 后台模式：nohup + 重定向输出
        args = [
            "bwrap",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind-try", "/lib", "/lib",
            "--ro-bind-try", "/lib64", "/lib64",
            "--ro-bind-try", "/bin", "/bin",
            "--ro-bind-try", "/sbin", "/sbin",
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            "--bind", ws_str, "/workspace",
            "--chdir", "/workspace",
            "--die-with-parent",
        ]
        inner = (
            f"cd /workspace && {env_prefix} "
            f"nohup bash -c {_shell_quote(command)} "
            f"> /workspace/.bg_output.log 2>&1 & echo $!"
        )
        args += ["bash", "-c", inner]
        return args

    else:
        # 回退模式：cd + HOME 限制（WSL / Git Bash / 无 bwrap 环境）
        if background:
            inner = (
                f'cd "{ws_str}" && {env_prefix} '
                f'nohup bash -c {_shell_quote(command)} '
                f'> "{ws_str}/.bg_output.log" 2>&1 & echo $!'
            )
            return wsl_prefix + [bash, "-c", inner] if wsl_prefix else [bash, "-c", inner]
        else:
            inner = (
                f'cd "{ws_str}" && {env_prefix} '
                f'timeout {timeout} bash -c {_shell_quote(command)}'
            )
            return wsl_prefix + [bash, "-c", inner] if wsl_prefix else [bash, "-c", inner]


def _shell_quote(s: str) -> str:
    """安全引用 shell 字符串。"""
    return "'" + s.replace("'", "'\"'\"'") + "'"


# ============ working_dir 验证 ============

def validate_working_dir(workspace: Path, working_dir: str) -> tuple[bool, str, Path]:
    """验证 working_dir 是否在工作区内。

    Args:
        workspace: 工作区根目录
        working_dir: 用户指定的子目录（相对路径）

    Returns:
        (is_valid, reason, resolved_path)
    """
    if not working_dir:
        return True, "", workspace

    # 禁止绝对路径
    if working_dir.startswith("/"):
        return False, "working_dir 必须是相对路径", workspace

    # 解析并检查是否在工作区内（防 ../ 逃逸）
    resolved = (workspace / working_dir).resolve()
    try:
        resolved.relative_to(workspace.resolve())
    except ValueError:
        return False, "working_dir 路径逃逸：超出工作区范围", workspace

    # 自动创建子目录
    resolved.mkdir(parents=True, exist_ok=True)
    return True, "", resolved


# ============ 后台进程管理 ============

# 进程注册表：pid -> {command, workspace, output_file, session_id}
_bg_processes: dict[int, dict] = {}


def register_bg_process(
    pid: int,
    command: str,
    workspace: Path,
    output_file: str,
    session_id: str = "",
) -> None:
    """注册后台进程，关联会话 ID 用于流式结束后清理。"""
    _bg_processes[pid] = {
        "command": command,
        "workspace": str(workspace),
        "output_file": output_file,
        "session_id": session_id,
    }


def get_bg_process(pid: int) -> dict | None:
    """查询后台进程信息。"""
    return _bg_processes.get(pid)


def list_bg_processes() -> list[dict]:
    """列出所有后台进程。"""
    result = []
    for pid, info in _bg_processes.items():
        alive = _is_process_alive(pid)
        result.append({
            "pid": pid,
            "command": info["command"],
            "running": alive,
        })
    return result


def unregister_bg_process(pid: int) -> None:
    """注销后台进程。"""
    _bg_processes.pop(pid, None)


def cleanup_session_processes(session_id: str) -> int:
    """杀掉指定会话的所有后台进程。

    在对话流式结束后调用，确保后台进程不会泄漏。
    Returns: 被杀掉的进程数。
    """
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
    """检查进程是否存活。

    Windows 上 Git Bash/WSL 的 PID 与 Windows PID 不同，
    需要通过 bash 检查。
    """
    if sys.platform == "win32":
        import subprocess
        bash = find_bash()
        try:
            if is_wsl_bash():
                result = subprocess.run([bash, "bash", "-c", f"kill -0 {pid} 2>/dev/null"], timeout=5, capture_output=True)
            else:
                result = subprocess.run([bash, "-c", f"kill -0 {pid} 2>/dev/null"], timeout=5, capture_output=True)
            return result.returncode == 0
        except Exception:
            return False
    try:
        os.kill(pid, 0)  # signal 0 = 不发信号，仅检查进程是否存在
        return True
    except (OSError, ProcessLookupError):
        return False


def kill_process(pid: int) -> bool:
    """终止进程。

    Windows 上通过 bash 执行 kill，兼容 Git Bash/WSL 的 PID。
    """
    if sys.platform == "win32":
        import subprocess
        bash = find_bash()
        kill_cmd = f"kill -9 {pid} 2>/dev/null; kill -9 -{pid} 2>/dev/null"
        try:
            if is_wsl_bash():
                subprocess.run([bash, "bash", "-c", kill_cmd], timeout=5, capture_output=True)
            else:
                subprocess.run([bash, "-c", kill_cmd], timeout=5, capture_output=True)
        except Exception:
            pass
        unregister_bg_process(pid)
        return True
    try:
        os.killpg(os.getpgid(pid), 9)  # 杀整个进程组
    except (OSError, ProcessLookupError):
        try:
            os.kill(pid, 9)
        except (OSError, ProcessLookupError):
            return False
    unregister_bg_process(pid)
    return True
