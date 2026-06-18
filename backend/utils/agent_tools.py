"""Agent 基础工具 - 委托给 file_manager / cli_executor 等核心能力

这些工具的 schema 必须在每次会话开始时注册到 LLM 工具列表中，
否则 AI 看不到 write_file / read_file 等基础文件操作能力，
会错误地选择 xlsx、pdf 等领域技能来写入纯文本文件。
"""
from __future__ import annotations

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
    """返回核心基础工具的 OpenAI 风格 function calling 定义列表。"""
    definitions: list[dict] = []

    try:
        from utils.file_manager import FileManagerTool
        fm = FileManagerTool()
        definitions.extend(fm.get_tool_definitions())
    except Exception as exc:
        print(f"Failed to load file_manager tool definitions: {exc}")

    try:
        from utils.cli_executor import CLIExecutor
        executor = CLIExecutor()
        definitions.append(executor.get_tool_definition())
    except Exception as exc:
        print(f"Failed to load cli_executor tool definition: {exc}")

    try:
        from utils.skills_manager import get_skill_by_name
        definitions.append(_build_read_skill_file_definition())
    except Exception:
        pass

    definitions.append(_build_create_scheduled_task_definition())

    return definitions


def _build_read_skill_file_definition() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "read_skill_file",
            "description": (
                "读取指定技能目录中的文件内容。"
                "当技能 SKILL.md 引用了其他文件（如 prompt 模板、脚本、说明文档）时使用。"
                "路径相对于技能目录。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "技能目录名（与 ~/.Aries/skills/available/ 下的子目录名一致）。",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "技能目录内的相对文件路径，例如 'templates/prompt.md'。",
                    },
                    "encoding": {
                        "type": "string",
                        "default": "utf-8",
                    },
                },
                "required": ["skill_name", "file_path"],
                "additionalProperties": False,
            },
        },
    }


def _build_create_scheduled_task_definition() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "create_scheduled_task",
            "description": (
                "创建定时任务。字段与 scheduled_tasks 表一致。"
                "到达 scheduled_at 后，系统按 task_content 自动运行 AI，"
                "结果写入 session_id 对应会话（网页 UUID 或 __wechat__/__qq__/__feishu__）。"
                "notify_type 仅在未传 session_id 时用于指定手机推送平台；"
                "均未指定时默认使用 system prompt 中的当前 session_id。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "任务名称（对应 title 字段）。",
                    },
                    "task_content": {
                        "type": "string",
                        "description": "要求说明（对应 task_content 字段），到时后 AI 执行的指令。",
                    },
                    "schedule_type": {
                        "type": "string",
                        "enum": [SCHEDULE_ONCE, SCHEDULE_DAILY, SCHEDULE_INTERVAL],
                        "default": SCHEDULE_ONCE,
                        "description": "执行类型（对应 schedule_type）：once=单次，daily=每天，interval=间隔重复。",
                    },
                    "scheduled_at": {
                        "type": "string",
                        "description": (
                            "执行时间（对应 scheduled_at），本地 ISO 格式如 2026-06-14T15:30:00。"
                            "单次/每天必填；interval 可省略（默认当前时间 + interval_minutes）。"
                        ),
                    },
                    "interval_minutes": {
                        "type": "integer",
                        "description": "间隔分钟数（对应 interval_minutes），schedule_type=interval 时必填。",
                    },
                    "session_id": {
                        "type": "string",
                        "description": (
                            "结果推送会话 ID（对应 session_id）。"
                            "网页会话填 UUID；手机推送填 __wechat__/__qq__/__feishu__。"
                            "不传则默认当前会话。"
                        ),
                    },
                    "notify_type": {
                        "type": "string",
                        "enum": ["wechat", "qq", "feishu"],
                        "description": (
                            "手机推送平台。用户明确指定微信/QQ/飞书回复时填写；"
                            "仅在未传 session_id 时生效，会自动映射为 __wechat__ 等。"
                        ),
                    },
                },
                "required": ["title", "task_content"],
                "additionalProperties": False,
            },
        },
    }


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
            notify_type=arguments.get("notify_type"),
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


def execute(tool: str = "", work_dir: str = "", session_id: str | None = None, invocation_id: str | None = None, **kwargs) -> dict:
    """执行核心基础工具。"""
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

        if tool == "read_skill_file":
            return _handle_read_skill_file(kwargs)

        if tool == "create_scheduled_task":
            return _handle_create_scheduled_task(kwargs, session_id=session_id)

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
