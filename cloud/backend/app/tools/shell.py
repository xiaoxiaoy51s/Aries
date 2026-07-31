"""Shell 执行工具：在沙箱内执行命令。

参考 cli_executor.py 的设计：
- 用 subprocess.Popen 执行（同步），通过 asyncio.to_thread 避免阻塞
- Windows 上用 Git Bash，Linux 上直接 shell=True
- 后台进程在对话结束后自动终止
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from typing import Any

from app.config.settings import settings
from app.tools.sandbox import (
    find_bash,
    get_tool_workspace,
    kill_process,
    list_bg_processes,
    register_bg_process,
    validate_command,
    validate_working_dir,
)

# ============ 工具 Schema ============

TOOL_SCHEMA_RUN = {
    "type": "function",
    "function": {
        "name": "run_shell",
        "description": (
            "在沙箱工作区内执行 bash 命令。可以用于创建/编辑/删除文件、运行脚本等。"
            "命令在用户专属工作区目录内执行，无法访问工作区外的文件。"
            "需要持续运行的命令（如 web server）可设置 background=true，"
            "对话结束后后台进程会自动终止。"
            "危险命令（rm -rf /、dd、mkfs 等）会被拦截。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 bash 命令",
                },
                "background": {
                    "type": "boolean",
                    "description": "是否后台运行。仅用于必须持续运行的进程（如 dev server）。后台进程在对话结束后自动终止。",
                    "default": False,
                },
                "timeout": {
                    "type": "integer",
                    "description": "命令超时时间（秒），默认 30。网络操作建议设为 90 或更长。使用 0 表示无超时。",
                    "default": 30,
                },
                "working_dir": {
                    "type": "string",
                    "description": "工作区内的子目录路径（相对路径）。留空时在工作区根目录执行。",
                    "default": "",
                },
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
}

TOOL_SCHEMA_STOP = {
    "type": "function",
    "function": {
        "name": "stop_process",
        "description": "停止一个后台运行的进程。",
        "parameters": {
            "type": "object",
            "properties": {
                "pid": {
                    "type": "integer",
                    "description": "要停止的进程 ID",
                },
            },
            "required": ["pid"],
            "additionalProperties": False,
        },
    },
}

TOOL_SCHEMA_LIST = {
    "type": "function",
    "function": {
        "name": "list_processes",
        "description": "列出当前所有后台运行的进程。",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
}


# ============ 执行函数 ============

async def execute(
    command: str,
    background: bool = False,
    timeout: int = 30,
    working_dir: str = "",
    *,
    context: dict[str, Any] | None = None,
) -> str:
    """执行 shell 命令。"""
    import logging
    logger = logging.getLogger(__name__)

    user_email = (context or {}).get("user_email", "")
    session_id = (context or {}).get("session_id", "")
    logger.info(f"run_shell: user={user_email}, session={session_id}, cmd={command[:100]}")

    if not user_email:
        return "错误：无法确定用户工作区（context 中无 user_email）"

    # 1. 安全校验
    is_safe, reason = validate_command(command)
    if not is_safe:
        return f"命令被拒绝：{reason}"

    # 2. 获取会话工作目录
    workspace, ws_err = get_tool_workspace(context)
    if ws_err or workspace is None:
        return f"工作区不可用：{ws_err or '未知错误'}"
    logger.info(f"workspace: {workspace}")

    # 3. 验证 working_dir
    if working_dir:
        is_valid, wd_reason, actual_workdir = validate_working_dir(workspace, working_dir)
        if not is_valid:
            return f"工作目录无效：{wd_reason}"
    else:
        actual_workdir = workspace

    # 4. 超时处理
    if timeout == 0:
        timeout = 3600
    timeout = min(max(timeout, 5), 3600)

    cwd = str(actual_workdir)
    logger.info(f"cwd: {cwd}, background={background}, timeout={timeout}")

    try:
        if background:
            return await _run_background(command, cwd, session_id)
        else:
            return await _run_sync(command, cwd, timeout)
    except Exception as e:
        import traceback
        return f"命令执行错误：{type(e).__name__}: {e}\n{traceback.format_exc()}"


async def _run_sync(command: str, cwd: str, timeout: int) -> str:
    """同步执行命令，等待完成。用 subprocess.Popen 避免 Windows asyncio 子进程问题。"""
    return await asyncio.to_thread(_run_sync_blocking, command, cwd, timeout)


def _run_sync_blocking(command: str, cwd: str, timeout: int) -> str:
    """同步阻塞执行命令。"""
    if sys.platform == "win32":
        bash = find_bash()
        if not bash:
            return "错误：Windows 上未找到 Git Bash，请安装 Git"
        proc = subprocess.Popen(
            [bash, "-c", command],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    else:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return f"命令执行超时（{timeout}秒）"

    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    exit_code = proc.returncode

    max_out = settings.SHELL_MAX_OUTPUT
    if len(out) > max_out:
        out = out[:max_out] + f"\n...(输出已截断，共 {len(out)} 字符)"

    result_parts = []
    if out:
        result_parts.append(out)
    if err:
        if len(err) > max_out // 2:
            err = err[:max_out // 2] + "\n...(stderr 已截断)"
        result_parts.append(f"[stderr]\n{err}")
    if exit_code != 0:
        result_parts.append(f"[退出码: {exit_code}]")

    return "\n".join(result_parts) if result_parts else "命令执行完成（无输出）"


async def _run_background(command: str, cwd: str, session_id: str) -> str:
    """后台执行命令，返回 PID。"""
    return await asyncio.to_thread(_run_background_blocking, command, cwd, session_id)


def _run_background_blocking(command: str, cwd: str, session_id: str) -> str:
    """同步阻塞启动后台进程。"""
    output_file = os.path.join(cwd, ".bg_output.log")

    if sys.platform == "win32":
        bash = find_bash()
        if not bash:
            return "错误：Windows 上未找到 Git Bash"
        full_cmd = f'nohup bash -c {_shell_quote(command)} > "{output_file}" 2>&1 & echo $!'
        proc = subprocess.Popen(
            [bash, "-c", full_cmd],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    else:
        full_cmd = f'nohup {command} > "{output_file}" 2>&1 & echo $!'
        proc = subprocess.Popen(
            full_cmd,
            shell=True,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

    try:
        stdout, _ = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        return "后台进程启动超时"

    output = stdout.decode("utf-8", errors="replace").strip()
    if not output:
        return "后台进程启动失败"

    try:
        pid = int(output.split("\n")[0])
    except ValueError:
        return f"无法解析进程 PID：{output}"

    from pathlib import Path
    register_bg_process(pid, command, Path(cwd), session_id)
    return f"后台进程已启动 (PID: {pid})\n命令: {command}\n输出日志: .bg_output.log"


def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


async def stop_process(
    pid: int,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    success = kill_process(pid)
    return f"进程 {pid} 已停止" if success else f"进程 {pid} 停止失败（可能已结束）"


async def list_processes(
    *,
    context: dict[str, Any] | None = None,
) -> str:
    procs = list_bg_processes()
    if not procs:
        return "当前没有后台进程"
    lines = [f"后台进程列表（共 {len(procs)} 个）:"]
    for p in procs:
        status = "运行中" if p["running"] else "已结束"
        lines.append(f"  PID {p['pid']} [{status}]: {p['command']}")
    return "\n".join(lines)
