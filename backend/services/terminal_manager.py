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
    r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):\d+/?",
    r"\bLocal:\s+http://",
    r"\bNetwork:\s+http://",
    r"\bvite\b.*\bready\b",
    r"\bready in\b",
    r"\bcompiled successfully\b",
    r"\bserver (?:running|started|listening)\b",
    r"\blistening on\b",
    r"\bpress h \+ enter to show help\b",
    # 通用启动完成信号
    r"\bstarted\b.*\bagent\b",
    r"\bagent\b.*\bstarted\b",
    r"\b(?:model|client|server|embedding|ocr|llm)\b.*\binitiali[sz]ed\b",
    r"\binitiali[sz]ed\b.*\b(?:model|client|server)\b",
    r"\bstartup complete\b",
    r"\bready\b.*\b(?:to accept|for connections|on port)\b",
    r"\buvicorn running\b",
    r"\bflask running\b",
    r"\bdjango .* version\b.*\bstarting\b",
    r"\bgunicorn .* booted\b",
    r"\bApplication startup complete\b",
)
PERSISTENT_COMMAND_PATTERNS = (
    r"^(?:npm|pnpm|yarn|bun)(?:\.cmd)?\s+(?:run\s+)?(?:dev|start|serve)(?:\s|$)",
    r"^(?:npm|pnpm|yarn|bun)(?:\.cmd)?\s+start(?:\s|$)",
    r"^(?:npx\s+)?vite(?:\s|$)",
    r"^(?:npx\s+)?next\s+dev(?:\s|$)",
    r"^(?:npx\s+)?nuxt\s+dev(?:\s|$)",
    r"^(?:npx\s+)?astro\s+dev(?:\s|$)",
    r"^(?:npx\s+)?svelte-kit\s+dev(?:\s|$)",
    r"^(?:npx\s+)?webpack\s+serve(?:\s|$)",
    r"^(?:npx\s+)?vue-cli-service\s+serve(?:\s|$)",
    # Python / 通用启动脚本：长运行服务
    r"^python(?:3)?(?:\.exe)?\s+(?:main|app|run|server|start|manage)\b",
    r"^python(?:3)?(?:\.exe)?\s+\S+\s+(?:runserver|serve|start)\b",
    r"^python(?:3)?(?:\.exe)?\s+-m\s+(?:uvicorn|gunicorn|flask|django)\b",
    r"^uvicorn\b",
    r"^gunicorn\b",
    r"^flask\b.*\brun\b",
    # go / rust / java 服务启动
    r"^go\s+run\b",
    r"^cargo\s+run\b",
    r"^java\s+-jar\b",
)
AUTO_DETACH_STABLE_SECONDS = 2.5
PERSISTENT_COMMAND_START_TIMEOUT = 45
# Shell prompt detection patterns for command completion
_SHELL_PROMPT_PATTERNS = (
    rb"PS [A-Za-z]:[^\r\n>]*>[\s]*$",
    rb"PS /[^\r\n>]*>[\s]*$",
    rb"[A-Za-z]:[^\r\n>]*>[\s]*$",
    rb"[^>\s]+@[^>\s]+:[^>]*\$[\s]*$",
    rb"[^>\s]+@[^>\s]+:[^>]*#[\s]*$",
)
# cmd.exe / PowerShell 在 PTY 下产生的噪声序列：
# 1. 设备属性查询响应（DA1/DA2 等）
# 2. 光标显示/隐藏、光标位置查询响应
# 3. 标题设置等 OSC 序列
_NOISE_OUTPUT_RE = re.compile(
    r"\x1b\[\?1;2c"
    r"|\x1b\[>0;[0-9;]*c"
    r"|\x1b\[\?62;[0-9;]*c"
    r"|\x1b\[c"
    r"|\x1b\[(?:1|2)t"
    r"|\x1b\[\?(?:1004|9001|25|2004)[hl]"
    r"|\x1b\][0-9;]*[^\x07\x1b]*(?:\x07|\x1b\\)"
)
# 通用 ANSI CSI 序列清理：光标移动、擦除、SGR 颜色等。
# 用于回放给 AI 时剥离所有控制序列，避免乱码。
_ANSI_CSI_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"
)
# 其他 ANSI 转义（单字符 ESC + 字符，如 ESC 7/8/=/>）
_ANSI_SINGLE_RE = re.compile(
    r"\x1b[=>78MNc]"
)
# 回车/制表符保留，但连续空行压缩
_MULTI_BLANK_RE = re.compile(
    r"\n{3,}"
)
_MAX_OUTPUT_BUFFER_CHARS = 500_000
# 返回给 AI 的快照最大字符数（前端 xterm 渲染不受此限制）
_MAX_AI_SNAPSHOT_CHARS = 20_000


def _sanitize_terminal_output(data: str) -> str:
    if not data:
        return data
    cleaned = _NOISE_OUTPUT_RE.sub("", data)
    # 剩余的 CSI 序列（光标移动 / SGR 颜色 / 擦除等）全部剥离
    cleaned = _ANSI_CSI_RE.sub("", cleaned)
    cleaned = _ANSI_SINGLE_RE.sub("", cleaned)
    # 压缩连续空行（PTY 输出常含大量空行）
    cleaned = _MULTI_BLANK_RE.sub("\n\n", cleaned)
    return cleaned.strip()


def _is_persistent_command(command: str) -> bool:
    normalized = (command or "").strip().lower()
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in PERSISTENT_COMMAND_PATTERNS)


def _strip_ansi_for_detection(data: str) -> str:
    cleaned = _sanitize_terminal_output(data or "")
    return re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", cleaned)


def _detect_auto_detach_ready(output: str) -> bool:
    text = _strip_ansi_for_detection(output)
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in AUTO_DETACH_READY_PATTERNS)


def _detect_shell_prompt(buffer: str) -> bool:
    """Detect if the last line in buffer looks like a shell prompt."""
    if not buffer:
        return False
    # Take the last ~200 chars of the buffer
    tail = buffer[-500:] if len(buffer) > 500 else buffer
    # Split into lines and check the last meaningful line
    lines = tail.split("\r\n")
    if len(lines) < 2:
        lines = tail.split("\n")
    # Check last few lines for prompt pattern
    for line in reversed(lines[-5:]):
        line_bytes = line.encode("utf-8", errors="replace")
        for pattern in _SHELL_PROMPT_PATTERNS:
            if re.search(pattern, line_bytes):
                return True
    return False


class _TerminalSession:
    def __init__(self, work_dir: str) -> None:
        self.work_dir = str(Path(work_dir).expanduser().resolve())
        self.lock = threading.Lock()
        self._pty: Any = None
        self._pid: int | None = None
        self._alive = False
        self._rows = 30
        self._cols = 120
        self._output_buffer = ""
        self._callbacks: list[OutputCallback] = []
        self._closed_notified = False

    @property
    def pid(self) -> int | None:
        """返回底层 PtyProcess 的 PID，shell 未启动时返回 None。"""
        if self._pid is not None:
            return self._pid
        if self._pty is not None:
            try:
                self._pid = self._pty.pid
            except Exception:
                pass
        return self._pid

    def is_running(self) -> bool:
        if not self._alive or self._pty is None:
            return False
        try:
            if os.name == "nt":
                return bool(self._pty.isalive())
            return self._pty.poll() is None
        except Exception:
            return False

    def is_alive(self) -> bool:
        """保持与 _TerminalSession.close 配套使用：返回会话是否在运行。"""
        return self.is_running()

    def clear_output_buffer(self) -> None:
        with self.lock:
            self._output_buffer = ""

    def buffer_length(self) -> int:
        """返回当前 buffer 长度，用于记录命令执行前的位置。"""
        with self.lock:
            return len(self._output_buffer)

    def snapshot_buffer_from(self, start: int) -> str:
        """返回从指定位置开始的 buffer 内容（sanitize 后，截断到 AI 快照上限）。"""
        with self.lock:
            content = self._output_buffer[start:]
        content = _sanitize_terminal_output(content)
        if len(content) > _MAX_AI_SNAPSHOT_CHARS:
            content = content[-_MAX_AI_SNAPSHOT_CHARS:]
        return content

    @staticmethod
    def _interactive_shell_argv() -> list[str]:
        """交互式 Console 默认 PowerShell；winpty 必须用 argv 列表启动。"""
        if os.name != "nt":
            return [os.environ.get("SHELL", "/bin/bash")]
        override = (os.environ.get("ARIESCLAW_CONSOLE_SHELL") or "").strip()
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
            self._pid = self._pty.pid
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
            self._pid = self._pty.pid
            self._master_fd = master
            os.close(slave)
        self._alive = True
        self._closed_notified = False
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
        self._pid = None

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
        try:
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
        finally:
            if not self._alive:
                self._notify_closed("进程已退出")

    def _emit(self, data: str) -> None:
        if not data:
            return
        # 前端 xterm 需要原始 ANSI 序列才能正确渲染换行、光标移动、颜色等。
        # buffer 中保留原始输出；给 AI 看的快照/回放再在取用时 sanitize。
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
        """前端 xterm 回放：返回原始 buffer（保留 ANSI 控制序列）。

        PowerShell 的 prompt 大量使用 CSI 序列（\x1b[2K 清行、\r 回车等）
        来控制光标和换行。剥离这些序列后只剩 \\r + 纯文本，xterm 只回车
        不换行，导致所有输出挤在一行。原始 buffer 交给 xterm 渲染才能
        正确还原终端显示。
        """
        with self.lock:
            return self._output_buffer

    def _notify_closed(self, reason: str = "会话已关闭") -> None:
        if self._closed_notified:
            return
        self._closed_notified = True
        self._emit(f"\r\n[Terminal] {reason}\r\n")

    def close(self) -> None:
        # 关闭前先通知订阅者；保留 buffer，前端仍可回放历史输出。
        self._notify_closed("会话已关闭")
        self._alive = False
        self._pid = None
        try:
            if os.name == "nt" and self._pty:
                self._pty.close(force=True)
            elif self._pty:
                self._pty.terminate()
        except Exception:
            pass

    def snapshot_buffer(self) -> str:
        """Return current buffer without clearing (sanitized, truncated for AI)."""
        with self.lock:
            content = self._output_buffer
        content = _sanitize_terminal_output(content)
        if len(content) > _MAX_AI_SNAPSHOT_CHARS:
            content = content[-_MAX_AI_SNAPSHOT_CHARS:]
        return content

    def kill_command(self) -> None:
        """Send Ctrl+C to the PTY to interrupt the currently running foreground command."""
        self.write("\x03")


class TerminalManager:
    _instance: TerminalManager | None = None
    _lock = threading.Lock()
    _interrupt_actions: dict[str, str] = {}
    _interrupt_lock = threading.Lock()
    _invocation_session_map: dict[str, str] = {}
    _map_lock = threading.Lock()

    def __init__(self) -> None:
        self._sessions: dict[str, _TerminalSession] = {}
        self._session_lock = threading.Lock()
        self._persistent_sessions: set[str] = set()
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
            path = Path(work_dir).expanduser().resolve()
        else:
            path = Path.home() / ".Aries" / "work_dir"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

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

    def attach_interactive(
        self,
        session_id: str,
        work_dir: str | None,
        rows: int,
        cols: int,
        reset: bool = True,
    ) -> _TerminalSession:
        if reset:
            try:
                from utils.cli_process_cleanup import cleanup_stale_cli_processes

                cleanup_stale_cli_processes()
            except ImportError:
                pass
        session = self.get_session(session_id, work_dir)
        if reset:
            session.restart_shell(rows=rows, cols=cols)
        elif not session.is_running():
            # shell 进程已退出，重启但保留 buffer（用户可以查看回放）
            session._spawn_shell(rows=rows, cols=cols, clear_buffer=False)
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

    @classmethod
    def set_interrupt_action(cls, invocation_id: str, action: str) -> None:
        """注册中断动作（由 CLIExecutor 在取消时调用）。"""
        with cls._interrupt_lock:
            cls._interrupt_actions[invocation_id] = action

    @classmethod
    def consume_interrupt_action(cls, invocation_id: str) -> str | None:
        with cls._interrupt_lock:
            return cls._interrupt_actions.pop(invocation_id, None)

    @classmethod
    def register_invocation_session(cls, invocation_id: str, session_id: str) -> None:
        with cls._map_lock:
            cls._invocation_session_map[invocation_id] = session_id

    @classmethod
    def lookup_session_for_invocation(cls, invocation_id: str) -> str | None:
        with cls._map_lock:
            sid = cls._invocation_session_map.get(invocation_id)
            if sid:
                return sid
            suffix = f":{invocation_id}"
            for key, value in cls._invocation_session_map.items():
                if key.endswith(suffix):
                    return value
            return None

    @classmethod
    def resolve_invocation_id(cls, invocation_id: str) -> str:
        with cls._map_lock:
            if invocation_id in cls._invocation_session_map:
                return invocation_id
            suffix = f":{invocation_id}"
            for key in cls._invocation_session_map.keys():
                if key.endswith(suffix):
                    return key
            return invocation_id

    @classmethod
    def close_session_if_exists(cls, session_id: str) -> bool:
        """关闭指定 session 的终端进程。返回是否成功找到并关闭。"""
        instance = cls.get_instance()
        session = instance._sessions.get(session_id)
        if session is None:
            return False
        session.close()
        instance._persistent_sessions.discard(session_id)
        return True

    @classmethod
    def terminate_all_active(cls, action: str = "terminate") -> list[str]:
        """终止所有 PTY 会话中的运行中命令。

        返回被关闭的 session id 列表。
        """
        closed: list[str] = []
        instance = cls.get_instance()
        with instance._session_lock:
            session_ids = list(instance._sessions.keys())
        for sid in session_ids:
            try:
                if sid in instance._persistent_sessions:
                    continue
                session = instance._sessions.get(sid)
                if session is None:
                    continue
                if session.is_alive():
                    session.close()
                    closed.append(sid)
            except Exception:
                pass
        return closed

    @classmethod
    def close_all_sessions(cls) -> list[str]:
        """关闭所有终端会话，包括 persistent（用于后端关闭）。返回被关闭的 session id 列表。"""
        closed: list[str] = []
        instance = cls.get_instance()
        with instance._session_lock:
            session_ids = list(instance._sessions.keys())
        for sid in session_ids:
            try:
                session = instance._sessions.get(sid)
                if session is None:
                    continue
                if session.is_alive():
                    session.close()
                    closed.append(sid)
                instance._persistent_sessions.discard(sid)
            except Exception:
                pass
        return closed

    @classmethod
    def clear_runtime_dir(cls) -> int:
        """清理 ~/.Aries/temp/cli_runtime 下的 PTY/捕获残留文件。"""
        try:
            from utils.cli_executor import CLIExecutor
            return CLIExecutor.clear_runtime_dir()
        except Exception:
            return 0

    def open_terminal_for_command(
        self,
        command: str,
        work_dir: str | None = None,
        timeout: int = 300,
        invocation_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """为 AI 命令创建一个新的专用终端会话，注入命令并等待完成。

        与 _run_command_in_agent_pty 不同，此方法:
        - 使用全新 session_id（不会与 agent session 冲突）
        - 不检查 WebSocket 订阅者
        - 返回 session_id 供前端连接

        命令执行完毕后终端保留，用户可在 ConsolePanel 中继续使用。
        """
        mapped_session_id = self.lookup_session_for_invocation(invocation_id) if invocation_id else None
        session_id = (session_id or mapped_session_id or "").strip() or f"ai-{uuid.uuid4().hex[:8]}"
        target_dir = self._normalize_work_dir(work_dir)

        if invocation_id:
            TerminalManager.register_invocation_session(invocation_id, session_id)

        session = self.get_session(session_id, target_dir)
        session.ensure_shell_ready()

        if not session.is_running():
            return {
                "success": False,
                "return_code": -1,
                "output_capture": "",
                "error": "无法启动终端 shell",
                "timed_out": False,
                "interrupted_action": None,
                "working_dir": target_dir,
                "session_id": session_id,
                "pid": session.pid,
            }

        # 等待 shell 初始化完成（prompt 出现）
        time.sleep(0.3)

        uid = uuid.uuid4().hex[:8]
        temp_dir = Path.home() / ".Aries" / "temp" / "cli_runtime"
        temp_dir.mkdir(parents=True, exist_ok=True)
        cap_file = temp_dir / f"out_{uid}.txt"
        done_file = temp_dir / f"done_{uid}.txt"
        cmd_ps1 = temp_dir / f"cmd_{uid}.ps1"

        # 清理残留旧文件
        for f in (cap_file, done_file, cmd_ps1):
            try:
                f.unlink(missing_ok=True)
            except PermissionError:
                pass

        cap_path = str(cap_file).replace("'", "''")
        done_path = str(done_file).replace("'", "''")
        cmd_path = str(cmd_ps1).replace("'", "''")

        # 将命令 + 捕获逻辑 + 退出码全部写入 ps1 文件
        # 避免：1) PTY 行长度限制导致命令被截断  2) PowerShell 命令行解析破坏引号
        # 开头 Write-Host 回显原始命令，让前端控制台显示真实命令而非 .ps1 路径
        # （前端 ConsolePanel 会过滤掉 & 'xxx.ps1' 调度行）
        # PowerShell 单引号字符串中，单引号本身用 '' 转义
        echo_command_ps = command.replace("'", "''")
        script = (
            f"$ErrorActionPreference = 'Continue'\r\n"
            f"chcp 65001 > $null\r\n"
            f"$OutputEncoding = [System.Text.Encoding]::UTF8\r\n"
            f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\r\n"
            f"Write-Host -ForegroundColor DarkGray '$ {echo_command_ps}'\r\n"
            f"$capFile = '{cap_path}'\r\n"
            f"$doneFile = '{done_path}'\r\n"
            f"$code = 0\r\n"
            f"try {{\r\n"
            f"    {command} 2>&1 | ForEach-Object {{\r\n"
            f"        Write-Host $_\r\n"
            f"        $_ | Out-File -FilePath $capFile -Encoding utf8 -Append\r\n"
            f"    }}\r\n"
            f"    $code = $LASTEXITCODE\r\n"
            f"    if ($code -eq $null) {{ $code = 0 }}\r\n"
            f"}} catch {{\r\n"
            f"    $_ | Out-String | Write-Host\r\n"
            f"    $code = 1\r\n"
            f"}}\r\n"
            f"[System.IO.File]::WriteAllText($doneFile, $code.ToString())\r\n"
        )
        cmd_ps1.write_bytes(b'\xef\xbb\xbf' + script.encode("utf-8"))

        # 记录执行前的 buffer 位置，捕获时只取新内容（不清空 buffer，前端保留历史）
        buffer_start = session.buffer_length()

        # 执行 ps1 文件（前端 ConsolePanel 会过滤掉这行调度路径，只看到 ps1 内 Write-Host 的原始命令）
        session.write(f"& '{cmd_path}'\r\n")

        captured = ""
        return_code = 0
        timed_out = False
        interrupted_action = None
        is_backgrounded = False
        auto_detached = False
        persistent_command = _is_persistent_command(command)
        ready_at: float | None = None
        last_ready_len = 0
        last_buffer_len = 0
        last_change_at = time.monotonic()

        # persistent 命令不再立即返回：走下面的循环检测 ready 信号，
        # 检测到后 auto_detach 返回，AI 能看到完整启动日志。
        # 超时仍未 ready 也 auto_detach（不 kill），保证进程保留可回放。
        if persistent_command:
            self._persistent_sessions.add(session_id)
            # persistent 命令使用更短的内部门限：ready 检测窗口最多 15s，
            # 不要让 AI 传入的 30s/60s timeout 全部耗尽。
            effective_timeout = min(timeout, 15)
            logger.info(
                "[PTY] persistent command detected, effective_timeout=%ss (ai_timeout=%ss)",
                effective_timeout, timeout,
            )
        else:
            effective_timeout = timeout

        deadline = time.monotonic() + effective_timeout
        while time.monotonic() < deadline:
            if invocation_id:
                action = TerminalManager.consume_interrupt_action(invocation_id)
                if action:
                    if action == "background":
                        is_backgrounded = True
                        break
                    else:
                        interrupted_action = action
                        session.kill_command()
                        time.sleep(0.3)
                        break

            if done_file.exists():
                # 额外检查：等待提示符稳定后再确认完成
                time.sleep(0.1)
                if _detect_shell_prompt(session.snapshot_buffer()):
                    break
                elif done_file.stat().st_size > 0:
                    # done_file 有内容但还没检测到提示符，再多等一会儿
                    time.sleep(0.3)
                    break

            snapshot = session.snapshot_buffer()
            snapshot_len = len(snapshot)

            # 跟踪 buffer 是否还在增长（用于停滞检测）
            if snapshot_len != last_buffer_len:
                last_buffer_len = snapshot_len
                last_change_at = time.monotonic()

            if persistent_command and _detect_auto_detach_ready(snapshot):
                logger.debug("[PTY] ready signal detected in buffer (%d chars)", snapshot_len)
                # 多阶段启动（如 Embedding → OCR → LLM 依次 initialized）：
                # 每次输出变化都重置 ready_at，等启动真正稳定后再 detach。
                current_len = snapshot_len
                if ready_at is None or current_len != last_ready_len:
                    ready_at = time.monotonic()
                    last_ready_len = current_len
                elif time.monotonic() - ready_at >= AUTO_DETACH_STABLE_SECONDS:
                    logger.info("[PTY] ready signal stable for %.1fs, auto-detaching", AUTO_DETACH_STABLE_SECONDS)
                    auto_detached = True
                    is_backgrounded = True
                    self._persistent_sessions.add(session_id)
                    break
            else:
                ready_at = None
                last_ready_len = 0
                # 停滞检测：persistent 命令如果 buffer 5s 没有新输出，
                # 认为启动阶段结束（可能 ready pattern 没覆盖到），直接 auto_detach。
                if persistent_command and snapshot_len > 100:
                    stall_seconds = time.monotonic() - last_change_at
                    if stall_seconds >= 5.0:
                        logger.info("[PTY] buffer stalled for %.1fs, auto-detaching (no ready match)", stall_seconds)
                        auto_detached = True
                        is_backgrounded = True
                        self._persistent_sessions.add(session_id)
                        break

            # 备用：如果检测到提示符且 done_file 即将出现
            if _detect_shell_prompt(snapshot):
                time.sleep(0.1)
                if done_file.exists():
                    break

            time.sleep(0.15)
        else:
            if persistent_command:
                logger.info("[PTY] persistent command reached effective timeout, auto-detaching (not kill)")
                auto_detached = True
                is_backgrounded = True
                self._persistent_sessions.add(session_id)
            else:
                timed_out = True
                session.kill_command()
                time.sleep(0.3)

        # 读取结果（只取本次命令执行后的新内容，不含历史输出）
        if is_backgrounded:
            return_code = 0
            captured = session.snapshot_buffer_from(buffer_start) or "命令已转入后台运行"
        elif done_file.exists():
            try:
                raw = done_file.read_text(encoding="utf-8-sig", errors="replace").strip()
                return_code = int(raw) if raw.lstrip("-").isdigit() else 0
            except Exception:
                return_code = 1
            if cap_file.exists():
                captured = _sanitize_terminal_output(cap_file.read_text(encoding="utf-8-sig", errors="replace"))
            else:
                captured = session.snapshot_buffer_from(buffer_start)
        else:
            return_code = -1
            captured = session.snapshot_buffer_from(buffer_start)

        return {
            "success": return_code == 0 and not timed_out and not interrupted_action,
            "return_code": return_code,
            "output_capture": captured,
            "auto_detached": auto_detached,
            "timed_out": timed_out,
            "interrupted_action": interrupted_action,
            "working_dir": target_dir,
            "session_id": session_id,
            "pid": session.pid,
        }

    def run_command_and_wait(
        self,
        command: str,
        work_dir: str | None = None,
        timeout: int = 300,
        invocation_id: str | None = None,
    ) -> dict[str, Any]:
        """前端手动执行命令：委托给 open_terminal_for_command，使用 agent 共享 session。

        统一走 PTY 路径，消除 _run_command_in_agent_pty / _run_subprocess_and_wait
        两套重复逻辑。agent session 让 ConsolePanel 能直接看到输出。
        """
        target_dir = self._normalize_work_dir(work_dir)
        # 使用 agent session，让前端 ConsolePanel 能看到命令执行过程
        agent_sid = self.resolve_agent_session_id(work_dir)
        return self.open_terminal_for_command(
            command=command,
            work_dir=target_dir,
            timeout=timeout,
            invocation_id=invocation_id,
            session_id=agent_sid,
        )
