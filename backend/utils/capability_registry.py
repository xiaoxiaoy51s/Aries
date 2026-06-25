"""Subagent 工具定义（delegate_to_subagent）。"""
from __future__ import annotations

from typing import Any

DELEGATE_TO_SUBAGENT_TOOL_NAME = "delegate_to_subagent"


def get_delegate_to_subagent_tool_definition() -> dict[str, Any]:
    """主 Agent 用来委派任务给子 Agent 的工具。

    schema 从 backend/tools/delegate_to_subagent.json 加载，便于统一管理。
    """
    from tools import get_tool_by_name
    tool = get_tool_by_name(DELEGATE_TO_SUBAGENT_TOOL_NAME)
    if tool:
        return tool
    # JSON 加载失败时的兜底
    return {
        "type": "function",
        "function": {
            "name": DELEGATE_TO_SUBAGENT_TOOL_NAME,
            "description": "委派任务给一个独立的子 Agent。",
            "parameters": {
                "type": "object",
                "properties": {
                    "subagent_name": {"type": "string", "description": "子 Agent 名称"},
                    "task": {"type": "string", "description": "任务描述"},
                },
                "required": ["subagent_name", "task"],
            },
        },
    }
