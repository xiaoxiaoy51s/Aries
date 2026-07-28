"""工具注册表：管理所有可用工具的 schema 和执行函数。"""
from __future__ import annotations

import inspect
import json
from typing import Any

from app.tools import shell, web_search

# 工具注册表: name -> (schema, executor)
_REGISTRY: dict[str, tuple[dict, Any]] = {}


def _register():
    _REGISTRY["web_search"] = (web_search.TOOL_SCHEMA, web_search.execute)
    _REGISTRY["run_shell"] = (shell.TOOL_SCHEMA_RUN, shell.execute)
    _REGISTRY["stop_process"] = (shell.TOOL_SCHEMA_STOP, shell.stop_process)
    _REGISTRY["list_processes"] = (shell.TOOL_SCHEMA_LIST, shell.list_processes)


_register()


def get_tool_schemas() -> list[dict]:
    """返回所有工具的 OpenAI function schema 列表。"""
    return [v[0] for v in _REGISTRY.values()]


async def execute_tool(
    name: str,
    arguments: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> str:
    """执行指定工具，返回结果文本。

    Args:
        name: 工具名称
        arguments: 工具参数
        context: 调用上下文（user_email, session_id 等），会传递给支持 context 参数的工具
    """
    if name not in _REGISTRY:
        return f"未知工具: {name}"
    executor = _REGISTRY[name][1]
    try:
        # 检查 executor 是否接受 context 关键字参数
        sig = inspect.signature(executor)
        if "context" in sig.parameters:
            return await executor(**arguments, context=context or {})
        return await executor(**arguments)
    except Exception as e:
        return f"工具执行错误: {e}"


def parse_tool_arguments(raw: str) -> dict[str, Any]:
    """安全解析工具参数 JSON 字符串。"""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"_raw": raw}
