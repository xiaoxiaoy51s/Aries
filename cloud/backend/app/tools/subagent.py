"""子 Agent 委派工具（由 chat_service 特殊路径并行执行，此处仅提供 schema）。"""

from __future__ import annotations

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "delegate_to_subagent",
        "description": (
            "委派任务给一个独立的子 Agent。子 Agent 拥有独立上下文窗口和工具集，"
            "适合复杂多步任务或保护主上下文不被淹没的场景。\n\n"
            "重要约束：\n"
            "- 子 Agent 看不到当前对话历史，你必须在 task 中提供完成任务所需的全部信息\n"
            "- 子 Agent 一次性返回最终结果，不能交互式追问\n"
            "- 同一轮 tool_calls 中可以并发委派多个不同子 Agent\n\n"
            "参数说明：\n"
            "- subagent_name：必填，目标子 Agent 名称（来自 Available Subagents 路由表中的 name）\n"
            "- task：必填，完整任务描述\n"
            "- isolation：选填，工作空间隔离模式（默认空=共享目录；\"worktree\"=git worktree 隔离）\n\n"
            "何时使用：复杂多步任务、需要独立上下文窗口、可并行的独立查询。\n"
            "何时不要使用：简单任务、答案已知、必须串行依赖前序结果的任务。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subagent_name": {
                    "type": "string",
                    "description": "目标子 Agent 名称（来自 Available Subagents 路由表中的 name）。不能为空字符串。",
                },
                "task": {
                    "type": "string",
                    "description": "完整任务描述，必须详尽，包含子 Agent 完成任务所需的全部上下文。不能为空字符串。",
                },
                "isolation": {
                    "type": "string",
                    "enum": ["", "worktree"],
                    "description": (
                        "工作空间隔离模式。默认空字符串=共享工作目录；"
                        "'worktree'=创建 git worktree 隔离工作空间"
                    ),
                },
            },
            "required": ["subagent_name", "task"],
            "additionalProperties": True,
        },
    },
}


async def execute(*, subagent_name: str = "", task: str = "", isolation: str = "", context: dict | None = None) -> str:
    """正常 registry 路径不应走到这里；chat_service 会拦截并行执行。"""
    return (
        "delegate_to_subagent 必须由主 Agent 的并行委派路径处理。"
        "若看到此消息，说明调用链路异常，请重试。"
    )
