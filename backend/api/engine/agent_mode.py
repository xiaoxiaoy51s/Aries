"""兼容层：从拆分后的小模块重新导出，保持旧的 import 路径可用。"""
from .confirmation import (
    CONFIRMATION_TIMEOUT_SECONDS,
    register_confirmation_wait,
    resolve_confirmation,
    wait_for_confirmation,
    wait_for_confirmation_with_cancel,
)
from .todo_handler import (
    get_todos,
    update_todos,
    clear_todos,
    format_todos_for_context,
    purge_todo_messages,
)
from .system_prompt import (
    build_agent_system_prompt_parts,
    build_agent_system_prompt,
    get_agent_skills_and_tools,
)
from .stream_constants import (
    MAX_TOOL_ROUNDS,
    REPEAT_TOOL_LIMIT,
    LLM_CONNECT_TIMEOUT_SECONDS,
    LLM_READ_TIMEOUT_SECONDS,
    LLM_WRITE_TIMEOUT_SECONDS,
    TOOL_EXECUTION_TIMEOUT_SECONDS,
)
from .stream_handler import (
    stream_agent_mode,
)

__all__ = [
    # confirmation
    "CONFIRMATION_TIMEOUT_SECONDS",
    "register_confirmation_wait",
    "resolve_confirmation",
    "wait_for_confirmation",
    "wait_for_confirmation_with_cancel",
    # todo
    "get_todos",
    "update_todos",
    "clear_todos",
    "format_todos_for_context",
    "purge_todo_messages",
    # system_prompt
    "build_agent_system_prompt_parts",
    "build_agent_system_prompt",
    "get_agent_skills_and_tools",
    # stream
    "MAX_TOOL_ROUNDS",
    "REPEAT_TOOL_LIMIT",
    "LLM_CONNECT_TIMEOUT_SECONDS",
    "LLM_READ_TIMEOUT_SECONDS",
    "LLM_WRITE_TIMEOUT_SECONDS",
    "TOOL_EXECUTION_TIMEOUT_SECONDS",
    "stream_agent_mode",
]
