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

    def execute(
        self,
        command: str,
        working_dir: str | None = None,
        timeout: int = 300,
        skip_confirmation: bool = False,
        invocation_id: str | None = None,
        terminal_session_id: str | None = None,
        session_id: str = "",
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

        # 自动检测长运行命令，未指定 session_id 时自动生成（避免覆盖正在运行的命令）
        if not session_id and _is_persistent_command(command):
            session_id = f"ai-{uuid.uuid4().hex[:8]}"

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
            return self._normalize_cli_result(result)

        except httpx.ConnectError:
            return {
                "success": False,
                "error": "CLI Server unavailable",
                "output": "CLI 服务无法连接，请尝试重启后端服务",
                "command": command,
                "requires_confirmation": False,
            }
        except httpx.TimeoutException:
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

        # 自动检测长运行命令，未指定 session_id 时自动生成
        if not session_id and _is_persistent_command(command):
            session_id = f"ai-{uuid.uuid4().hex[:8]}"

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

            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            if detach_event.is_set():
                return "detach"
            return "cancel"

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
            return self._normalize_cli_result(result)

        except httpx.ConnectError:
            return {
                "success": False,
                "error": "CLI Server unavailable",
                "output": "CLI 服务无法连接，请尝试重启后端服务",
                "command": command,
                "requires_confirmation": False,
            }
        except httpx.TimeoutException:
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