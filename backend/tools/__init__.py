"""
工具定义加载器 - 从 JSON 文件加载所有核心工具的 schema 定义。

这些 JSON 文件集中管理工具的 OpenAI function calling schema，
便于统一查看和维护。运行时通过此模块加载并返回给 agent_tools.py 等调用方。

使用方式：
    from tools import get_tool_definitions, get_tool_by_name
    tools = get_tool_definitions()
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_TOOLS_DIR = Path(__file__).parent

# 工具定义缓存
_tool_definitions: list[dict[str, Any]] | None = None
_tool_map: dict[str, dict[str, Any]] | None = None


def _get_json_files() -> list[Path]:
    """获取 tools 目录下所有 .json 文件（按名称排序）。"""
    return sorted(_TOOLS_DIR.glob("*.json"))


def _load_all() -> list[dict[str, Any]]:
    """加载所有 JSON 文件中的工具定义。"""
    definitions: list[dict[str, Any]] = []
    for fpath in _get_json_files():
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("type") == "function":
                definitions.append(data)
            elif isinstance(data, list):
                # 兼容列表格式
                for item in data:
                    if isinstance(item, dict) and item.get("type") == "function":
                        definitions.append(item)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Failed to load tool definition from {fpath.name}: {exc}")
    return definitions


def get_tool_definitions() -> list[dict[str, Any]]:
    """返回所有工具定义（OpenAI function calling 格式）。"""
    global _tool_definitions
    if _tool_definitions is None:
        _tool_definitions = _load_all()
    return list(_tool_definitions)


def get_tool_by_name(name: str) -> dict[str, Any] | None:
    """按工具名称查找工具定义。"""
    global _tool_map
    if _tool_map is None:
        _tool_map = {}
        for tool in get_tool_definitions():
            func_name = tool.get("function", {}).get("name", "")
            if func_name:
                _tool_map[func_name] = tool
    return _tool_map.get(name)


def reload() -> list[dict[str, Any]]:
    """重新加载所有工具定义（清空缓存）。"""
    global _tool_definitions, _tool_map
    _tool_definitions = None
    _tool_map = None
    return get_tool_definitions()


def get_tool_names() -> list[str]:
    """返回所有工具名称列表。"""
    return [
        t.get("function", {}).get("name", "")
        for t in get_tool_definitions()
        if t.get("function", {}).get("name")
    ]


__all__ = [
    "get_tool_definitions",
    "get_tool_by_name",
    "get_tool_names",
    "reload",
]