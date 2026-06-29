"""
Terminal Manager - Node.js CLI 进程管理器

在 FastAPI 启动时自动启动 backend/cli/ 的 Node.js CLI 服务，
在关闭时自动清理。前端 WebSocket 直接连接 Node.js CLI。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---- Node.js CLI 进程管理 ----

_CLI_PROCESS: subprocess.Popen[str] | None = None
_CLI_PORT: int = 0
_CLI_STARTED = threading.Event()


def find_cli_dir() -> Path:
    """查找 backend/cli/ 目录（开发或打包后的 resources/cli）。"""
    from utils.app_paths import get_cli_dir
    return get_cli_dir()


def find_node() -> str:
    """查找 node 可执行文件。

    优先级：
        1. env.json 用户配置
        2. ~/.Aries/runtimes/node（安装包首次释放的内置 Node）
        3. 安装包 resources/node（尚未释放时的兜底）
        4. 系统 PATH / 常见路径
    """
    from utils.runtime_manager import resolve_runtime

    resolved = resolve_runtime("node")
    if resolved.get("path"):
        return resolved["path"]

    node = os.environ.get("NODE_EXE", "") or shutil_which("node")
    if node:
        return node

    # 尝试常见路径
    candidates = [
        r"C:\Program Files\nodejs\node.exe",
        r"C:\Program Files (x86)\nodejs\node.exe",
    ]
    if os.environ.get("LOCALAPPDATA"):
        candidates.insert(0, os.environ["LOCALAPPDATA"] + r"\fnm\node-versions\latest\node.exe")
    if os.environ.get("USERPROFILE"):
        candidates.insert(0, os.environ["USERPROFILE"] + r"\AppData\Roaming\nvm\v18.17.0\node.exe")
    for c in candidates:
        if os.path.isfile(c):
            return str(Path(c).resolve())
    raise RuntimeError(
        "未找到 Node.js 可执行文件。请安装 Node.js 并确保其在 PATH 中，"
        "或设置环境变量 NODE_EXE。"
    )


def shutil_which(cmd: str) -> str:
    """查找可执行文件"""
    import shutil
    result = shutil.which(cmd)
    return result or ""


def get_cli_port() -> int:
    return _CLI_PORT


def _find_available_port(start: int = 18765) -> int:
    """找到可用端口"""
    import socket
    for port in range(start, start + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return start  # fallback


def _parse_cli_stdout(line: str) -> dict[str, Any] | None:
    """解析 Node.js CLI 的 stdout JSON 行"""
    line = line.strip()
    if not line:
        return None
    if not line.startswith('{'):
        return None
    try:
        data = json.loads(line)
        if data.get("event") == "ready":
            return data
    except json.JSONDecodeError:
        pass
    return None


def start_cli_server(
    work_dir: str | None = None,
    port: int = 0,
) -> int:
    """启动 Node.js CLI Server，返回分配的端口号"""
    global _CLI_PROCESS, _CLI_PORT

    if _CLI_PROCESS and _CLI_PROCESS.poll() is None:
        logger.info("Node.js CLI Server 已在运行 (PID=%d, port=%d)", _CLI_PROCESS.pid, _CLI_PORT)
        return _CLI_PORT

    cli_dir = find_cli_dir()
    node_exe = find_node()

    # 决定入口文件和 runner
    dist_index = cli_dir / "dist" / "index.js"
    src_index = cli_dir / "src" / "index.ts"

    if dist_index.exists():
        # 优先使用编译后的 JS（最稳定）
        entry = str(dist_index)
        cmd = [node_exe, entry]
    elif src_index.exists():
        # fallback：用 tsx 运行 TypeScript
        entry = str(src_index)
        # Windows 上 tsx 是 tsx.cmd，需要用 shell 或找到 .cmd 文件
        if sys.platform == "win32":
            tsx_cmd = cli_dir / "node_modules" / ".bin" / "tsx.cmd"
            if tsx_cmd.is_file():
                cmd = [str(tsx_cmd), entry]
            else:
                # 用 node --import tsx/esm
                cmd = [node_exe, "--import", "tsx/esm", entry]
        else:
            tsx_bin = str(cli_dir / "node_modules" / ".bin" / "tsx")
            if os.path.isfile(tsx_bin):
                cmd = [tsx_bin, entry]
            else:
                cmd = [node_exe, "--import", "tsx/esm", entry]
    else:
        raise FileNotFoundError(
            f"未找到 CLI 入口文件（尝试 {dist_index} 和 {src_index}）"
        )

    if not port:
        port = _find_available_port()

    from engine.file_manager import UserFileManager
    manager = UserFileManager(work_dir=work_dir)
    allowed_dir = str(manager.get_user_dir())

    logger.info("启动 Node.js CLI Server: port=%d, entry=%s, allowed=%s", port, entry, allowed_dir)

    env = dict(os.environ)
    env["NODE_NO_WARNINGS"] = "1"

    cmd = cmd + ["--port", str(port), "--allowed-dir", allowed_dir]

    try:
        _CLI_PROCESS = subprocess.Popen(
            cmd,
            cwd=str(cli_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
    except FileNotFoundError:
        raise RuntimeError(
            f"无法启动 CLI: node 运行器 '{node_exe}' 未找到。"
            "请确保已安装依赖: cd backend/cli && npm install"
        )

    # 等待就绪信号
    deadline = time.time() + 15
    ready = False
    while time.time() < deadline:
        if _CLI_PROCESS.stdout:
            line = _CLI_PROCESS.stdout.readline()
            if line:
                print(f"[CLI] {line.rstrip()}")
                info = _parse_cli_stdout(line)
                if info:
                    port = info.get("port", port)
                    ready = True
                    break
        if _CLI_PROCESS.poll() is not None:
            break
        time.sleep(0.1)

    if not ready:
        # 读取 stderr 用于诊断
        stderr_output = ""
        if _CLI_PROCESS.stderr:
            try:
                stderr_output = _CLI_PROCESS.stderr.read(2000)
            except Exception:
                pass
        raise RuntimeError(
            f"Node.js CLI Server 启动超时或失败。\nstderr: {stderr_output}"
        )

    _CLI_PORT = port
    _CLI_STARTED.set()

    # 配置 cli_executor 的 HTTP 客户端
    from utils.cli_executor import configure as configure_cli
    configure_cli(port)

    logger.info("Node.js CLI Server 就绪 (PID=%d, port=%d)", _CLI_PROCESS.pid, port)
    return port


def stop_cli_server() -> None:
    """停止 Node.js CLI Server

    关键：先让 Node.js 主动调用 closeAll()，由 Node.js 用 taskkill /T /F
    杀光所有 PTY 子进程树（包括 npm run dev 启动的 vite 等 dev server）。
    然后再 taskkill Node.js 本身。否则 Node.js 启动的 vite 进程会变成孤儿
    继续占用端口（如 React 项目的 5173），下次启动会跳到 5174/5176。
    """
    global _CLI_PROCESS, _CLI_PORT
    if _CLI_PROCESS and _CLI_PROCESS.poll() is None:
        pid = _CLI_PROCESS.pid
        port = _CLI_PORT
        logger.info("正在停止 Node.js CLI Server (PID=%d, port=%d)...", pid, port)

        # 1) 先通知 Node.js 主动清理：触发 shutdown() 的等价路径
        #    /reset-agent 端点会调用 termManager.closeAll()，
        #    内部对每个 session 的 PTY 用 taskkill /T /F 杀整棵进程树
        if port:
            try:
                import httpx
                httpx.post(
                    f"http://127.0.0.1:{port}/reset-agent",
                    json={"work_dir": ""},
                    timeout=3,
                )
            except Exception as e:
                logger.debug("reset-agent 调用失败（继续 taskkill）: %s", e)

        # 2) 再强制杀 Node.js 进程本身
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True, timeout=5, check=False,
                )
            else:
                _CLI_PROCESS.send_signal(signal.SIGTERM)
                _CLI_PROCESS.wait(timeout=5)
        except Exception as e:
            logger.warning("停止 CLI Server 异常: %s", e)
        _CLI_PROCESS = None
        _CLI_PORT = 0
        _CLI_STARTED.clear()
        logger.info("Node.js CLI Server 已停止")


def is_cli_running() -> bool:
    return _CLI_PROCESS is not None and _CLI_PROCESS.poll() is None


# ---- 保持兼容的 TerminalManager 类（前端 WebSocket 路由用） ----

class TerminalManager:
    """终端管理器 - 管理 Node.js CLI Server 生命周期

    保持与旧版相同的接口签名，但内部实现完全委托给 Node.js CLI。
    """

    _instance: TerminalManager | None = None
    _lock = threading.Lock()
    # invocation_id → terminal_session_id 映射（Python 端内存表，跨进程不共享）
    # 用于前端通过 toolCallId 找到对应的终端 session
    _invocation_sessions: dict[str, str] = {}

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def get_instance(cls) -> TerminalManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = TerminalManager()
            return cls._instance

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def resolve_agent_session_id(self, work_dir: str | None = None) -> str:
        from engine.file_manager import UserFileManager
        manager = UserFileManager(work_dir=work_dir)
        key = str(manager.get_user_dir())
        return f"agent:{key}"

    def get_agent_session(self, work_dir: str | None = None):
        return _CLI_SESSION_WRAPPER

    @classmethod
    def close_all_sessions(cls) -> list[str]:
        return []

    @classmethod
    def terminate_all_active(cls, action: str = "terminate") -> list[str]:
        return []

    @classmethod
    def clear_runtime_dir(cls) -> int:
        return 0

    @classmethod
    def register_invocation_session(cls, inv_id: str, session_id: str) -> None:
        """记录 invocation_id → terminal_session_id 映射，供前端查询。"""
        if not inv_id or not session_id:
            return
        with cls._lock:
            cls._invocation_sessions[inv_id] = session_id

    @classmethod
    def resolve_invocation_session(cls, inv_id: str) -> str | None:
        """通过 invocation_id 查 terminal session_id，未找到返回 None。"""
        if not inv_id:
            return None
        with cls._lock:
            return cls._invocation_sessions.get(inv_id)


# 占位对象，保持引用兼容
class _SessionWrapper:
    """占位 session wrapper"""
    def is_running(self) -> bool:
        return is_cli_running()

    def force_reset(self) -> None:
        if is_cli_running():
            stop_cli_server()
            start_cli_server()

_CLI_SESSION_WRAPPER = _SessionWrapper()