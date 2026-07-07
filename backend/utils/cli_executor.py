"""
CLI Executor - HTTP 客户端（委托给 Node.js CLI Server）
完全替代原有 subprocess/PTY 实现，通过 HTTP 调用 backend/cli/ 的 VS Code 风格 CLI
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx


_CLI_SERVER_URL: str = ""
_CLI_PORT: int = 0


def configure(port: int) -> None:
    """由 TerminalManager 在 Node.js CLI 启动后调用"""
    global _CLI_SERVER_URL, _CLI_PORT
    _CLI_PORT = port
    _CLI_SERVER_URL = f"http://127.0.0.1:{port}"


def get_server_url() -> str:
    global _CLI_SERVER_URL
    if not _CLI_SERVER_URL:
        return ""
    return _CLI_SERVER_URL


def get_server_port() -> int:
    return _CLI_PORT


class CLIExecutor:
    """CLI 执行器 - 通过 HTTP 委托给 Node.js CLI Server

    保持与原 CLIExecutor 相同的接口签名，方便 AI 工具调用。
    实际执行在 Node.js 进程中完成（使用 node-pty，比 winpty 更稳定）。

    支持异步可中断执行：用户点击"后台运行"或"停止服务"时，
    可以通过 signal_detach / signal_cancel 通知正在执行的命令立即返回。
    """

    DEFAULT_TIMEOUT_SECONDS = 300
    MAX_TIMEOUT_SECONDS = 86400
    DIRECT_VISIBLE_COMMAND_MAX_LENGTH = 4000
    # async 模式下等待初始输出信号的超时（秒）
    ASYNC_INITIAL_TIMEOUT_SECONDS = 15

    # invocation_id -> asyncio.Event，用于外部信号通知
    _detach_events: dict[str, asyncio.Event] = {}
    _cancel_events: dict[str, asyncio.Event] = {}

    def __init__(self, user_email: str | None = None, work_dir: str | None = None) -> None:
        self._work_dir = work_dir

    @property
    def allowed_dir(self) -> Path:
        from engine.file_manager import UserFileManager
        manager = UserFileManager(work_dir=self._work_dir)
        return manager.get_user_dir()

    @property
    def user_home_dir(self) -> Path:
        return Path.home().resolve()

    def _resolve_mode_and_session(self, command: str, mode: str, session_id: str) -> tuple[str, str, int]:
        """解析 mode/session_id/timeout。返回 (session_id, effective_mode, effective_timeout)。"""
        mode = (mode or "sync").lower()
        if mode == "async":
            # async 模式：自动生成 session_id，使用短超时等待初始输出
            if not session_id:
                session_id = f"ai-{uuid.uuid4().hex[:8]}"
            return session_id, "async", self.ASYNC_INITIAL_TIMEOUT_SECONDS
        else:
            # sync 模式：持久命令自动检测
            if not session_id and _is_persistent_command(command):
                session_id = f"ai-{uuid.uuid4().hex[:8]}"
            return session_id, "sync", 0

    def execute(
        self,
        command: str,
        working_dir: str | None = None,
        timeout: int = 300,
        skip_confirmation: bool = False,
        invocation_id: str | None = None,
        terminal_session_id: str | None = None,
        session_id: str = "",
        mode: str = "sync",
        **extra,
    ) -> dict[str, Any]:
        """通过 HTTP 委托给 Node.js CLI Server 执行命令"""
        server_url = get_server_url()
        if not server_url:
            return {
                "success": False,
                "error": "CLI Server not started",
                "output": "CLI 服务未启动，请稍后重试",
                "command": command,
                "requires_confirmation": False,
            }

        if not command or not command.strip():
            return {
                "success": False,
                "error": "Missing command",
                "output": "缺少要执行的命令",
                "command": "",
                "requires_confirmation": False,
            }

        # 解析 mode：async 模式自动生成 session_id 并使用短超时
        session_id, effective_mode, async_timeout = self._resolve_mode_and_session(
            command, mode, session_id
        )

        # async 模式使用短超时等待初始输出
        if effective_mode == "async":
            timeout = async_timeout

        try:
            payload = {
                "command": command.strip(),
                "working_dir": working_dir or "",
                "timeout": min(max(timeout, 1), self.MAX_TIMEOUT_SECONDS),
                "skip_confirmation": skip_confirmation,
                "invocation_id": invocation_id or "",
                "session_id": session_id,
            }

            resp = httpx.post(
                f"{server_url}/execute",
                json=payload,
                timeout=timeout + 10,
            )

            result = resp.json()
            result = self._normalize_cli_result(result)

            # async 模式：无论是否超时，只要有 session_id 就标记为后台运行
            if effective_mode == "async" and session_id:
                result["is_background"] = True
                result["session_id"] = session_id
                result["output"] = result.get("output", "") + f"\n\n[后台运行中] session_id: {session_id}\n后续可用 check_command_status 查看输出，stop_command 停止。"

            return result

        except httpx.ConnectError:
            return {
                "success": False,
                "error": "CLI Server unavailable",
                "output": "CLI 服务无法连接，请尝试重启后端服务",
                "command": command,
                "requires_confirmation": False,
            }
        except httpx.TimeoutException:
            # async 模式超时是正常的：命令在后台继续运行
            if effective_mode == "async" and session_id:
                return {
                    "success": True,
                    "return_code": 0,
                    "output": f"命令已在后台启动\n命令: {command}\nsession_id: {session_id}\n\n后续可用 check_command_status 查看输出，stop_command 停止。",
                    "command": command,
                    "is_background": True,
                    "session_id": session_id,
                    "requires_confirmation": False,
                }
            return {
                "success": False,
                "error": f"Request timed out after {timeout + 10}s",
                "output": f"命令请求超时\n命令: {command}\n",
                "command": command,
                "timed_out": True,
                "requires_confirmation": False,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": f"执行异常: {e}",
                "command": command,
                "requires_confirmation": False,
            }

    # ---- 以下静态方法仅为兼容保留（实际委托给 Node.js CLI） ----

    @classmethod
    def signal_detach(cls, invocation_id: str) -> None:
        """用户点击"后台运行"时调用，通知对应 invocation 立即 detach。"""
        event = cls._detach_events.get(invocation_id)
        if event and not event.is_set():
            event.set()

    @classmethod
    def signal_cancel(cls, invocation_id: str) -> None:
        """用户点击"停止服务"或停止生成时调用，通知对应 invocation 立即取消。"""
        event = cls._cancel_events.get(invocation_id)
        if event and not event.is_set():
            event.set()

    @classmethod
    def cancel_session_invocations(cls, session_id: str) -> list[str]:
        """取消某 chat session 下所有进行中的 cli_executor 调用。"""
        if not session_id:
            return []
        prefix = f"{session_id}:"
        cancelled: list[str] = []
        for inv_id in list(cls._cancel_events.keys()):
            if inv_id.startswith(prefix):
                cls.signal_cancel(inv_id)
                cancelled.append(inv_id)
        return cancelled

    @classmethod
    def get_active_invocations(cls) -> list[str]:
        return []

    @classmethod
    def set_interrupt_action(cls, inv_id: str, action: str) -> None:
        pass

    @classmethod
    def terminate_all_active(cls, action: str = "terminate") -> list[str]:
        return []

    @classmethod
    def clear_runtime_dir(cls) -> int:
        return 0

    # ------------------------------------------------------------------
    # 异步可中断执行（agent_mode 使用）
    # ------------------------------------------------------------------

    async def execute_async(
        self,
        command: str,
        working_dir: str | None = None,
        timeout: int = 300,
        skip_confirmation: bool = False,
        invocation_id: str | None = None,
        terminal_session_id: str | None = None,
        session_id: str = "",
        mode: str = "sync",
        cancel_event: asyncio.Event | None = None,
        **extra,
    ) -> dict[str, Any]:
        """异步执行命令，支持用户中断和后台运行。

        与 execute() 行为一致，但会监听外部信号：
        - signal_detach(invocation_id)：用户点击"后台运行"，立即让命令返回 auto_detached
        - signal_cancel(invocation_id)：用户点击"停止服务"或停止生成，立即取消命令
        """
        server_url = get_server_url()
        if not server_url:
            return {
                "success": False,
                "error": "CLI Server not started",
                "output": "CLI 服务未启动，请稍后重试",
                "command": command,
                "requires_confirmation": False,
            }

        if not command or not command.strip():
            return {
                "success": False,
                "error": "Missing command",
                "output": "缺少要执行的命令",
                "command": "",
                "requires_confirmation": False,
            }

        # 解析 mode：async 模式自动生成 session_id 并使用短超时
        session_id, effective_mode, async_timeout = self._resolve_mode_and_session(
            command, mode, session_id
        )

        # async 模式使用短超时等待初始输出
        if effective_mode == "async":
            timeout = async_timeout

        # 按域名规则注入代理环境变量（npm install / git clone 等）
        original_command = command.strip()
        try:
            from utils.network_manager import wrap_command_with_proxy
            command = wrap_command_with_proxy(original_command)
        except Exception:
            command = original_command

        payload = {
            "command": command,
            "working_dir": working_dir or "",
            "timeout": min(max(timeout, 1), self.MAX_TIMEOUT_SECONDS),
            "skip_confirmation": skip_confirmation,
            "invocation_id": invocation_id or "",
            "session_id": session_id,
        }

        # 注册事件
        detach_event = asyncio.Event()
        local_cancel_event = asyncio.Event()
        if invocation_id:
            self._detach_events[invocation_id] = detach_event
            self._cancel_events[invocation_id] = local_cancel_event

        async def _request() -> httpx.Response:
            async with httpx.AsyncClient() as client:
                return await client.post(
                    f"{server_url}/execute",
                    json=payload,
                    timeout=timeout + 10,
                )

        async def _wait_signal() -> str:
            """等待 detach 或 cancel 信号。"""
            tasks: list[asyncio.Task] = []
            tasks.append(asyncio.create_task(detach_event.wait()))
            tasks.append(asyncio.create_task(local_cancel_event.wait()))
            if cancel_event:
                tasks.append(asyncio.create_task(cancel_event.wait()))

            try:
                done, pending = await asyncio.wait(
                    tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except asyncio.CancelledError:
                # 外部取消：清理所有内部任务，避免 "Task was destroyed but it is pending"
                for t in tasks:
                    t.cancel()
                for t in tasks:
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass
                raise

            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            if detach_event.is_set():
                return "detach"
            return "cancel"

        request_task: asyncio.Task | None = None
        signal_task: asyncio.Task | None = None
        try:
            request_task = asyncio.create_task(_request())
            signal_task = asyncio.create_task(_wait_signal())

            done, pending = await asyncio.wait(
                [request_task, signal_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if signal_task in done:
                # 用户触发了信号
                action = signal_task.result()
                if action == "detach":
                    # 通知 Node.js detach，然后等待 /execute 返回
                    await self._call_nodejs_detach(server_url, invocation_id)
                    # 等待 /execute 返回（Node.js 已经 finish，会很快）
                    try:
                        resp = await request_task
                        result = resp.json()
                    except Exception:
                        result = {
                            "success": True,
                            "return_code": 0,
                            "output": f"命令已转入后台运行\n命令: {command}",
                            "command": command,
                            "auto_detached": True,
                            "requires_confirmation": False,
                        }
                    return result
                else:
                    # cancel：通知 Node.js interrupt 并取消 HTTP 请求
                    await self._call_nodejs_interrupt(server_url, invocation_id)
                    request_task.cancel()
                    try:
                        await request_task
                    except asyncio.CancelledError:
                        pass
                    return {
                        "success": False,
                        "error": "User cancelled",
                        "output": "用户已停止命令执行",
                        "command": command,
                        "requires_confirmation": False,
                    }

            # /execute 先完成
            resp = await request_task
            result = resp.json()
            result = self._normalize_cli_result(result)

            # async 模式：标记为后台运行
            if effective_mode == "async" and session_id:
                result["is_background"] = True
                result["session_id"] = session_id
                result["output"] = result.get("output", "") + f"\n\n[后台运行中] session_id: {session_id}\n后续可用 check_command_status 查看输出，stop_command 停止。"

            return result

        except httpx.ConnectError:
            return {
                "success": False,
                "error": "CLI Server unavailable",
                "output": "CLI 服务无法连接，请尝试重启后端服务",
                "command": command,
                "requires_confirmation": False,
            }
        except httpx.TimeoutException:
            # async 模式超时是正常的：命令在后台继续运行
            if effective_mode == "async" and session_id:
                return {
                    "success": True,
                    "return_code": 0,
                    "output": f"命令已在后台启动\n命令: {command}\nsession_id: {session_id}\n\n后续可用 check_command_status 查看输出，stop_command 停止。",
                    "command": command,
                    "is_background": True,
                    "session_id": session_id,
                    "requires_confirmation": False,
                }
            # sync 模式超时才是错误
            return {
                "success": False,
                "error": f"Request timed out after {timeout + 10}s",
                "output": f"命令请求超时\n命令: {command}\n",
                "command": command,
                "timed_out": True,
                "requires_confirmation": False,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": f"执行异常: {e}",
                "command": command,
                "requires_confirmation": False,
            }
        finally:
            # 确保所有子任务被取消，避免 "Task was destroyed but it is pending"
            for t in [request_task, signal_task]:
                if t and not t.done():
                    t.cancel()
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass
            if invocation_id:
                self._detach_events.pop(invocation_id, None)
                self._cancel_events.pop(invocation_id, None)

    def _normalize_cli_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """清理 output 中的 ANSI 转义；captured_output 保留原始供前端回放。"""
        from utils.terminal_output import sanitize_terminal_output_for_ai

        output = result.get("output", "")
        if isinstance(output, str):
            result["output"] = sanitize_terminal_output_for_ai(output)
        if "captured_output" not in result:
            result["captured_output"] = result.get("output", "")
        result["working_dir"] = result.get("working_dir") or str(self.allowed_dir)
        return result

    async def _call_nodejs_detach(self, server_url: str, invocation_id: str | None) -> None:
        """调用 Node.js CLI 的 detach 端点。"""
        if not server_url or not invocation_id:
            return
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{server_url}/sessions/{invocation_id}/detach",
                    timeout=5,
                )
        except Exception:
            pass

    async def _call_nodejs_interrupt(self, server_url: str, invocation_id: str | None) -> None:
        """调用 Node.js CLI 的 interrupt 端点。"""
        if not server_url or not invocation_id:
            return
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{server_url}/sessions/{invocation_id}/interrupt",
                    timeout=5,
                )
        except Exception:
            pass


# 长运行服务检测模式（与 Node.js CLI 的 PERSISTENT_PATTERNS 对齐）
import re as _re

_PERSISTENT_PATTERNS: list[_re.Pattern] = [
    _re.compile(r"^(?:npm|pnpm|yarn|bun)(?:\.cmd)?\s+(?:run\s+)?(?:dev|start|serve)(?:\s|$)", _re.IGNORECASE),
    _re.compile(r"^(?:npx\s+)?vite(?:\s|$)", _re.IGNORECASE),
    _re.compile(r"^(?:npx\s+)?next\s+dev(?:\s|$)", _re.IGNORECASE),
    _re.compile(r"^python(?:3)?(?:\.exe)?\s+(?:main|app|run|server|start|manage)\b", _re.IGNORECASE),
    _re.compile(r"^python(?:3)?(?:\.exe)?\s+-m\s+(?:uvicorn|gunicorn|flask|django)\b", _re.IGNORECASE),
    _re.compile(r"^uvicorn\b", _re.IGNORECASE),
    _re.compile(r"^gunicorn\b", _re.IGNORECASE),
    _re.compile(r"^flask\b.*\brun\b", _re.IGNORECASE),
    _re.compile(r"^go\s+run\b", _re.IGNORECASE),
    _re.compile(r"^cargo\s+run\b", _re.IGNORECASE),
    _re.compile(r"^java\s+-jar\b", _re.IGNORECASE),
    # 新增：Spring Boot / Gradle / .NET / PHP / Rails
    _re.compile(r"^(?:mvn(?:\.cmd)?|gradle(?:\.bat)?)\s+(?:spring-boot:run|bootRun)\b", _re.IGNORECASE),
    _re.compile(r"^dotnet\s+run\b", _re.IGNORECASE),
    _re.compile(r"^php\s+artisan\s+serve\b", _re.IGNORECASE),
    _re.compile(r"^(?:bundle\s+exec\s+)?rails\s+(?:s|server)\b", _re.IGNORECASE),
]


def _is_persistent_command(command: str) -> bool:
    """检测是否为长运行命令（开发服务器等），这类命令应自动使用新终端。"""
    cmd = command.strip()
    return any(p.search(cmd) for p in _PERSISTENT_PATTERNS)