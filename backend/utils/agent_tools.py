"""Agent 基础工具 - 委托给 file_manager / cli_executor 等核心能力

这些工具的 schema 必须在每次会话开始时注册到 LLM 工具列表中，
否则 AI 看不到 write_file / read_file 等基础文件操作能力，
会错误地选择 xlsx、pdf 等领域技能来写入纯文本文件。
"""
from __future__ import annotations

import asyncio
import traceback
from typing import Any

from db.scheduled_task import (
    SCHEDULE_DAILY,
    SCHEDULE_INTERVAL,
    SCHEDULE_ONCE,
    create_task,
    infer_notify_type,
    normalize_task_create_payload,
)
from utils.time_utils import local_iso_to_display


def get_tool_definitions() -> list[dict]:
    """返回核心基础工具的 OpenAI 风格 function calling 定义列表。

    所有工具 schema 统一管理在 backend/tools/*.json 文件中，
    通过 tools 包自动加载。delegate_to_subagent 由 skills_manager.py 单独注入。
    """
    try:
        from tools import get_tool_definitions as load_tool_defs
        all_defs = load_tool_defs()
        # 过滤掉 delegate_to_subagent（由 skills_manager.py 单独注入）
        return [
            d for d in all_defs
            if d.get("function", {}).get("name") != "delegate_to_subagent"
        ]
    except Exception as exc:
        print(f"Failed to load tool definitions from tools/: {exc}")
        return []


def _schedule_type_label(schedule_type: str) -> str:
    return {
        SCHEDULE_ONCE: "单次",
        SCHEDULE_DAILY: "每天",
        SCHEDULE_INTERVAL: "间隔重复",
    }.get(schedule_type, schedule_type)


def _notify_label(notify_type: str) -> str:
    return {
        "wechat": "微信",
        "qq": "QQ",
        "feishu": "飞书",
        "none": "网页会话",
    }.get(notify_type, notify_type)


def _handle_create_scheduled_task(
    arguments: dict[str, Any],
    session_id: str | None = None,
) -> dict[str, Any]:
    try:
        payload = normalize_task_create_payload(
            title=str(arguments.get("title") or ""),
            task_content=str(arguments.get("task_content") or ""),
            scheduled_at=arguments.get("scheduled_at"),
            session_id=arguments.get("session_id"),
            schedule_type=str(arguments.get("schedule_type") or SCHEDULE_ONCE),
            interval_minutes=arguments.get("interval_minutes"),
            default_session_id=session_id,
        )
    except ValueError as exc:
        msg = str(exc)
        return {"success": False, "error": msg, "output": msg}

    try:
        task_id = create_task(**payload)

        effective_session = payload["session_id"]
        schedule_type = payload["schedule_type"]
        scheduled_at = payload["scheduled_at"]
        interval_mins = payload["interval_minutes"]
        resolved_notify = infer_notify_type(effective_session)

        lines = [
            f"已创建定时任务 #{task_id}",
            f"title：{payload['title'] or '（无标题）'}",
            f"task_content：{payload['task_content'][:80]}{'…' if len(payload['task_content']) > 80 else ''}",
            f"schedule_type：{_schedule_type_label(schedule_type)}",
            f"scheduled_at：{local_iso_to_display(scheduled_at)}",
        ]
        if schedule_type == SCHEDULE_INTERVAL and interval_mins:
            lines.append(f"interval_minutes：{interval_mins}")
        lines.append(f"session_id：{effective_session or '（新建网页会话）'}")
        lines.append(f"结果推送：{_notify_label(resolved_notify)}")
        lines.append(f"执行后自动删除：{'是' if payload.get('auto_delete') else '否'}")
        output = "\n".join(lines)

        return {
            "success": True,
            "error": "",
            "output": output,
            "task_id": task_id,
            **payload,
            "notify_type": resolved_notify,
        }
    except ValueError as exc:
        msg = str(exc)
        return {"success": False, "error": msg, "output": msg}
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "output": traceback.format_exc(),
        }


def _get_file_manager(work_dir: str | None) -> Any:
    from utils.file_manager import FileManagerTool
    return FileManagerTool(work_dir=work_dir)


def _handle_read_skill_file(arguments: dict[str, Any]) -> dict[str, Any]:
    skill_name = str(arguments.get("skill_name") or "").strip()
    file_path = str(arguments.get("file_path") or "").strip()
    encoding = str(arguments.get("encoding") or "utf-8")
    if not skill_name or not file_path:
        return {
            "success": False,
            "error": "缺少 skill_name 或 file_path 参数",
            "output": "缺少 skill_name 或 file_path 参数",
        }
    try:
        from utils.skills_manager import get_skill_by_name
        entry = get_skill_by_name(skill_name)
        if entry is None:
            return {
                "success": False,
                "error": f"技能不存在: {skill_name}",
                "output": f"技能不存在: {skill_name}",
            }
        target = (entry.skill_path / file_path).resolve()
        if not str(target).startswith(str(entry.skill_path.resolve())):
            return {
                "success": False,
                "error": "非法的文件路径（越界）",
                "output": "非法的文件路径（越界）",
            }
        if not target.exists() or not target.is_file():
            return {
                "success": False,
                "error": f"技能文件不存在: {file_path}",
                "output": f"技能文件不存在: {file_path}",
            }
        content = target.read_text(encoding=encoding, errors="replace")
        return {
            "success": True,
            "error": "",
            "output": content,
            "file_path": str(target),
            "skill": skill_name,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "output": traceback.format_exc(),
        }


async def _handle_send_file_to_user(
    kwargs: dict,
    work_dir: str = "",
    session_id: str | None = None,
) -> dict:
    """将文件发送到用户当前使用的平台（飞书/QQ）。

    根据 session_id 判断平台：
    - __feishu__ → 飞书文件发送
    - __qq__ → QQ 文件发送
    - __wechat__ → 微信暂不支持
    - 其他 → 网页会话不支持
    """
    from pathlib import Path

    file_path = str(kwargs.get("file_path") or "").strip()
    if not file_path:
        return {"success": False, "error": "缺少 file_path 参数", "output": "缺少 file_path 参数"}

    # 解析文件路径（支持相对路径）
    raw_path = Path(file_path)
    if not raw_path.is_absolute() and work_dir:
        raw_path = Path(work_dir) / raw_path
    resolved = str(raw_path.expanduser())

    if not Path(resolved).is_file():
        return {"success": False, "error": f"文件不存在: {resolved}", "output": f"文件不存在: {resolved}"}

    # 判断平台
    sid = (session_id or "").strip()
    platform = None
    if sid == "__feishu__":
        platform = "feishu"
    elif sid == "__qq__":
        platform = "qq"
    elif sid == "__wechat__":
        platform = "wechat"
    elif sid.startswith("__"):
        platform = sid.strip("__")

    if platform == "feishu":
        from services.feishu_file import send_file_to_feishu
        ok = send_file_to_feishu(resolved)
        if ok:
            return {"success": True, "error": "", "output": f"已通过飞书发送文件: {Path(resolved).name}"}
        return {"success": False, "error": "飞书文件发送失败", "output": "飞书文件发送失败，请检查 bot 是否在线及文件大小"}

    if platform == "qq":
        from services.qq_file import send_file_to_qq
        ok = await send_file_to_qq(resolved)
        if ok:
            return {"success": True, "error": "", "output": f"已通过QQ发送文件: {Path(resolved).name}"}
        return {"success": False, "error": "QQ文件发送失败", "output": "QQ文件发送失败，请检查 bot 是否在线及文件大小"}

    if platform == "wechat":
        return {"success": False, "error": "微信暂不支持发送文件", "output": "微信平台暂不支持发送文件功能"}

    return {"success": False, "error": "当前会话不支持发送文件", "output": "网页会话不支持发送文件，请在飞书/QQ对话中使用"}


def execute(tool: str = "", work_dir: str = "", session_id: str | None = None, invocation_id: str | None = None, **kwargs) -> dict:
    """执行核心基础工具（同步入口，保持兼容）。"""
    try:
        if tool == "cli_executor":
            from utils.cli_executor import CLIExecutor
            executor = CLIExecutor(work_dir=work_dir)
            cli_kwargs = dict(kwargs)
            if work_dir and "working_dir" not in cli_kwargs:
                cli_kwargs["working_dir"] = work_dir
            if invocation_id and "invocation_id" not in cli_kwargs:
                cli_kwargs["invocation_id"] = invocation_id
            return executor.execute(**cli_kwargs)

        return _execute_sync(tool, work_dir, session_id, invocation_id, kwargs)
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "output": traceback.format_exc(),
        }


async def execute_async(
    tool: str = "",
    args: dict | None = None,
    work_dir: str = "",
    session_id: str | None = None,
    invocation_id: str | None = None,
    cancel_event: asyncio.Event | None = None,
    **kwargs,
) -> dict:
    """执行核心基础工具（异步入口，支持中断）。

    cli_executor 会响应 cancel_event 和用户点击的 detach/cancel 信号。
    其他工具委托给同步 execute 并在线程池中运行。
    """
    try:
        if tool == "cli_executor":
            from utils.cli_executor import CLIExecutor
            executor = CLIExecutor(work_dir=work_dir)
            cli_kwargs = dict(args) if args else {}
            if work_dir and "working_dir" not in cli_kwargs:
                cli_kwargs["working_dir"] = work_dir
            if invocation_id and "invocation_id" not in cli_kwargs:
                cli_kwargs["invocation_id"] = invocation_id
            cli_kwargs["cancel_event"] = cancel_event
            return await executor.execute_async(**cli_kwargs)

        if tool == "send_file_to_user":
            merged_kwargs = dict(args) if args else {}
            merged_kwargs.update(kwargs)
            return await _handle_send_file_to_user(merged_kwargs, work_dir=work_dir, session_id=session_id)

        loop = asyncio.get_running_loop()
        merged_kwargs = dict(args) if args else {}
        merged_kwargs.update(kwargs)
        return await loop.run_in_executor(
            None,
            lambda: _execute_sync(tool, work_dir, session_id, invocation_id, merged_kwargs),
        )
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "output": traceback.format_exc(),
        }


def _execute_sync(tool: str, work_dir: str, session_id: str | None, invocation_id: str | None, kwargs: dict) -> dict:
    """非 cli_executor 工具的同步执行。"""
    try:
        if tool == "read_skill_file":
            return _handle_read_skill_file(kwargs)

        if tool == "create_scheduled_task":
            return _handle_create_scheduled_task(kwargs, session_id=session_id)

        if tool == "write_agent_memory":
            from memory.agent_memory import write_agent_memory
            return write_agent_memory(work_dir, str(kwargs.get("content") or ""))

        # 多策略编辑工具（#4）
        if tool in ("replace_string", "multi_replace_string", "apply_patch"):
            from utils.edit_tools import EditTools
            et = EditTools(work_dir=work_dir)
            return et.execute(tool, kwargs)

        fm = _get_file_manager(work_dir)

        if tool == "read_file":
            return fm.execute_read_file(**kwargs)
        if tool == "write_file":
            return fm.execute_write_file(**kwargs)
        if tool == "edit_file":
            return fm.execute_edit_file(**kwargs)
        if tool == "list_files":
            return fm.execute_list_files(**kwargs)
        if tool == "search_file":
            return fm.execute_search_file(**kwargs)

        # 非核心工具：转发到 skills_manager 执行（如 playwright、web_search 等 skill 工具）
        from utils.skills_manager import execute_tool as execute_skill_tool
        result = execute_skill_tool(tool, kwargs, work_dir=work_dir, session_id=session_id, invocation_id=invocation_id)
        if result is not None:
            return result

        return {
            "success": False,
            "error": f"Unknown tool: {tool}",
            "output": f"未知的核心工具: {tool}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "output": traceback.format_exc(),
        }


__all__ = [
    "get_tool_definitions",
    "execute",
    "execute_async",
]
