"""工具执行前后的 hook 注册与分发。

借鉴 Codex 的 PreToolUse/PostToolUse hook 设计：
- PreToolUse: 可重写工具参数（updated_args）或阻断执行（blocked）
- PostToolUse: 可阻断结果回传模型或注入额外上下文

hook 签名：
    async def pre_tool_hook(tool_name: str, args: dict, context: dict) -> dict | None
    返回 None/{} 表示放行；
    返回 {"updated_args": {...}} 表示重写参数后继续执行；
    返回 {"blocked": "原因"} 表示阻断，工具不执行，直接返回错误。

    async def post_tool_hook(tool_name: str, args: dict, result: dict, context: dict) -> dict | None
    返回 None/{} 表示放行；
    返回 {"blocked": "原因"} 表示阻断结果回传，用错误替换 result；
    返回 {"feedback": "消息"} 表示替换模型可见输出。
"""
import asyncio
from typing import Any, Callable, Awaitable, Optional

# hook 注册表
_pre_tool_hooks: list[Callable[[str, dict, dict], Awaitable[Optional[dict]]]] = []
_post_tool_hooks: list[Callable[[str, dict, dict, dict], Awaitable[Optional[dict]]]] = []


def register_pre_tool_hook(fn: Callable[[str, dict, dict], Awaitable[Optional[dict]]]) -> None:
    """注册一个 PreToolUse hook。"""
    _pre_tool_hooks.append(fn)


def register_post_tool_hook(fn: Callable[[str, dict, dict, dict], Awaitable[Optional[dict]]]) -> None:
    """注册一个 PostToolUse hook。"""
    _post_tool_hooks.append(fn)


def clear_hooks() -> None:
    """清空所有 hook（测试用）。"""
    _pre_tool_hooks.clear()
    _post_tool_hooks.clear()


async def run_pre_tool_hooks(tool_name: str, args: dict, context: dict) -> dict:
    """依次执行所有 PreToolUse hook。

    返回:
        {} — 放行
        {"updated_args": {...}} — 重写参数后继续
        {"blocked": "原因"} — 阻断执行
    """
    current_args = args
    for hook in _pre_tool_hooks:
        try:
            ret = await hook(tool_name, current_args, context)
        except Exception as e:
            # hook 出错不影响主流程，记录后继续
            print(f"[pre_tool_hook] error: {e}")
            continue
        if not ret:
            continue
        if "blocked" in ret:
            return {"blocked": ret["blocked"]}
        if "updated_args" in ret:
            current_args = ret["updated_args"]
    return {"updated_args": current_args} if current_args is not args else {}


async def run_post_tool_hooks(tool_name: str, args: dict, result: dict, context: dict) -> dict:
    """依次执行所有 PostToolUse hook。

    返回:
        {} — 放行
        {"blocked": "原因"} — 阻断，用错误替换 result
        {"feedback": "消息"} — 替换模型可见输出
    """
    for hook in _post_tool_hooks:
        try:
            ret = await hook(tool_name, args, result, context)
        except Exception as e:
            print(f"[post_tool_hook] error: {e}")
            continue
        if not ret:
            continue
        if "blocked" in ret:
            return {"blocked": ret["blocked"]}
        if "feedback" in ret:
            return {"feedback": ret["feedback"]}
    return {}


__all__ = [
    "register_pre_tool_hook",
    "register_post_tool_hook",
    "clear_hooks",
    "run_pre_tool_hooks",
    "run_post_tool_hooks",
]
