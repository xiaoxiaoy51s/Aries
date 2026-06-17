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

    _visible_shell_lock = threading.Lock()
    _visible_shell_command_lock = threading.Lock()
    _visible_shell_process: subprocess.Popen[str] | None = None
    _visible_shell_dispatch_dir: Path | None = None
    _powershell_lock = threading.Lock()
    _resolved_powershell_exe: str | None = None
    _log_lock = threading.Lock()
    _active_processes: dict[str, subprocess.Popen[str]] = {}
    _interrupt_actions: dict[str, str] = {}
    _active_visible_polls: dict[str, dict[str, Any]] = {}
    _cancel_all_event = threading.Event()

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
        CLIExecutor._cleanup_old_runtime_files()

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
    def _visible_shell_command_echo_literal(command: str) -> str:
        raw = str(command or "").strip().replace("\r\n", "\n")
        if not raw:
            return CLIExecutor._escape_ps_single_quoted("(empty)")
        if len(raw) > 1200:
            raw = raw[:1200] + "..."
        display = raw.replace("\n", " | ")
        return CLIExecutor._escape_ps_single_quoted(display)

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

    @classmethod
    def _reset_visible_shell(cls) -> None:
        with cls._visible_shell_lock:
            cls._visible_shell_process = None
            cls._visible_shell_dispatch_dir = None

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

    @classmethod
    def _shared_shell_bootstrap_command(cls, bootstrap_dir: Path) -> str:
        qd = cls._escape_ps_single_quoted(str(bootstrap_dir.resolve()))
        dispatch_dir = cls._runtime_root() / "shared_dispatch"
        qdispatch = cls._escape_ps_single_quoted(str(dispatch_dir.resolve()))
        return (
            f"Set-Location -LiteralPath '{qd}'; "
            "$ErrorActionPreference = 'Continue'; "
            "try { "
            "$Host.UI.RawUI.WindowTitle = 'NonoClaw shared shell'; "
            "Write-Host 'NonoClaw shared shell - 自动化下发命令（非完整交互式会话），外观与手动打开的 PowerShell 可能不同。' "
            "} catch {}; "
            f"$dispatchDir = '{qdispatch}'; "
            "if (-not (Test-Path -LiteralPath $dispatchDir)) { "
            "  New-Item -ItemType Directory -Path $dispatchDir -Force | Out-Null "
            "}; "
            "while ($true) { "
            "  $jobs = @(Get-ChildItem -LiteralPath $dispatchDir -Filter 'job_*.ps1' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime, Name); "
            "  if ($jobs.Count -eq 0) { Start-Sleep -Milliseconds 200; continue }; "
            "  foreach ($job in $jobs) { "
            "    try { & $job.FullName } catch { ($_ | Out-String) | Write-Host }; "
            "    Remove-Item -LiteralPath $job.FullName -Force -ErrorAction SilentlyContinue "
            "  } "
            "}"
        )

    @classmethod
    def _cleanup_old_runtime_files(cls) -> None:
        runtime_dir = cls._runtime_root()
        if not runtime_dir.exists():
            return
        try:
            for item in runtime_dir.iterdir():
                if item.is_dir() and item.name.startswith("dispatch_"):
                    try:
                        shutil.rmtree(item, ignore_errors=True)
                    except Exception:
                        pass
                elif item.is_file() and item.name.startswith("done_"):
                    try:
                        stat = item.stat()
                        if time.time() - stat.st_mtime > 3600:
                            item.unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception:
            pass

    @classmethod
    def _ensure_shared_visible_shell(cls, bootstrap_dir: Path) -> subprocess.Popen[str]:
        with cls._visible_shell_lock:
            shell = cls._visible_shell_process
            if shell and shell.poll() is None:
                return shell
            if shell is not None and shell.poll() is not None:
                cls._cleanup_old_runtime_files()
            powershell_exe = cls._resolve_classic_powershell_exe()
            create_new_console = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            bootstrap = cls._shared_shell_bootstrap_command(bootstrap_dir)
            dispatch_dir = cls._runtime_root() / "shared_dispatch"
            with cls._log_lock:
                dispatch_dir.mkdir(parents=True, exist_ok=True)
            shell = subprocess.Popen(
                [
                    powershell_exe,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    bootstrap,
                ],
                cwd=str(bootstrap_dir.resolve()),
                stdin=None,
                stdout=None,
                stderr=None,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=create_new_console,
            )
            cls._visible_shell_process = shell
            cls._visible_shell_dispatch_dir = dispatch_dir.resolve()
            return shell

    def _prepare_done_file(self, target_dir: Path) -> Path:
        logs_dir = self._runtime_root()
        with self._log_lock:
            logs_dir.mkdir(parents=True, exist_ok=True)
        filename = f"done_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.txt"
        done_file = logs_dir / filename
        done_file.write_text("", encoding="utf-8")
        return done_file

    @staticmethod
    def _read_done_code(done_file: Path) -> int:
        try:
            raw = (done_file.read_text(encoding="utf-8-sig", errors="replace") or "").strip()
            return int(raw or "1")
        except Exception:
            return 1

    _dispatch_lock = threading.Lock()

    def _write_visible_dispatch_script(
        self,
        *,
        command: str,
        target_dir: Path,
        done_file: Path,
        capture_file: Path,
    ) -> Path:
        quoted_dir = self._escape_ps_single_quoted(str(target_dir))
        quoted_done = self._escape_ps_single_quoted(str(done_file))
        quoted_cap = self._escape_ps_single_quoted(str(capture_file.resolve()))
        unique_id = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        dispatch_dir = self._runtime_root() / f"dispatch_{unique_id}"
        with self._log_lock:
            dispatch_dir.mkdir(parents=True, exist_ok=True)
        dispatch_file = dispatch_dir / "dispatch.ps1"
        use_script_file = len(command) > self.DIRECT_VISIBLE_COMMAND_MAX_LENGTH or "\x00" in command
        ps_exe = self._resolve_classic_powershell_exe()
        quoted_ps = self._escape_ps_single_quoted(ps_exe)
        if use_script_file:
            fragment_file = dispatch_dir / "cmd.ps1"
            fragment_file.write_text(command, encoding="utf-8")
        else:
            fragment_file = dispatch_dir / "fragment.ps1"
            expanded = self._ensure_wide_dir_output(str(command).rstrip())
            fragment_file.write_text(expanded + "\n", encoding="utf-8-sig")
        quoted_frag = self._escape_ps_single_quoted(str(fragment_file.resolve()))
        quoted_cmd_echo = self._visible_shell_command_echo_literal(command)
        ps_lines = [
            "$ErrorActionPreference = 'Continue'",
            f"Set-Location -LiteralPath '{quoted_dir}'",
            f"$done = '{quoted_done}'",
            f"$cap = '{quoted_cap}'",
            f"$NonoClawCmdEcho = '{quoted_cmd_echo}'",
            "if (Test-Path -LiteralPath $done) { Remove-Item -LiteralPath $done -Force -ErrorAction SilentlyContinue }",
            "if (Test-Path -LiteralPath $cap) { Remove-Item -LiteralPath $cap -Force -ErrorAction SilentlyContinue }",
            f"$psExe = '{quoted_ps}'",
            f"$frag = '{quoted_frag}'",
            "try {",
            "  Write-Host ''",
            "  Write-Host ('PS ' + (Get-Location).Path + '> ' + $NonoClawCmdEcho) -ForegroundColor DarkCyan",
            "  Write-Host '(子进程输出实时显示；命令未结束前工具会一直等待)' -ForegroundColor DarkGray",
            "  $transcriptPath = $cap + '.transcript'",
            "  Start-Transcript -Path $transcriptPath -Append -Force | Out-Null",
            "  & $psExe -ExecutionPolicy Bypass -File $frag 2>&1 | ForEach-Object { Write-Host $_ }",
            "  Stop-Transcript | Out-Null",
            "  if ($null -eq $LASTEXITCODE) { $code = 1 }",
            "  else {",
            "    try { $code = [int]$LASTEXITCODE } catch { $code = 1 }",
            "  }",
            "  if (Test-Path -LiteralPath $transcriptPath) {",
            "    Get-Content -LiteralPath $transcriptPath -Raw -Encoding utf8 | Set-Content -LiteralPath $cap -Encoding utf8 -Force",
            "    Remove-Item -LiteralPath $transcriptPath -Force -ErrorAction SilentlyContinue",
            "  } else {",
            "    Set-Content -LiteralPath $cap -Value '' -Encoding utf8; Write-Host '(no console output)' -ForegroundColor DarkGray",
            "  }",
            "} catch {",
            "  Write-Host ''",
            "  Write-Host ('PS ' + (Get-Location).Path + '> ' + $NonoClawCmdEcho) -ForegroundColor DarkCyan",
            "  ($_ | Out-String) | Write-Host",
            "  $code = 1",
            "  try { Set-Content -LiteralPath $cap -Value (($_ | Out-String)) -Encoding utf8 -Force } catch {}",
            "}",
            "Set-Content -LiteralPath $done -Value $code -Encoding utf8",
            f"Remove-Item -LiteralPath '{quoted_frag}' -Force -ErrorAction SilentlyContinue",
        ]
        dispatch_file.write_text("\n".join(ps_lines) + "\n", encoding="utf-8-sig")
        return dispatch_file

    @classmethod
    def _done_file_key(cls, done_file: Path) -> str:
        return str(done_file.resolve())

    @classmethod
    def _force_complete_done_file(cls, done_file: Path, return_code: int = -1) -> None:
        try:
            if not done_file.exists() or done_file.stat().st_size == 0:
                done_file.write_text(str(return_code), encoding="utf-8")
        except Exception:
            pass

    @classmethod
    def _kill_pid_tree(cls, pid: int, *, force: bool = True) -> None:
        if not pid or os.name != "nt":
            return
        try:
            cmd = ["taskkill", "/PID", str(pid), "/T"]
            if force:
                cmd.append("/F")
            subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
        except Exception:
            pass

    @classmethod
    def _register_visible_poll(
        cls,
        done_file: Path,
        *,
        capture_file: Path,
        pids: list[int] | None = None,
    ) -> None:
        with cls._visible_shell_lock:
            cls._active_visible_polls[cls._done_file_key(done_file)] = {
                "done_file": done_file,
                "capture_file": capture_file,
                "pids": [int(p) for p in (pids or []) if p],
                "interrupted_action": None,
            }

    @classmethod
    def _unregister_visible_poll(cls, done_file: Path) -> None:
        with cls._visible_shell_lock:
            cls._active_visible_polls.pop(cls._done_file_key(done_file), None)
            if not cls._active_visible_polls:
                cls._cancel_all_event.clear()

    @classmethod
    def _update_visible_poll_pids(cls, done_file: Path, pids: list[int]) -> None:
        with cls._visible_shell_lock:
            poll = cls._active_visible_polls.get(cls._done_file_key(done_file))
            if poll is not None:
                poll["pids"] = [int(p) for p in pids if p]

    @classmethod
    def _mark_visible_poll_interrupted(cls, done_file: Path, action: str) -> None:
        with cls._visible_shell_lock:
            poll = cls._active_visible_polls.get(cls._done_file_key(done_file))
            if poll is not None:
                poll["interrupted_action"] = action

    @classmethod
    def _visible_poll_interrupted_action(cls, done_file: Path) -> str | None:
        with cls._visible_shell_lock:
            poll = cls._active_visible_polls.get(cls._done_file_key(done_file))
            if poll is None:
                return None
            action = poll.get("interrupted_action")
            return str(action) if action else None

    @classmethod
    def _force_unblock_visible_polls(cls, action: str = "terminate") -> None:
        with cls._visible_shell_lock:
            polls = list(cls._active_visible_polls.values())
        for poll in polls:
            done_file = poll["done_file"]
            cls._mark_visible_poll_interrupted(done_file, action)
            cls._force_complete_done_file(done_file)
            for pid in poll.get("pids") or []:
                cls._kill_pid_tree(int(pid))

    @classmethod
    def _abort_visible_poll(
        cls,
        done_file: Path,
        *,
        action: str,
        pids: list[int] | None = None,
    ) -> None:
        cls._mark_visible_poll_interrupted(done_file, action)
        cls._force_complete_done_file(done_file)
        kill_pids = list(pids or [])
        with cls._visible_shell_lock:
            poll = cls._active_visible_polls.get(cls._done_file_key(done_file))
            if poll is not None:
                kill_pids.extend(int(p) for p in poll.get("pids") or [])
        for pid in dict.fromkeys(kill_pids):
            cls._kill_pid_tree(pid)

    def _poll_visible_command_result(
        self,
        *,
        done_file: Path,
        capture_file: Path,
        timeout: int,
        invocation_id: str | None = None,
        extra_pids: list[int] | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        capture_snapshot = ""
        ready_detected_since: float | None = None
        while True:
            if self._cancel_all_event.is_set():
                self._abort_visible_poll(
                    done_file,
                    action="terminate",
                    pids=extra_pids,
                )
                if capture_file.exists():
                    capture_snapshot = capture_file.read_text(encoding="utf-8", errors="replace")
                return {
                    "stdout": capture_snapshot,
                    "return_code": -1,
                    "timed_out": False,
                    "auto_detached": False,
                    "interrupted_action": "terminate",
                }
            if invocation_id:
                pending_action = self._consume_interrupt_action(invocation_id)
                if pending_action:
                    self._abort_visible_poll(
                        done_file,
                        action=pending_action,
                        pids=extra_pids,
                    )
                    if capture_file.exists():
                        capture_snapshot = capture_file.read_text(encoding="utf-8", errors="replace")
                    return {
                        "stdout": capture_snapshot,
                        "return_code": -1,
                        "timed_out": False,
                        "auto_detached": pending_action == "skip",
                        "interrupted_action": pending_action,
                    }
            if done_file.exists() and done_file.stat().st_size > 0:
                return_code = self._read_done_code(done_file)
                captured = ""
                if capture_file.exists():
                    captured = capture_file.read_text(encoding="utf-8", errors="replace")
                interrupted_action = self._visible_poll_interrupted_action(done_file)
                return {
                    "stdout": captured,
                    "return_code": return_code,
                    "timed_out": False,
                    "auto_detached": False,
                    "interrupted_action": interrupted_action,
                }
            if capture_file.exists():
                current_capture = capture_file.read_text(encoding="utf-8", errors="replace")
                if current_capture != capture_snapshot:
                    capture_snapshot = current_capture
                    ready_detected_since = None
                else:
                    if ready_detected_since is None:
                        ready_detected_since = time.monotonic()
                    elif time.monotonic() - ready_detected_since >= self.AUTO_DETACH_STABLE_SECONDS:
                        for pattern in self.AUTO_DETACH_READY_PATTERNS:
                            if re.search(pattern, current_capture, re.IGNORECASE):
                                return {
                                    "stdout": current_capture,
                                    "return_code": 0,
                                    "timed_out": False,
                                    "auto_detached": True,
                                }
            if time.monotonic() >= deadline:
                return {
                    "stdout": capture_snapshot,
                    "return_code": -1,
                    "timed_out": True,
                    "auto_detached": False,
                }
            time.sleep(0.3)

    def _dispatch_visible_command(
        self,
        shell: subprocess.Popen[str],
        *,
        command: str,
        target_dir: Path,
        done_file: Path,
        capture_file: Path,
    ) -> None:
        if shell.poll() is not None:
            raise RuntimeError("Shared PowerShell exited unexpectedly")
        dispatch_file = self._write_visible_dispatch_script(
            command=command,
            target_dir=target_dir,
            done_file=done_file,
            capture_file=capture_file,
        )
        quoted_dispatch = self._escape_ps_single_quoted(str(dispatch_file.resolve()))
        unique_id = dispatch_file.parent.name.replace("dispatch_", "", 1)
        with self._dispatch_lock:
            job_dispatch_dir = CLIExecutor._visible_shell_dispatch_dir
            if job_dispatch_dir is None:
                raise RuntimeError("Shared PowerShell dispatch directory is not initialized")
            job_file = job_dispatch_dir / f"job_{unique_id}.ps1"
            temp_job = job_file.with_suffix(".tmp")
            temp_job.write_text(f"& '{quoted_dispatch}'\n", encoding="utf-8-sig")
            temp_job.replace(job_file)

    def _launch_visible_dispatch_window(
        self,
        *,
        dispatch_file: Path,
        target_dir: Path,
    ) -> int:
        powershell_exe = self._resolve_classic_powershell_exe()
        quoted_powershell = self._escape_ps_single_quoted(powershell_exe)
        quoted_dir = self._escape_ps_single_quoted(str(target_dir))
        quoted_dispatch = self._escape_ps_single_quoted(str(dispatch_file.resolve()))
        start_process_command = (
            f"$ps='{quoted_powershell}'; "
            "if (Test-Path $ps) { "
            "Start-Process "
            "-FilePath $ps "
            f"-WorkingDirectory '{quoted_dir}' "
            "-ArgumentList @("
            "'-NoProfile','-ExecutionPolicy','Bypass','-File',"
            f"'{quoted_dispatch}'"
            ") "
            "-PassThru | Select-Object -ExpandProperty Id "
            "} else { throw 'PowerShell executable not found' }"
        )
        fallback = subprocess.run(
            [
                powershell_exe,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                start_process_command,
            ],
            cwd=str(target_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
        pid_text = (fallback.stdout or "").strip().splitlines()
        if fallback.returncode == 0 and pid_text:
            return int(pid_text[-1].strip())
        raise RuntimeError(
            f"Unable to launch visible PowerShell window: "
            f"code={fallback.returncode}, stderr={(fallback.stderr or '').strip()}"
        )

    def _execute_in_new_visible_powershell(
        self,
        *,
        command: str,
        target_dir: Path,
        timeout: int,
        invocation_id: str | None = None,
    ) -> dict[str, Any]:
        done_file = self._prepare_done_file(target_dir)
        capture_file = done_file.with_name(f"{done_file.stem}.capture.log")
        dispatch_file = self._write_visible_dispatch_script(
            command=command,
            target_dir=target_dir,
            done_file=done_file,
            capture_file=capture_file,
        )
        console_pid = self._launch_visible_dispatch_window(
            dispatch_file=dispatch_file,
            target_dir=target_dir,
        )
        self._register_visible_poll(
            done_file,
            capture_file=capture_file,
            pids=[console_pid],
        )
        try:
            poll_result = self._poll_visible_command_result(
                done_file=done_file,
                capture_file=capture_file,
                timeout=timeout,
                invocation_id=invocation_id,
                extra_pids=[console_pid],
            )
            return {
                "pid": console_pid,
                "process": None,
                **poll_result,
            }
        finally:
            self._unregister_visible_poll(done_file)

    def _launch_dedicated_visible_console(
        self,
        *,
        command: str,
        target_dir: Path,
    ) -> dict[str, Any]:
        logs_dir = target_dir / ".NonoClaw_cli_logs"
        with self._log_lock:
            logs_dir.mkdir(parents=True, exist_ok=True)
        stamp = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        command_script = logs_dir / f"interactive_{stamp}.ps1"
        quoted_dir = self._escape_ps_single_quoted(str(target_dir))
        powershell_exe = self._resolve_classic_powershell_exe()
        create_new_console = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        launch_errors: list[str] = []
        use_script_file = len(command) > self.DIRECT_VISIBLE_COMMAND_MAX_LENGTH or "\n" in command or "\x00" in command
        if use_script_file:
            command_script.write_text(command, encoding="utf-8")
            powershell_args = [
                "-ExecutionPolicy",
                "Bypass",
                "-NoExit",
                "-File",
                str(command_script),
            ]
        else:
            powershell_args = [
                "-NoExit",
                "-Command",
                command,
            ]
        quoted_powershell = self._escape_ps_single_quoted(powershell_exe)
        start_process_command = (
            f"$ps='{quoted_powershell}'; "
            "if (Test-Path $ps) { "
            "Start-Process "
            "-FilePath $ps "
            f"-WorkingDirectory '{quoted_dir}' "
            "-ArgumentList @("
            + ",".join(f"'{self._escape_ps_single_quoted(arg)}'" for arg in powershell_args) +
            ") "
            "-PassThru | Select-Object -ExpandProperty Id "
            "} else { throw 'PowerShell executable not found' }"
        )
        try:
            fallback = subprocess.run(
                [
                    powershell_exe,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    start_process_command,
                ],
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
            pid_text = (fallback.stdout or "").strip().splitlines()
            if fallback.returncode == 0 and pid_text:
                launched_pid = int(pid_text[-1].strip())
                return {
                    "pid": launched_pid,
                    "launcher_script": "",
                    "command_script": str(command_script) if use_script_file else "",
                    "used_windows_terminal": False,
                }
            launch_errors.append(
                f"start-process fallback failed: code={fallback.returncode}, stderr={(fallback.stderr or '').strip()}"
            )
        except Exception as exc:
            launch_errors.append(f"start-process fallback exception: {exc}")
        raise RuntimeError(" ; ".join(launch_errors) or "Unable to launch visible PowerShell window")

    def _execute_in_shared_visible_powershell(
        self,
        *,
        command: str,
        target_dir: Path,
        timeout: int,
        invocation_id: str | None = None,
    ) -> dict[str, Any]:
        done_file = self._prepare_done_file(target_dir)
        capture_file = done_file.with_name(f"{done_file.stem}.capture.log")
        self._register_visible_poll(
            done_file,
            capture_file=capture_file,
            pids=[],
        )
        try:
            with self._visible_shell_command_lock:
                shell = self._ensure_shared_visible_shell(self._allowed_dir.resolve())
                if shell.pid:
                    self._update_visible_poll_pids(done_file, [int(shell.pid)])
                self._dispatch_visible_command(
                    shell,
                    command=command,
                    target_dir=target_dir,
                    done_file=done_file,
                    capture_file=capture_file,
                )
            poll_result = self._poll_visible_command_result(
                done_file=done_file,
                capture_file=capture_file,
                timeout=timeout,
                invocation_id=invocation_id,
                extra_pids=[int(shell.pid)] if shell.pid else None,
            )
            return {
                "process": shell,
                **poll_result,
            }
        finally:
            self._unregister_visible_poll(done_file)

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
                            "description": "超时时间（秒）。建议按任务复杂度设置：简单命令 30s，pip install 等网络操作 120s+；默认 300。",
                            "default": 300,
                        },
                        "visible_terminal_mode": {
                            "type": "string",
                            "description": (
                                "可见终端模式（仅 Windows）。shared=复用同一窗口，等待结束并捕获输出；"
                                "该窗口由脚本循环驱动并另起子进程执行每条命令，不是完整的交互式 PSReadLine 会话，因此外观可能与手动打开的 PowerShell/Windows Terminal 不同。"
                                "new=每次新开独立窗口，等待结束并捕获输出（stdout/stderr 会写入工具返回结果）。"
                            ),
                            "enum": ["shared", "new"],
                            "default": "shared",
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
        visible_terminal_mode: str = "shared",
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
        # 越界检查：工作目录超出允许范围也判定为危险
        is_oob = self._is_working_dir_outside_allowed(working_dir)

        # 黑白名单权限检查（优先于危险检查）
        from db.path_permissions import check_path_permission
        perm_result = check_path_permission(str(target_dir))
        if perm_result:
            if perm_result.get("allowed"):
                # 白名单命中，跳过所有危险检查直接放行
                danger_check = None
                is_oob = False
            else:
                # 黑名单命中，直接拒绝
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

        # 未命中黑白名单，继续原有的危险/越界检查流程
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
        use_visible_powershell = os.name == "nt"
        mode_normalized = str(visible_terminal_mode or "shared").strip().lower()
        if mode_normalized not in {"shared", "new"}:
            mode_normalized = "shared"
        if use_visible_powershell:
            if mode_normalized == "shared":
                try:
                    shared_result = self._execute_in_shared_visible_powershell(
                        command=normalized_command,
                        target_dir=target_dir,
                        timeout=timeout,
                        invocation_id=invocation_id,
                    )
                except Exception as exc:
                    return {
                        "success": False,
                        "error": str(exc),
                        "output": (
                            f"共享 PowerShell 执行失败\n命令: {normalized_command}\n"
                            f"执行目录: {target_dir}\n异常: {exc}"
                        ),
                        "command": normalized_command,
                        "working_dir": str(target_dir),
                        "requires_confirmation": False,
                    }
                proc = shared_result.get("process")
                shared_pid = int(proc.pid) if proc is not None else None
                interrupted_action = shared_result.get("interrupted_action")
                auto_detached = bool(shared_result.get("auto_detached"))
                if auto_detached:
                    output_lines = [
                        "检测到命令已进入长期运行状态，已自动结束本次等待",
                        f"命令: {normalized_command}",
                        f"执行目录: {target_dir}",
                        "可见终端模式: shared（共享窗口）",
                        "状态: 已脱离等待，服务继续在该窗口运行",
                    ]
                    if shared_pid is not None:
                        output_lines.append(f"Console PID: {shared_pid}")
                    row: dict[str, Any] = {
                        "success": True,
                        "detached_background": True,
                        "auto_detached": True,
                        "output": "\n".join(output_lines),
                        "command": normalized_command,
                        "working_dir": str(target_dir),
                        "requires_confirmation": False,
                    }
                    if shared_pid is not None:
                        row["pid"] = shared_pid
                    return row
                if interrupted_action:
                    action_label = "跳过等待" if interrupted_action == "skip" else "结束"
                    output_lines = [
                        f"命令已被用户{action_label}",
                        f"命令: {normalized_command}",
                        f"执行目录: {target_dir}",
                        "可见终端模式: shared（共享窗口）",
                    ]
                    if shared_pid is not None:
                        output_lines.append(f"Console PID: {shared_pid}")
                    if interrupted_action == "skip":
                        output_lines.append(
                            "共享窗口内的命令可能仍在运行；已丢弃共享句柄，"
                            "下一次 shared 调用会按需新开窗口。"
                        )
                    row = {
                        "success": False,
                        "interrupted": True,
                        "interrupted_action": interrupted_action,
                        "detached_background": interrupted_action == "skip",
                        "error": f"Command {action_label} by user",
                        "output": "\n".join(output_lines),
                        "command": normalized_command,
                        "working_dir": str(target_dir),
                        "requires_confirmation": False,
                    }
                    if shared_pid is not None:
                        row["pid"] = shared_pid
                    return row
                if shared_result.get("timed_out"):
                    row = {
                        "success": False,
                        "error": f"Command timed out after {timeout} seconds",
                        "output": (
                            f"命令执行超时（共享 PowerShell）\n命令: {normalized_command}\n"
                            f"执行目录: {target_dir}\n超时时间: {timeout} 秒"
                        ),
                        "command": normalized_command,
                        "working_dir": str(target_dir),
                        "requires_confirmation": False,
                    }
                    if shared_pid is not None:
                        row["pid"] = shared_pid
                    return row
                return_code = int(shared_result.get("return_code") or 0)
                captured = str(shared_result.get("stdout") or "").strip()
                output_lines = [
                    "CLI command executed in the shared visible PowerShell window.",
                    f"Command: {normalized_command}",
                    f"Working directory: {target_dir}",
                    "Visible terminal mode: shared",
                    f"Return code: {return_code}",
                ]
                if shared_pid is not None:
                    output_lines.append(f"Shared console PID: {shared_pid}")
                output_lines.append("Captured stdout/stderr (mirrored to the same window):")
                if captured:
                    output_lines.append(self._truncate_output(captured))
                else:
                    output_lines.append("(empty)")
                out: dict[str, Any] = {
                    "success": return_code == 0,
                    "return_code": return_code,
                    "captured_output": captured,
                    "output": "\n".join(output_lines),
                    "command": normalized_command,
                    "working_dir": str(target_dir),
                    "requires_confirmation": False,
                }
                if shared_pid is not None:
                    out["pid"] = shared_pid
                return out
            try:
                new_result = self._execute_in_new_visible_powershell(
                    command=normalized_command,
                    target_dir=target_dir,
                    timeout=timeout,
                    invocation_id=invocation_id,
                )
            except Exception as exc:
                return {
                    "success": False,
                    "error": str(exc),
                    "output": (
                        f"独立 PowerShell 窗口执行失败\n命令: {normalized_command}\n"
                        f"执行目录: {target_dir}\n异常: {exc}"
                    ),
                    "command": normalized_command,
                    "working_dir": str(target_dir),
                    "requires_confirmation": False,
                }
            console_pid = new_result.get("pid")
            interrupted_action = new_result.get("interrupted_action")
            auto_detached = bool(new_result.get("auto_detached"))
            if interrupted_action:
                action_label = "跳过等待" if interrupted_action == "skip" else "结束"
                output_lines = [
                    f"命令已被用户{action_label}",
                    f"命令: {normalized_command}",
                    f"执行目录: {target_dir}",
                    "可见终端模式: new（独立窗口）",
                ]
                if console_pid is not None:
                    output_lines.append(f"Console PID: {console_pid}")
                row = {
                    "success": False,
                    "interrupted": True,
                    "interrupted_action": interrupted_action,
                    "detached_background": interrupted_action == "skip",
                    "error": f"Command {action_label} by user",
                    "output": "\n".join(output_lines),
                    "command": normalized_command,
                    "working_dir": str(target_dir),
                    "requires_confirmation": False,
                }
                if console_pid is not None:
                    row["pid"] = int(console_pid)
                return row
            if auto_detached:
                output_lines = [
                    "检测到命令已进入长期运行状态，已自动结束本次等待",
                    f"命令: {normalized_command}",
                    f"执行目录: {target_dir}",
                    "可见终端模式: new（独立窗口）",
                    "状态: 已脱离等待，服务继续在该窗口运行",
                ]
                if console_pid is not None:
                    output_lines.append(f"Console PID: {console_pid}")
                row = {
                    "success": True,
                    "detached_background": True,
                    "auto_detached": True,
                    "output": "\n".join(output_lines),
                    "command": normalized_command,
                    "working_dir": str(target_dir),
                    "requires_confirmation": False,
                }
                if console_pid is not None:
                    row["pid"] = int(console_pid)
                return row
            if new_result.get("timed_out"):
                row = {
                    "success": False,
                    "error": f"Command timed out after {timeout} seconds",
                    "output": (
                        f"命令执行超时（独立 PowerShell 窗口）\n命令: {normalized_command}\n"
                        f"执行目录: {target_dir}\n超时时间: {timeout} 秒"
                    ),
                    "command": normalized_command,
                    "working_dir": str(target_dir),
                    "requires_confirmation": False,
                }
                if console_pid is not None:
                    row["pid"] = int(console_pid)
                return row
            return_code = int(new_result.get("return_code") or 0)
            captured = str(new_result.get("stdout") or "").strip()
            output_lines = [
                "CLI command executed in a new visible PowerShell window.",
                f"Command: {normalized_command}",
                f"Working directory: {target_dir}",
                "Visible terminal mode: new",
                f"Return code: {return_code}",
            ]
            if console_pid is not None:
                output_lines.append(f"Console PID: {console_pid}")
            output_lines.append("Captured stdout/stderr (mirrored to the same window):")
            if captured:
                output_lines.append(self._truncate_output(captured))
            else:
                output_lines.append("(empty)")
            out = {
                "success": return_code == 0,
                "return_code": return_code,
                "captured_output": captured,
                "output": "\n".join(output_lines),
                "command": normalized_command,
                "working_dir": str(target_dir),
                "requires_confirmation": False,
            }
            if console_pid is not None:
                out["pid"] = int(console_pid)
            return out
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
                        self._terminate_process(process, force=pending_action == "terminate")
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
        if interrupted_action:
            action_label = "跳过等待" if interrupted_action == "skip" else "结束"
            output_lines = [
                f"命令已被用户{action_label}",
                f"命令: {normalized_command}",
                f"执行目录: {target_dir}",
            ]
            if interrupted_action == "skip":
                output_lines.append("后台 PowerShell 会继续执行该命令；当前前台等待已脱离。")
            return {
                "success": False,
                "interrupted": True,
                "interrupted_action": interrupted_action,
                "detached_background": interrupted_action == "skip",
                "error": f"Command {action_label} by user",
                "output": "\n".join(output_lines),
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
        with cls._visible_shell_lock:
            cls._active_processes[invocation_id] = process
            cls._interrupt_actions.pop(invocation_id, None)

    @classmethod
    def _unregister_process(cls, invocation_id: str) -> None:
        with cls._visible_shell_lock:
            cls._active_processes.pop(invocation_id, None)
            cls._interrupt_actions.pop(invocation_id, None)

    @classmethod
    def _consume_interrupt_action(cls, invocation_id: str) -> str | None:
        with cls._visible_shell_lock:
            return cls._interrupt_actions.pop(invocation_id, None)

    @classmethod
    def set_interrupt_action(cls, invocation_id: str, action: str) -> None:
        """公开 API：外部（agent_mode 收到 cancel_event）设置某个 invocation 的中断动作。

        action 取值：
        - "terminate": 立即强制结束进程（taskkill /T /F）
        - "skip": 跳过等待（共享 PowerShell 模式下让命令在后台继续）
        """
        if not invocation_id or not action:
            return
        with cls._visible_shell_lock:
            cls._interrupt_actions[invocation_id] = action

    @classmethod
    def terminate_all_active(cls, action: str = "terminate") -> list[int]:
        """终止所有正在运行的子进程（外部取消/退出时调用）。

        返回被终止的 pid 列表。
        """
        terminated: list[int] = []
        cls._cancel_all_event.set()
        cls._force_unblock_visible_polls(action)
        with cls._visible_shell_lock:
            shell = cls._visible_shell_process
            if shell is not None and shell.poll() is None:
                try:
                    pid = int(shell.pid)
                    cls._terminate_process(shell, force=(action == "terminate"))
                    terminated.append(pid)
                except Exception:
                    pass
            cls._visible_shell_process = None
            cls._visible_shell_dispatch_dir = None
            for inv_id in list(cls._active_processes.keys()):
                cls._interrupt_actions[inv_id] = action
            targets = list(cls._active_processes.items())
        for inv_id, process in targets:
            with cls._visible_shell_lock:
                cls._interrupt_actions[inv_id] = action
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
        """返回当前所有活动 invocation_id，用于外部清理时引用。"""
        with cls._visible_shell_lock:
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
