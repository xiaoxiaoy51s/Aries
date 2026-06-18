"""
CLI Executor - 基础命令执行工具
被 agent_tools.py 直接引用，作为核心后端功能
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any


class CLIExecutor:
    DEFAULT_TIMEOUT_SECONDS = 300
    MAX_TIMEOUT_SECONDS = 86400
    DIRECT_VISIBLE_COMMAND_MAX_LENGTH = 4000

    DANGEROUS_PATTERNS = [
        (r"\b(del|erase|rd|rmdir|rm)\b", "删除文件或目录"),
        (r"\b(move|mv|ren|rename)\b", "移动或重命名文件"),
        (r"((?<!-)\bformat\b(?!-)|\bshutdown\b|\brestart\b)", "系统危险操作"),
        (r"\b(reg\s)", "注册表操作"),
        (r"\b(net\s+user|net\s+localgroup)\b", "用户管理操作"),
    ]

    BLOCKED_PATTERNS = [
        r"\.\.\\",
        r"\.\./",
        r"powershell.*-enc",
        r"powershell.*-e\s",
        r"wget\b",
        r"curl.*\|\s*bash",
    ]

    ALLOWED_PATTERNS = [
        r"^python\s+",
        r"^python3\s+",
        r"^pip\s+",
        r"^npm\s+",
    ]

    AUTO_DETACH_READY_PATTERNS = (
        r"http://localhost:\d+/?",
        r"https://localhost:\d+/?",
        r"\bvite\b.*\bready\b",
        r"\bready in\b",
        r"\bpress h \+ enter to show help\b",
        r"\blocal:\s+http://",
    )
    AUTO_DETACH_STABLE_SECONDS = 1.5

    _powershell_lock = threading.Lock()
    _resolved_powershell_exe: str | None = None
    _log_lock = threading.Lock()
    _active_processes: dict[str, subprocess.Popen[str]] = {}
    _interrupt_actions: dict[str, str] = {}
    _process_lock = threading.Lock()

    @classmethod
    def _runtime_root(cls) -> Path:
        """ps1 调度/日志/done 文件的根目录。

        统一使用 ~/.MIMOClaw/temp/cli_runtime，避免：
        1. 把临时文件散落到系统 TEMP 中；
        2. 避免 AI 进程把日志写到 work_dir 时造成的死锁/误读。
        """
        root = Path.home() / ".MIMOClaw" / "temp" / "cli_runtime"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def __init__(self, user_email: str | None = None, work_dir: str | None = None) -> None:
        from utils.user_file_manager import UserFileManager
        self.manager = UserFileManager(work_dir=work_dir)
        self._user_home_dir = Path.home().resolve()
        # 显式工作目录时使用该目录；否则沿用默认 ~/.MIMOClaw
        if work_dir and work_dir.strip():
            self._allowed_dir = Path(work_dir).expanduser().resolve()
        else:
            self._allowed_dir = self.manager.get_user_dir()
        self._allowed_dir.mkdir(parents=True, exist_ok=True)

    @property
    def allowed_dir(self) -> Path:
        return self._allowed_dir

    @property
    def user_home_dir(self) -> Path:
        return self._user_home_dir

    def _resolve_target_dir(self, working_dir: str | None) -> Path:
        if not working_dir or not working_dir.strip():
            return self._allowed_dir
        target = Path(working_dir).resolve()
        if target == self._user_home_dir or str(target).startswith(str(self._user_home_dir) + os.sep):
            return target
        if target == self._allowed_dir or str(target).startswith(str(self._allowed_dir) + os.sep):
            return target
        # 越界：返回 allowed_dir 作为默认，由 execute 方法判断危险
        return self._allowed_dir

    def _is_working_dir_outside_allowed(self, working_dir: str | None) -> bool:
        """判断指定的工作目录是否超出允许范围。"""
        if not working_dir or not working_dir.strip():
            return False
        target = Path(working_dir).resolve()
        if target == self._user_home_dir or str(target).startswith(str(self._user_home_dir) + os.sep):
            return False
        if target == self._allowed_dir or str(target).startswith(str(self._allowed_dir) + os.sep):
            return False
        return True

    def _is_allowed_command(self, command: str) -> tuple[bool, str]:
        for pattern in self.ALLOWED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return True, f"命令匹配白名单模式：{pattern}"
        return False, ""

    def _is_blocked_command(self, command: str) -> tuple[bool, str]:
        is_allowed, _ = self._is_allowed_command(command)
        if is_allowed:
            return False, ""
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return True, f"命令包含被阻止的模式：{pattern}"
        return False, ""

    def _check_dangerous_command(self, command: str) -> dict[str, Any] | None:
        danger_types = []
        danger_info_parts = []
        for pattern, description in self.DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                danger_types.append(description)
                danger_info_parts.append(description)
        if danger_types:
            return {
                "danger_types": danger_types,
                "danger_info": "、".join(danger_info_parts),
            }
        return None

    def _truncate_output(self, output: str, max_length: int = 10000) -> str:
        if len(output) <= max_length:
            return output
        return output[:max_length] + f"\n... (输出已截断，共 {len(output)} 字符)"

    @staticmethod
    def _escape_ps_single_quoted(value: str) -> str:
        return str(value or "").replace("'", "''")

    @staticmethod
    def _is_dir_listing_command(command: str) -> bool:
        normalized = (command or "").strip()
        import shlex
        try:
            tokens = shlex.split(normalized, posix=False)
        except Exception:
            tokens = normalized.split()
        if not tokens:
            return False
        first = tokens[0].lower().rstrip("/\\").rstrip(":")
        return first in ("dir", "ls", "gci", "get-childitem", "childitem")

    @staticmethod
    def _ensure_wide_dir_output(command: str) -> str:
        import shlex
        normalized = (command or "").strip()
        lower = normalized.lower()
        if any(flag in lower for flag in ("-name", " | ", "format-table", "select-object", "out-string")):
            return normalized
        try:
            tokens = shlex.split(normalized, posix=False)
        except Exception:
            return normalized
        first = (tokens[0] or "").lower().rstrip("/\\").rstrip(":")
        if first not in ("dir", "ls", "gci", "get-childitem", "childitem"):
            return normalized
        args_str = " ".join(tokens[1:]) if len(tokens) > 1 else "."
        wrapped = (
            f"Get-ChildItem {args_str} | "
            "Select-Object @{N='Mode';E={$_.Mode}}, "
            "@{N='LastWriteTime';E={$_.LastWriteTime.ToString('yyyy-MM-dd HH:mm')}}, "
            "@{N='Size';E={if($_.PSIsContainer){'  <DIR>'}else{'{0,12:N0}' -f $_.Length}}}, "
            "Name | "
            "Format-Table -AutoSize | "
            "Out-String -Width 4096"
        )
        return wrapped

    @staticmethod
    def _build_windows_shell_path_candidates() -> list[str]:
        candidates: list[str] = []
        system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
        candidates.append(
            str(Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
        )
        candidates.append(
            str(Path(system_root) / "Sysnative" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
        )
        return candidates

    @classmethod
    def _is_usable_powershell(cls, executable: str) -> bool:
        try:
            result = subprocess.run(
                [executable, "-NoProfile", "-NonInteractive", "-Command", "echo ok"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return False
        except Exception:
            return False
        return result.returncode == 0 and "ok" in (result.stdout or "").lower()

    @classmethod
    def _resolve_powershell_exe(cls) -> str:
        with cls._powershell_lock:
            if cls._resolved_powershell_exe and cls._is_usable_powershell(cls._resolved_powershell_exe):
                return cls._resolved_powershell_exe
            probe_candidates: list[str] = []
            configured = str(os.environ.get("POWERSHELL_EXE", "") or "").strip()
            if configured:
                probe_candidates.append(configured)
            for name in ("powershell.exe", "powershell", "pwsh.exe", "pwsh"):
                resolved = shutil.which(name)
                if resolved:
                    probe_candidates.append(resolved)
                probe_candidates.append(name)
            probe_candidates.extend(cls._build_windows_shell_path_candidates())
            checked: set[str] = set()
            for candidate in probe_candidates:
                normalized = str(candidate or "").strip()
                if not normalized:
                    continue
                key = normalized.lower()
                if key in checked:
                    continue
                checked.add(key)
                if cls._is_usable_powershell(normalized):
                    cls._resolved_powershell_exe = normalized
                    return normalized
            raise RuntimeError(
                "未找到可用 PowerShell。请确认系统已安装 PowerShell，"
                "并检查 PATH；也可设置环境变量 POWERSHELL_EXE 指向 powershell.exe 或 pwsh.exe。"
            )

    @classmethod
    def _resolve_classic_powershell_exe(cls) -> str:
        for candidate in cls._build_windows_shell_path_candidates():
            normalized = str(candidate or "").strip()
            if normalized and cls._is_usable_powershell(normalized):
                return normalized
        return cls._resolve_powershell_exe()

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str], force: bool = False) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                cmd = ["taskkill", "/PID", str(process.pid), "/T"]
                if force:
                    cmd.append("/F")
                subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
            elif force:
                process.kill()
            else:
                process.terminate()
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "cli_executor",
                "description": (
                    "执行本地 CLI 命令。仅用于文件操作、运行脚本、读取目录信息、安装依赖等任务。"
                    "如果命令包含删除、重命名、系统级变更等危险操作，会返回需要用户确认。"
                    "\n\n【重要提示】"
                    "1. 当返回 'file is locked' 或 'Internal error' 但 exit_code=0 时，说明命令实际已成功执行，无需重试。"
                    "2. 对于 pip install 等网络操作，建议设置 timeout 为 120 秒或更长。"
                    "3. 执行 Python 脚本时，如果脚本路径包含空格，请使用引号包裹。"
                    "4. 对于 npm run dev、pnpm dev、yarn dev、vite、next dev 等开发服务器，必须设置 open_in_terminal=true，timeout 建议 30-60 秒；服务启动成功后系统会自动转入后台，不要为了等待服务结束设置很长 timeout。"
                    "5. 对于需要用户看实时输出的长命令（如 npm create、git clone），可将 open_in_terminal 设为 true。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要执行的命令。",
                        },
                        "working_dir": {
                            "type": "string",
                            "description": (
                                "可选执行目录。留空时固定为用户目录；"
                                "也可设为用户目录下的子目录，或当前用户主目录及其子目录。"
                            ),
                            "default": "",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "超时时间（秒）。简单命令建议 30s；开发服务器建议 30-60s，启动后会自动后台保留；pip install 等网络操作可用 120s+；默认 300。",
                            "default": 300,
                        },
                        "open_in_terminal": {
                            "type": "boolean",
                            "description": (
                                "是否在用户可见的终端中执行。默认 false（后台执行）。"
                                "适用于需要用户看到实时输出或交互的命令。设为 true 时命令会在前端终端面板中显示。"
                            ),
                            "default": False,
                        },
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            },
        }

    def execute(
        self,
        command: str,
        working_dir: str | None = None,
        timeout: int = 300,
        skip_confirmation: bool = False,
        invocation_id: str | None = None,
        open_in_terminal: bool = False,
        terminal_session_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_command = str(command or "").strip()
        if not normalized_command:
            return {
                "success": False,
                "error": "Missing command",
                "output": "缺少要执行的命令",
                "command": "",
                "working_dir": str(self._allowed_dir),
                "requires_confirmation": False,
            }
        if normalized_command.startswith("claude"):
            if "--permission-mode" not in normalized_command and "-p" in normalized_command:
                normalized_command = normalized_command.replace("-p", "-p --permission-mode bypassPermissions", 1)
        timeout = max(1, min(timeout, self.MAX_TIMEOUT_SECONDS))
        target_dir = self._resolve_target_dir(working_dir)
        is_blocked, block_msg = self._is_blocked_command(normalized_command)
        if is_blocked:
            return {
                "success": False,
                "error": f"Command blocked: {block_msg}",
                "output": f"命令被阻止\n命令: {normalized_command}\n原因: {block_msg}",
                "command": normalized_command,
                "working_dir": str(target_dir),
                "requires_confirmation": False,
            }
        danger_check = self._check_dangerous_command(normalized_command)
        is_oob = self._is_working_dir_outside_allowed(working_dir)
        from db.path_permissions import check_path_permission
        perm_result = check_path_permission(str(target_dir))
        if perm_result:
            if perm_result.get("allowed"):
                danger_check = None
                is_oob = False
            else:
                return {
                    "success": False,
                    "error": "Path blocked",
                    "output": (
                        f"命令执行被拒绝\n命令: {normalized_command}\n"
                        f"执行目录: {target_dir}\n"
                        f"原因: {perm_result.get('reason', '黑名单限制')}\n"
                        f"用户已将该路径加入黑名单，禁止 AI 在此执行命令。"
                    ),
                    "command": normalized_command,
                    "working_dir": str(target_dir),
                    "requires_confirmation": False,
                    "danger_types": ["路径在黑名单中"],
                    "danger_info": perm_result.get("reason", "黑名单限制"),
                }
        if is_oob:
            oob_info = "工作目录超出允许范围"
            if danger_check:
                danger_check["danger_types"].append(oob_info)
                danger_check["danger_info"] = "、".join(danger_check["danger_types"])
            else:
                danger_check = {
                    "danger_types": [oob_info],
                    "danger_info": oob_info,
                }
        if danger_check and not skip_confirmation:
            return {
                "success": False,
                "error": "Confirmation required",
                "output": (
                    f"危险命令需要确认\n命令: {normalized_command}\n"
                    f"原因: {danger_check['danger_info']}\n请由用户手动确认后再继续执行。"
                ),
                "command": normalized_command,
                "working_dir": str(target_dir),
                "requires_confirmation": True,
                "danger_types": danger_check["danger_types"],
                "danger_info": danger_check["danger_info"],
            }
        target_dir.mkdir(parents=True, exist_ok=True)

        # 根据 open_in_terminal 选择执行方式
        if open_in_terminal:
            # AI 主动在终端中执行：创建专用终端会话，前端可连接查看
            try:
                from services.terminal_manager import TerminalManager
                tm = TerminalManager.get_instance()
                pty_result = tm.open_terminal_for_command(
                    command=normalized_command,
                    work_dir=str(target_dir),
                    timeout=timeout,
                    invocation_id=invocation_id,
                )
            except Exception as exc:
                pty_result = None

            if pty_result is not None:
                return_code = int(pty_result.get("return_code") or 0)
                captured = str(pty_result.get("output_capture") or "").strip()
                timed_out = bool(pty_result.get("timed_out"))
                interrupted_action = pty_result.get("interrupted_action")
                session_id = pty_result.get("session_id")
                auto_detached = bool(pty_result.get("auto_detached"))

                if interrupted_action:
                    return {
                        "success": False,
                        "interrupted": True,
                        "interrupted_action": interrupted_action,
                        "error": "Command interrupted by user",
                        "output": (
                            f"命令已被用户中断\n命令: {normalized_command}\n"
                            f"执行目录: {target_dir}\n"
                            f"中断前终端输出:\n{self._truncate_output(captured) if captured else '(无输出)'}"
                        ),
                        "command": normalized_command,
                        "working_dir": str(target_dir),
                        "requires_confirmation": False,
                        "captured_output": captured,
                        "session_id": session_id,
                    }
                if auto_detached:
                    return {
                        "success": True,
                        "return_code": 0,
                        "captured_output": captured,
                        "output": (
                            f"开发服务器已启动并转入后台运行\n"
                            f"命令: {normalized_command}\n"
                            f"执行目录: {target_dir}\n"
                            f"可在右侧控制台查看或停止该服务。"
                        ),
                        "command": normalized_command,
                        "working_dir": str(target_dir),
                        "requires_confirmation": False,
                        "session_id": session_id,
                        "auto_detached": True,
                    }

                if timed_out:
                    return {
                        "success": False,
                        "error": f"Command timed out after {timeout} seconds",
                        "output": (
                            f"命令执行超时\n命令: {normalized_command}\n"
                            f"执行目录: {target_dir}\n超时时间: {timeout} 秒\n"
                            f"终端输出:\n{self._truncate_output(captured) if captured else '(无输出)'}"
                        ),
                        "command": normalized_command,
                        "working_dir": str(target_dir),
                        "requires_confirmation": False,
                        "captured_output": captured,
                        "session_id": session_id,
                    }

                output_lines = [
                    f"Command: {normalized_command}",
                    f"Working directory: {target_dir}",
                    f"Return code: {return_code}",
                ]
                if captured:
                    output_lines.append(self._truncate_output(captured))
                else:
                    output_lines.append("(empty output)")

                return {
                    "success": return_code == 0,
                    "return_code": return_code,
                    "captured_output": captured,
                    "output": "\n".join(output_lines),
                    "command": normalized_command,
                    "working_dir": str(target_dir),
                    "requires_confirmation": False,
                    "session_id": session_id,
                    "auto_detached": auto_detached,
                }

            # PTY 不可用时 fallback 到隐藏子进程
            pty_result = None

        # 后台静默执行（open_in_terminal=false 或 PTY fallback）
        try:
            process = subprocess.Popen(
                normalized_command,
                shell=True,
                cwd=str(target_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "output": (
                    f"命令执行失败\n命令: {normalized_command}\n"
                    f"执行目录: {target_dir}\n异常: {exc}"
                ),
                "command": normalized_command,
                "working_dir": str(target_dir),
                "requires_confirmation": False,
            }
        if invocation_id:
            self._register_process(invocation_id, process)
        stdout = ""
        stderr = ""
        timed_out = False
        interrupted_action = None
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if invocation_id:
                    pending_action = self._consume_interrupt_action(invocation_id)
                    if pending_action:
                        interrupted_action = pending_action
                        if pending_action == "background":
                            stdout = "命令已转入后台运行"
                            stderr = ""
                            break
                        self._terminate_process(process, force=True)
                        try:
                            stdout, stderr = process.communicate(timeout=5)
                        except subprocess.TimeoutExpired:
                            self._terminate_process(process, force=True)
                            stdout, stderr = process.communicate(timeout=5)
                        break
                if time.monotonic() >= deadline:
                    timed_out = True
                    self._terminate_process(process, force=True)
                    try:
                        stdout, stderr = process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        stdout = stdout or ""
                        stderr = (stderr or "").strip()
                    break
        finally:
            if invocation_id:
                self._unregister_process(invocation_id)
        command_return_code = int(process.returncode or 0)
        if interrupted_action == "background":
            return {
                "success": True,
                "interrupted_action": interrupted_action,
                "output": (
                    f"命令已转入后台运行\n命令: {normalized_command}\n"
                    f"执行目录: {target_dir}"
                ),
                "command": normalized_command,
                "working_dir": str(target_dir),
                "requires_confirmation": False,
                "auto_detached": True,
            }
        if interrupted_action:
            return {
                "success": False,
                "interrupted": True,
                "interrupted_action": interrupted_action,
                "error": f"Command interrupted by user",
                "output": (
                    f"命令已被用户中断\n命令: {normalized_command}\n"
                    f"执行目录: {target_dir}"
                ),
                "command": normalized_command,
                "working_dir": str(target_dir),
                "requires_confirmation": False,
            }
        if timed_out:
            return {
                "success": False,
                "error": f"Command timed out after {timeout} seconds",
                "output": (
                    f"命令执行超时\n命令: {normalized_command}\n"
                    f"执行目录: {target_dir}\n超时时间: {timeout} 秒"
                ),
                "command": normalized_command,
                "working_dir": str(target_dir),
                "requires_confirmation": False,
            }
        output = (stdout or "").strip()
        stderr = (stderr or "").strip()
        if stderr:
            output = f"{output}\n[STDERR]\n{stderr}".strip()
        if not output:
            output = "(命令执行完成，无输出)"
        else:
            output = self._truncate_output(output)
        output_lines = [
            f"Executed command: {normalized_command}",
            f"Working directory: {target_dir}",
            f"Return code: {command_return_code}",
            "Output:",
            output,
        ]
        return {
            "success": command_return_code == 0,
            "return_code": command_return_code,
            "output": "\n".join(output_lines),
            "command": normalized_command,
            "working_dir": str(target_dir),
            "requires_confirmation": False,
        }

    @classmethod
    def _register_process(cls, invocation_id: str, process: subprocess.Popen[str]) -> None:
        with cls._process_lock:
            cls._active_processes[invocation_id] = process
            cls._interrupt_actions.pop(invocation_id, None)

    @classmethod
    def _unregister_process(cls, invocation_id: str) -> None:
        with cls._process_lock:
            cls._active_processes.pop(invocation_id, None)
            cls._interrupt_actions.pop(invocation_id, None)

    @classmethod
    def _consume_interrupt_action(cls, invocation_id: str) -> str | None:
        with cls._process_lock:
            return cls._interrupt_actions.pop(invocation_id, None)

    @classmethod
    def set_interrupt_action(cls, invocation_id: str, action: str) -> None:
        if not invocation_id or not action:
            return
        with cls._process_lock:
            target_id = invocation_id
            if target_id not in cls._active_processes:
                suffix = f":{invocation_id}"
                for key in cls._active_processes.keys():
                    if key.endswith(suffix):
                        target_id = key
                        break
            cls._interrupt_actions[target_id] = action

    @classmethod
    def terminate_all_active(cls, action: str = "terminate") -> list[int]:
        terminated: list[int] = []
        targets: list[tuple[str, subprocess.Popen[str]]] = []
        with cls._process_lock:
            for inv_id in list(cls._active_processes.keys()):
                cls._interrupt_actions[inv_id] = action
            targets = list(cls._active_processes.items())
        for inv_id, process in targets:
            try:
                if process.poll() is None:
                    pid = int(process.pid)
                    cls._terminate_process(process, force=(action == "terminate"))
                    terminated.append(pid)
            except Exception:
                pass
        return terminated

    @classmethod
    def get_active_invocations(cls) -> list[str]:
        with cls._process_lock:
            return list(cls._active_processes.keys())

    @classmethod
    def clear_runtime_dir(cls) -> int:
        """清理 ~/.MIMOClaw/temp/cli_runtime 下的残留文件（dispatch_*/done_*）。

        适用于：用户暂停/关闭文件/切换会话时，确保下一轮不会误读上一次未结束的日志。
        """
        runtime_dir = cls._runtime_root()
        removed = 0
        if not runtime_dir.exists():
            return 0
        try:
            for item in runtime_dir.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                        removed += 1
                    elif item.is_file():
                        item.unlink(missing_ok=True)
                        removed += 1
                except Exception:
                    pass
        except Exception:
            pass
        return removed
