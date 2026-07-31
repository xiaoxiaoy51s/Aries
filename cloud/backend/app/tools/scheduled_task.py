"""定时任务工具：供 Agent 创建定时任务。

参照 backend 的 agent 工具模式，适配 cloud 后端的工具注册表。
"""
from __future__ import annotations

from typing import Any

from app.database import async_session
from app.service.scheduled_task_service import (
    SCHEDULE_ONCE,
    SCHEDULE_TYPES,
    ScheduledTaskService,
    normalize_create_payload,
)

# OpenAI function-calling schema
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_scheduled_task",
        "description": (
            "创建一个定时任务，到指定时间后自动执行。"
            "支持单次（once）、每天（daily）、固定间隔（interval）三种模式。"
            "任务会在后台调度器中到点自动执行，把 task_content 作为要求发送给 AI。"
            "系统不会自动向手机平台推送结果；若需发送到飞书/QQ/微信，"
            "应在 task_content 中要求 AI 调用 send_message_to_user 并指定 platform。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_content": {
                    "type": "string",
                    "description": "任务的要求说明，到点后会作为用户消息发送给 AI 执行",
                },
                "scheduled_at": {
                    "type": "string",
                    "description": "执行时间，ISO 格式如 2026-07-28T15:30:00,使用命令可查看当前环境的具体时间",
                },
                "title": {
                    "type": "string",
                    "description": "任务标题（可选）",
                },
                "schedule_type": {
                    "type": "string",
                    "enum": list(SCHEDULE_TYPES),
                    "description": "调度类型：once=单次, daily=每天, interval=固定间隔",
                },
                "interval_minutes": {
                    "type": "integer",
                    "description": "间隔分钟数（schedule_type=interval 时必填）",
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "结果写入的会话 ID（可选，不填则新建网页会话）。"
                        "平台会话请填简写：QQ 填 __qq__，微信填 __wechat__，飞书填 __feishu__"
                        "（也可用 _qq_ / _wechat_ / _feishu_）。"
                        "系统会自动加上当前用户邮箱前缀，变为 {邮箱}__qq__ 等形式，避免多用户共用同一会话。"
                    ),
                },
            },
            "required": ["task_content", "scheduled_at", "schedule_type"],
        },
    },
}


async def execute(
    task_content: str,
    scheduled_at: str,
    schedule_type: str = SCHEDULE_ONCE,
    title: str = "",
    interval_minutes: int | None = None,
    session_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """创建定时任务并返回结果文本。"""
    user_id = (context or {}).get("user_id")
    user_email = (context or {}).get("user_email")
    if not user_id:
        return "错误：无法确定当前用户，定时任务创建失败。"

    try:
        payload = normalize_create_payload(
            title=title,
            task_content=task_content,
            scheduled_at=scheduled_at,
            session_id=session_id,
            schedule_type=schedule_type,
            interval_minutes=interval_minutes,
            default_session_id=(context or {}).get("session_id"),
            user_email=user_email,
        )
    except ValueError as e:
        return f"创建失败：{e}"

    async with async_session() as db:
        task_id = await ScheduledTaskService.create_task(
            db,
            user_id,
            title=payload["title"],
            task_content=payload["task_content"],
            scheduled_at=payload["scheduled_at"],
            session_id=payload["session_id"],
            schedule_type=payload["schedule_type"],
            interval_minutes=payload["interval_minutes"],
            auto_delete=payload["auto_delete"],
        )

    return (
        f"定时任务已创建（ID={task_id}）。\n"
        f"标题：{payload['title'] or '(无)'}\n"
        f"类型：{payload['schedule_type']}\n"
        f"执行时间：{payload['scheduled_at']}\n"
        f"会话：{payload['session_id'] or '(新建)'}"
    )
