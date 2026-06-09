"""Embedded PTY terminal manager for CLI execution and interactive console."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

OutputCallback = Callable[[str], None]
logger = logging.getLogger(__name__)

AUTO_DETACH_READY_PATTERNS = (
    r"http://localhost:\d+/?",
    r"https://localhost:\d+/?",
    r"\bvite\b.*\bready\b",
    r"\bready in\b",
    r"\bpress h \+ enter to show help\b",
    r"\blocal:\s+http://",
)
AUTO_DETACH_STABLE_SECONDS = 1.5
INTERACTIVE_PROMPT_PATTERNS = (
    r"\(y/n\)",
    r"\[Y/n\]",
    r"\[y/N\]",
    r"continue\?",
    r"proceed\?",
)
# cmd.exe echoes these when xterm sends device-attribute queries; they break the cursor.
_NOISE_OUTPUT_RE = re.compile(
    r"\x1b\[\?1;2c"
    r"|\x1b\[>0;[0-9;]*c"
    r"|\x1b\[\?62;[0-9;]*c"
    r"|\x1b\[c"
)
_MAX_OUTPUT_BUFFER_CHARS = 256_000


def _sanitize_terminal_output(data: str) -> str:
    if not data:
        return data
    return _NOISE_OUTPUT_RE.sub("", data)


class _TerminalSession:
    def __init__(self, work_dir: str) -> None:
        self.work_dir = str(Path(work_dir).expanduser().resolve())
        self.lock = threading.Lock()
        self._pty: Any = None
        self._alive = False
        self._rows = 30
        self._cols = 120
        self._output_buffer = ""
        self._callbacks: list[OutputCallback] = []

    def is_running(self) -> bool:
        if not self._alive or self._pty is None:
            return False
        try:
            if os.name == "nt":
                return bool(self._pty.isalive())
            return self._pty.poll() is None
        except Exception:
            return False

    def clear_output_buffer(self) -> None:
        with self.lock:
            self._output_buffer = ""

    @staticmethod
    def _interactive_shell_argv() -> list[str]:
        """交互式 Console 默认 PowerShell；winpty 必须用 argv 列表启动。"""
        if os.name != "nt":
            return [os.environ.get("SHELL", "/bin/bash")]
        override = (os.environ.get("MIMOCLAW_CONSOLE_SHELL") or "").strip()
        if override:
            return shlex.split(override, posix=False)
        if shutil.which("pwsh"):
            return ["pwsh.exe", "-NoLogo", "-NoExit"]
        if shutil.which("powershell"):
            return ["powershell.exe", "-NoLogo", "-NoExit"]
        return [os.environ.get("COMSPEC", "cmd.exe")]

    @property
    def shell_kind(self) -> str:
        if os.name != "nt":
            return "unix"
        exe = (self._interactive_shell_argv()[0] or "").lower()
        if "powershell" in exe or exe.endswith("pwsh.exe"):
            return "powershell"
        return "cmd"

    def _spawn_shell(self, rows: int = 30, cols: int = 120, *, clear_buffer: bool = True) -> None:
        self._rows = max(1, rows)
        self._cols = max(20, cols)
        if clear_buffer:
            self._output_buffer = ""
        if os.name == "nt":
            from winpty import PtyProcess

            argv = self._interactive_shell_argv()
            logger.info("Spawning interactive shell argv=%s cwd=%s", argv, self.work_dir)
            self._pty = PtyProcess.spawn(
                argv,
                cwd=self.work_dir,
                dimensions=(self._rows, self._cols),
            )
        else:
            import pty
            import subprocess

            master, slave = pty.openpty()
            shell = os.environ.get("SHELL", "/bin/bash")
            self._pty = subprocess.Popen(
                [shell],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=self.work_dir,
                text=False,
            )
            self._master_fd = master
            os.close(slave)
        self._alive = True
        threading.Thread(target=self._reader_loop, daemon=True, name=f"pty-{self.work_dir}").start()

    def ensure_shell_ready(self, rows: int = 30, cols: int = 120) -> None:
        """PTY 异常退出后重启 shell，避免后续 write 写入死进程。"""
        if self.is_running():
            return
        with self.lock:
            self._alive = False
            try:
                if os.name == "nt" and self._pty:
                    self._pty.close(force=True)
                elif self._pty:
                    self._pty.terminate()
            except Exception:
                pass
            self._pty = None
        time.sleep(0.05)
        self._spawn_shell(rows=rows, cols=cols, clear_buffer=True)

    def _kill_pty_process(self, force: bool = True) -> None:
        if not self._pty:
            return
        try:
            if os.name == "nt":
                try:
                    self._pty.write("\x03")
                    time.sleep(0.08)
                except Exception:
                    pass
                self._pty.close(force=force)
            else:
                if force:
                    self._pty.kill()
                else:
                    self._pty.terminate()
        except Exception:
            pass

    def restart_shell(self, rows: int = 30, cols: int = 120) -> None:
        with self.lock:
            self._alive = False
            self._output_buffer = ""
            self._kill_pty_process(force=True)
            self._pty = None
        time.sleep(0.05)
        self._spawn_shell(rows=rows, cols=cols, clear_buffer=False)

    def force_reset(self, rows: int = 30, cols: int = 120) -> None:
        """超时或卡死时强制结束 PTY 内残留进程并重建 shell。"""
        self.restart_shell(rows=rows, cols=cols)

    def _reader_loop(self) -> None:
        while self._alive and self._pty is not None:
            try:
                if os.name == "nt":
                    if not self._pty.isalive():
                        self._alive = False
                        break
                    chunk = self._pty.read(4096)
                    if not chunk:
                        time.sleep(0.05)
                        continue
                else:
                    import select

                    ready, _, _ = select.select([self._master_fd], [], [], 0.1)
                    if not ready:
                        if self._pty.poll() is not None:
                            self._alive = False
                            break
                        continue
                    chunk = os.read(self._master_fd, 4096).decode("utf-8", errors="replace")
                self._emit(chunk)
            except Exception:
                self._alive = False
                time.sleep(0.1)

    def _emit(self, data: str) -> None:
        if not data:
            return
        data = _sanitize_terminal_output(data)
        if not data:
            return
        with self.lock:
            self._output_buffer += data
            if len(self._output_buffer) > _MAX_OUTPUT_BUFFER_CHARS:
                self._output_buffer = self._output_buffer[-_MAX_OUTPUT_BUFFER_CHARS // 2 :]
            callbacks = list(self._callbacks)
        for cb in callbacks:
            try:
                cb(data)
            except Exception:
                pass

    def subscribe(self, callback: OutputCallback) -> None:
        with self.lock:
            self._callbacks.append(callback)

    def unsubscribe(self, callback: OutputCallback) -> None:
        with self.lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def write(self, data: str) -> None:
        self.ensure_shell_ready(self._rows, self._cols)
        if not self._pty or not self._alive:
            return
        try:
            if os.name == "nt":
                self._pty.write(data)
            else:
                os.write(self._master_fd, data.encode("utf-8", errors="replace"))
        except Exception:
            self.force_reset(self._rows, self._cols)
            if not self._pty or not self._alive:
                return
            try:
                if os.name == "nt":
                    self._pty.write(data)
                else:
                    os.write(self._master_fd, data.encode("utf-8", errors="replace"))
            except Exception:
                pass

    def resize(self, rows: int, cols: int) -> None:
        self._rows = max(1, rows)
        self._cols = max(20, cols)
        if os.name == "nt" and self._pty:
            try:
                self._pty.setwinsize(self._rows, self._cols)
            except Exception:
                pass

    def get_replay_buffer(self) -> str:
        with self.lock:
            return _sanitize_terminal_output(self._output_buffer)

    def close(self) -> None:
        self._alive = False
        try:
            if os.name == "nt" and self._pty:
                self._pty.close(force=True)
            elif self._pty:
                self._pty.terminate()
        except Exception:
            pass


class TerminalManager:
    _instance: TerminalManager | None = None
    _lock = threading.Lock()
    _interrupt_actions: dict[str, str] = {}
    _interrupt_lock = threading.Lock()

    def __init__(self) -> None:
        self._sessions: dict[str, _TerminalSession] = {}
        self._session_lock = threading.Lock()
        self._async_subscribers: dict[str, list[asyncio.Queue[str]]] = defaultdict(list)
        self._ws_callbacks: dict[str, OutputCallback] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def get_instance(cls) -> TerminalManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = TerminalManager()
            return cls._instance

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _normalize_work_dir(self, work_dir: str | None) -> str:
        if work_dir and work_dir.strip():
            return str(Path(work_dir).expanduser().resolve())
        return str(Path.home() / ".MIMOClaw")

    def get_session(self, session_id: str, work_dir: str | None = None) -> _TerminalSession:
        with self._session_lock:
            if session_id not in self._sessions:
                wd = self._normalize_work_dir(work_dir)
                self._sessions[session_id] = _TerminalSession(wd)
            return self._sessions[session_id]

    def get_agent_session(self, work_dir: str | None = None) -> _TerminalSession:
        return self.get_session(self.resolve_agent_session_id(work_dir), work_dir)

    def resolve_agent_session_id(self, work_dir: str | None = None) -> str:
        """公开给前端调用：返回 agent 在指定 work_dir 下使用的 session id。

        前端用 `__agent__` 占位订阅时，WebSocket 处理器会调用此方法解析出真实 sid，
        保证用户终端与 AI 命令共享同一个 PTY（避免前后端各自 normalize 路径不一致）。
        """
        key = self._normalize_work_dir(work_dir)
        return f"agent:{key}"

    def reset_agent_session(self, work_dir: str | None = None) -> None:
        """手动清理 agent 侧状态（重建遗留 PTY，subprocess 模式无共享状态）。"""
        session = self.get_agent_session(work_dir)
        session.force_reset()

    @staticmethod
    def _launch_detached_command(command: str, work_dir: str) -> dict[str, Any]:
        """new 模式：独立子进程后台运行，不占用 agent 共享 PTY。"""
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=work_dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        return {"pid": proc.pid}

    def attach_interactive(
        self,
        session_id: str,
        work_dir: str | None,
        rows: int,
        cols: int,
        reset: bool = True,
    ) -> _TerminalSession:
        if reset:
            from utils.cli_process_cleanup import cleanup_stale_cli_processes

            cleanup_stale_cli_processes()
        session = self.get_session(session_id, work_dir)
        if reset:
            session.restart_shell(rows=rows, cols=cols)
        elif not session.is_running():
            session._spawn_shell(rows=rows, cols=cols)
        else:
            session.resize(rows, cols)
        return session

    def _broadcast_async(self, session_id: str, data: str) -> None:
        queues = list(self._async_subscribers.get(session_id, []))
        if not self._loop:
            return
        for q in queues:
            self._loop.call_soon_threadsafe(q.put_nowait, data)

    def subscribe_ws(
        self, session_id: str, work_dir: str | None
    ) -> tuple[_TerminalSession, asyncio.Queue[str], OutputCallback]:
        session = self.get_session(session_id, work_dir)
        old_cb = self._ws_callbacks.pop(session_id, None)
        if old_cb:
            session.unsubscribe(old_cb)
        self._async_subscribers[session_id] = []

        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=500)

        def on_output(data: str) -> None:
            self._broadcast_async(session_id, data)

        session.subscribe(on_output)
        self._ws_callbacks[session_id] = on_output
        self._async_subscribers[session_id].append(queue)
        return session, queue, on_output

    def unsubscribe_ws(
        self, session_id: str, queue: asyncio.Queue[str], callback: OutputCallback
    ) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.unsubscribe(callback)
        if self._ws_callbacks.get(session_id) is callback:
            self._ws_callbacks.pop(session_id, None)
        subs = self._async_subscribers.get(session_id, [])
        if queue in subs:
            subs.remove(queue)
        if not subs:
            self._async_subscribers.pop(session_id, None)

    def broadcast_message(self, work_dir: str | None, message: str) -> None:
        prefix = f"\r\n[Agent] {message}\r\n"
        session = self.get_agent_session(work_dir)
        session._emit(prefix)

    @staticmethod
    def _looks_interactive(output: str) -> bool:
        tail = output[-500:] if len(output) > 500 else output
        return any(re.search(p, tail, re.IGNORECASE) for p in INTERACTIVE_PROMPT_PATTERNS)

    @staticmethod
    def _looks_auto_detach(output: str) -> bool:
        return any(re.search(p, output, re.IGNORECASE) for p in AUTO_DETACH_READY_PATTERNS)

    @staticmethod
    def _kill_process_tree(pid: int) -> None:
        """Kill an entire process tree on Windows (taskkill /T /F)."""
        if os.name != "nt":
            return
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            pass

    @staticmethod
    def _run_subprocess_and_wait(command: str, work_dir: str, timeout: int) -> dict[str, Any]:
        """Agent shared 模式：独立子进程执行并捕获输出，避免 PTY 死锁。

        使用 Popen + taskkill /T 替代 subprocess.run，确保超时时杀掉整个进程树，
        避免遗留子进程（如 shell=True 下 cmd.exe → powershell 的子链）。
        """
        captured = ""
        return_code = 0
        timed_out = False
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            stdout, stderr = process.communicate(timeout=max(1, timeout))
            return_code = int(process.returncode or 0)
            stdout = (stdout or "").strip()
            stderr = (stderr or "").strip()
            if stderr:
                captured = f"{stdout}\n[STDERR]\n{stderr}".strip() if stdout else stderr
            else:
                captured = stdout
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            return_code = -1
            partial_out = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
            partial_err = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else ""
            if process is not None:
                # communicate 超时后子进程可能仍在，强制杀整棵树；勿再调用 communicate（会卡住）
                TerminalManager._kill_process_tree(process.pid)
                try:
                    process.kill()
                except Exception:
                    pass
                for stream in (process.stdout, process.stderr):
                    if stream:
                        try:
                            stream.close()
                        except Exception:
                            pass
                try:
                    process.wait(timeout=2)
                except Exception:
                    pass
            if partial_err:
                captured = f"{partial_out}\n[STDERR]\n{partial_err}".strip() if partial_out else partial_err
            else:
                captured = partial_out
        result = {
            "success": return_code == 0 and not timed_out,
            "return_code": return_code,
            "output_capture": captured,
            "auto_detached": False,
            "timed_out": timed_out,
            "interrupted_action": None,
            "working_dir": work_dir,
        }
        if result.get("timed_out"):
            try:
                from utils.cli_process_cleanup import cleanup_stale_cli_processes

                cleanup_stale_cli_processes(force=True)
            except Exception:
                pass
        return result

    @classmethod
    def set_interrupt_action(cls, invocation_id: str, action: str) -> None:
        """注册中断动作（由 CLIExecutor 在取消时调用）。"""
        with cls._interrupt_lock:
            cls._interrupt_actions[invocation_id] = action

    @classmethod
    def consume_interrupt_action(cls, invocation_id: str) -> str | None:
        with cls._interrupt_lock:
            return cls._interrupt_actions.pop(invocation_id, None)

    @staticmethod
    def _run_command_in_agent_pty(
        command: str,
        work_dir: str,
        timeout: int,
        invocation_id: str | None = None,
    ) -> dict[str, Any]:
        """将命令注入 agent PTY 会话（ConsolePanel 可见），通过临时文件捕获输出。

        逻辑：
        1. 检测 agent PTY 是否有 ConsolePanel 订阅者；没有则 fallback 到隐藏子进程
        2. 将用户命令写入临时 .ps1，构建包装脚本用 Tee-Object 同时输出到屏幕和文件
        3. 注入 PTY 并轮询 done 文件等待完成
        4. 超时或用户取消时向 PTY 发送 Ctrl+C
        """
        manager = TerminalManager.get_instance()
        session = manager.get_agent_session(work_dir)

        # 检查是否有 ConsolePanel 连接
        with session.lock:
            has_subscribers = len(session._callbacks) > 0
        if not has_subscribers:
            return TerminalManager._run_subprocess_and_wait(command, work_dir, timeout)

        # 确保 PTY 存活
        session.ensure_shell_ready()
        if not session.is_running():
            return TerminalManager._run_subprocess_and_wait(command, work_dir, timeout)

        uid = uuid.uuid4().hex[:8]
        temp_dir = Path(tempfile.gettempdir()) / "NonoClaw_cli_runtime" / "pty_jobs"
        temp_dir.mkdir(parents=True, exist_ok=True)
        cap_file = temp_dir / f"out_{uid}.txt"
        done_file = temp_dir / f"done_{uid}.txt"
        cmd_ps1 = temp_dir / f"cmd_{uid}.ps1"
        wrapper_ps1 = temp_dir / f"wrap_{uid}.ps1"

        # 清理可能残留的旧文件
        for f in (cap_file, done_file, cmd_ps1, wrapper_ps1):
            f.unlink(missing_ok=True)

        # 将用户命令写入独立 .ps1
        cmd_ps1.write_text(command, encoding="utf-8")

        # 构建包装脚本：执行用户命令，Tee 输出到屏幕+捕获文件，完成后写退出码文件
        cap_path = str(cap_file).replace("'", "''")
        done_path = str(done_file).replace("'", "''")
        cmd_path = str(cmd_ps1).replace("'", "''")
        wrapper_content = (
            f"$ErrorActionPreference = 'Continue'\r\n"
            f"$capFile = '{cap_path}'\r\n"
            f"$doneFile = '{done_path}'\r\n"
            f"try {{\r\n"
            f"    & '{cmd_path}' 2>&1 | Tee-Object -FilePath $capFile\r\n"
            f"    $code = $LASTEXITCODE\r\n"
            f"}} catch {{\r\n"
            f"    $_ | Out-String | Write-Host\r\n"
            f"    $code = 1\r\n"
            f"}}\r\n"
            f"$code | Out-File -FilePath $doneFile -Encoding utf8\r\n"
        )
        wrapper_ps1.write_text(wrapper_content, encoding="utf-8")

        # 发送 ANSI 标记提示 AI 命令开始
        session._emit(
            "\r\n\x1b[33m━━━ AI 命令开始执行 ━━━\x1b[0m\r\n"
        )
        # 注入包装脚本到 PTY
        wrapper_path = str(wrapper_ps1).replace("'", "''")
        session.write(f"& '{wrapper_path}'\r\n")

        captured = ""
        return_code = 0
        timed_out = False
        interrupted = False

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if invocation_id:
                action = TerminalManager.consume_interrupt_action(invocation_id)
                if action:
                    interrupted = True
                    session.write("\x03")  # Ctrl+C
                    time.sleep(0.3)
                    break

            if done_file.exists():
                break

            time.sleep(0.15)
        else:
            timed_out = True
            session.write("\x03")
            time.sleep(0.3)

        # 读取结果
        if done_file.exists():
            try:
                return_code = int(done_file.read_text(encoding="utf-8").strip() or "0")
            except Exception:
                return_code = 1
        else:
            return_code = -1

        if cap_file.exists():
            captured = cap_file.read_text(encoding="utf-8", errors="replace")

        # 发送 ANSI 标记提示 AI 命令结束
        session._emit(
            f"\r\n\x1b[33m━━━ AI 命令执行完毕 (exit: {return_code}) ━━━\x1b[0m\r\n"
        )

        # 清理临时文件
        for f in (cap_file, done_file, cmd_ps1, wrapper_ps1):
            f.unlink(missing_ok=True)

        return {
            "success": return_code == 0 and not timed_out and not interrupted,
            "return_code": return_code,
            "output_capture": captured,
            "auto_detached": False,
            "timed_out": timed_out,
            "interrupted_action": "interrupt" if interrupted else None,
            "working_dir": work_dir,
        }

    def run_command_and_wait(
        self,
        command: str,
        work_dir: str | None = None,
        timeout: int = 300,
        visible_terminal_mode: str = "shared",
        invocation_id: str | None = None,
    ) -> dict[str, Any]:
        from utils.cli_process_cleanup import cleanup_stale_cli_processes

        cleanup_stale_cli_processes()
        target_dir = self._normalize_work_dir(work_dir)
        mode = str(visible_terminal_mode or "shared").strip().lower()

        if mode == "new":
            launch = self._launch_detached_command(command, target_dir)
            return {
                "success": True,
                "return_code": 0,
                "detached": True,
                "pid": launch.get("pid"),
                "output_capture": "",
                "auto_detached": False,
                "timed_out": False,
                "interrupted_action": None,
                "working_dir": target_dir,
            }

        # 优先尝试 agent PTY（ConsolePanel 可见），无连接时 fallback 到隐藏子进程
        pty_result = self._run_command_in_agent_pty(
            command, target_dir, timeout, invocation_id
        )
        return pty_result
