"""Shell 执行工具：在沙箱内执行 bash 命令。

提供两个工具：
1. run_shell - 执行命令（同步或后台）
2. stop_process - 停止后台进程

安全机制：
- 每个用户有独立工作区（按邮箱隔离），命令只能在工作区内操作
- 危险命令黑名单拦截（rm -rf /、dd、mkfs 等）
- bwrap mount namespace 隔离（可用时）/ cd+HOME 回退
- 同步命令有超时限制
- 后台进程在对话流式结束后自动终止
- 输出截断防止过长
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.tools.sandbox import (
    build_command_args,
    get_user_workspace,
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
    """执行 shell 命令。

    Args:
        command: bash 命令
        background: 是否后台运行
        timeout: 超时秒数（0 表示无超时）
        working_dir: 工作区内子目录（相对路径）
        context: 调用上下文（含 user_email, session_id）
    """
    user_email = (context or {}).get("user_email", "")
    session_id = (context or {}).get("session_id", "")
    if not user_email:
        return "错误：无法确定用户工作区"

    # 1. 安全校验
    is_safe, reason = validate_command(command)
    if not is_safe:
        return f"命令被拒绝：{reason}"

    # 2. 获取工作区
    workspace = get_user_workspace(user_email)

    # 3. 验证 working_dir（必须在工作区内）
    actual_workdir = workspace
    if working_dir:
        is_valid, wd_reason, actual_workdir = validate_working_dir(workspace, working_dir)
        if not is_valid:
            return f"工作目录无效：{wd_reason}"

    # 4. 构建命令
    if timeout == 0:
        timeout = 3600  # 0 表示无超时，实际给 1 小时上限
    timeout = min(max(timeout, 5), 3600)  # 限制 5~3600 秒

    args = build_command_args(
        command=command,
        workspace=actual_workdir,
        timeout=timeout,
        background=background,
    )

    # 5. 执行
    try:
        if background:
            # 后台模式：读取输出的 PID
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode("utf-8", errors="replace").strip()
            if not output:
                err = stderr.decode("utf-8", errors="replace").strip()
                return f"后台进程启动失败：{err}" if err else "后台进程启动失败"

            try:
                pid = int(output.split("\n")[0])
            except ValueError:
                return f"无法解析进程 PID：{output}"

            # 注册进程（关联 session_id，用于流式结束后清理）
            output_file = str(actual_workdir / ".bg_output.log")
            register_bg_process(pid, command, actual_workdir, output_file, session_id)

            return f"后台进程已启动 (PID: {pid})\n命令: {command}\n输出日志: .bg_output.log"

        else:
            # 同步模式
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout + 5,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return f"命令执行超时（{timeout}秒）"

            out = stdout.decode("utf-8", errors="replace")
            err = stderr.decode("utf-8", errors="replace")
            exit_code = proc.returncode

            # 截断输出
            max_out = settings.SHELL_MAX_OUTPUT
            if len(out) > max_out:
                out = out[:max_out] + f"\n...(输出已截断，共 {len(out)} 字符)"

            # 组装结果
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

    except FileNotFoundError as e:
        return f"执行环境错误：{e}"
    except Exception as e:
        return f"命令执行错误：{e}"


async def stop_process(
    pid: int,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    """停止后台进程。"""
    success = kill_process(pid)
    if success:
        return f"进程 {pid} 已停止"
    return f"进程 {pid} 停止失败（可能已结束）"


async def list_processes(
    *,
    context: dict[str, Any] | None = None,
) -> str:
    """列出所有后台进程。"""
    procs = list_bg_processes()
    if not procs:
        return "当前没有后台进程"

    lines = [f"后台进程列表（共 {len(procs)} 个）:"]
    for p in procs:
        status = "运行中" if p["running"] else "已结束"
        lines.append(f"  PID {p['pid']} [{status}]: {p['command']}")
    return "\n".join(lines)
