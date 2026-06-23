"""
CLI Executor - HTTP 客户端（委托给 Node.js CLI Server）
完全替代原有 subprocess/PTY 实现，通过 HTTP 调用 backend/cli/ 的 VS Code 风格 CLI
"""
from __future__ import annotations

import asyncio
import json
import os
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
        from utils.user_file_manager import UserFileManager
        manager = UserFileManager(work_dir=self._work_dir)
        return manager.get_user_dir()

    @property
    def user_home_dir(self) -> Path:
        return Path.home().resolve()

    def get_tool_definition(self) -> dict[str, Any]:
        """返回 AI 工具定义（保持兼容）"""
        return {
            "type": "function",
            "function": {
                "name": "cli_executor",
                "description": (
                    "执行本地 CLI 命令。仅用于文件操作、运行脚本、读取目录信息、安装依赖等任务。"
                    "如果命令包含删除、重命名、系统级变更等危险操作，会返回需要用户确认。"
                    "\n\n【重要提示】"
                    "1. 当返回 'file is locked' 或 'Internal error' 但 exit_code=0 时，说明命令实际已成功执行，无需重试。"
                    "2. 对于 pip install 等网络操作，建议设置 timeout 为 90 秒或更长。"
                    "3. 执行 Python 脚本时，如果脚本路径包含空格，请使用引号包裹。"
                    "4. 对于 npm run dev、pnpm dev、yarn dev、vite、next dev、python main.py、uvicorn 等开发服务器，"
                    "系统会自动使用新终端运行（new_terminal=true），不会中断已有命令。"
                    "timeout 建议 20-40 秒；服务启动成功后系统会自动转入后台。"
                    "5. 对于其他需要长时间运行的命令（如 deno serve、rails server），请显式设置 new_terminal=true。"
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
                            "description": "超时时间（秒）。简单命令建议 30s；pip install 等网络操作可用 120s+；默认 300。",
                            "default": 300,
                        },
                        "new_terminal": {
                            "type": "boolean",
                            "description": "是否新开一个独立终端会话。默认 false（复用已有终端）。",
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
        terminal_session_id: str | None = None,
        new_terminal: bool = False,
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

        # 自动检测长运行命令，强制使用新终端（避免覆盖正在运行的命令）
        if not new_terminal and _is_persistent_command(command):
            new_terminal = True

        try:
            payload = {
                "command": command.strip(),
                "working_dir": working_dir or "",
                "timeout": min(max(timeout, 1), self.MAX_TIMEOUT_SECONDS),
                "skip_confirmation": skip_confirmation,
                "invocation_id": invocation_id or "",
                "new_terminal": new_terminal,
            }

            resp = httpx.post(
                f"{server_url}/execute",
                json=payload,
                timeout=timeout + 10,
            )

            result = resp.json()

            # 兼容原接口字段
            if "captured_output" not in result:
                result["captured_output"] = result.get("output", "")
            result["working_dir"] = result.get("working_dir") or str(self.allowed_dir)

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
        new_terminal: bool = False,
        cancel_event: asyncio.Event | None = None,
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

        # 自动检测长运行命令，强制使用新终端
        if not new_terminal and _is_persistent_command(command):
            new_terminal = True

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
            "new_terminal": new_terminal,
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
            if "captured_output" not in result:
                result["captured_output"] = result.get("output", "")
            result["working_dir"] = result.get("working_dir") or str(self.allowed_dir)
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
]


def _is_persistent_command(command: str) -> bool:
    """检测是否为长运行命令（开发服务器等），这类命令应自动使用新终端。"""
    cmd = command.strip()
    return any(p.search(cmd) for p in _PERSISTENT_PATTERNS)