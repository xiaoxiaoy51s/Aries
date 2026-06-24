"""Capability Registry - 统一检索 skill / mcp / subagent 三类能力

设计目标：
1. 给主 Agent 提供 `capability_search(query, kinds?)` 工具，让它发现系统中**全部**能力，
   不受 enabled / available 状态过滤（这样主 Agent 才能基于全集生成新的 Subagent）。
2. 每条能力的 summary 字段长度受控，避免主 Agent 上下文膨胀。
3. 数据源：
   - skills：~/.Aries/skills/{available,unavailable}/*
   - mcps：  ~/.Aries/mcp.json 中 mcpServers
   - subagents：~/.Aries/agent/*.json

查询命中使用简单的关键词包含匹配，对中文和英文都成立。
后续若需要语义检索，可在 `_score_entry` 处替换实现。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# summary 最大字符数，避免主 Agent 上下文膨胀
_SUMMARY_MAX = 120
# capability_search 返回结果上限
_DEFAULT_TOP_K = 10


@dataclass
class CapabilityItem:
    kind: str  # "skill" | "mcp" | "subagent"
    name: str
    summary: str
    status: str  # available | unavailable | disabled | missing_dep
    extra: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "summary": self.summary,
            "status": self.status,
            "extra": self.extra,
        }


def _truncate(text: str, limit: int = _SUMMARY_MAX) -> str:
    text = (text or "").strip().replace("\n", " ").replace("\r", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _collect_skills() -> list[CapabilityItem]:
    items: list[CapabilityItem] = []
    try:
        from utils.skills_manager import discover_skills

        for entry in discover_skills():
            items.append(
                CapabilityItem(
                    kind="skill",
                    name=entry.name,
                    summary=_truncate(entry.description),
                    status="available" if entry.enabled else "unavailable",
                    extra={
                        "folder_name": entry.folder_name,
                        "path": str(entry.skill_path),
                    },
                )
            )
    except Exception as exc:
        logger.warning("收集 skills 失败: %s", exc)
    return items


def _collect_mcps() -> list[CapabilityItem]:
    items: list[CapabilityItem] = []
    try:
        from utils.plugins_manager import discover_plugins

        for plugin in discover_plugins():
            items.append(
                CapabilityItem(
                    kind="mcp",
                    name=plugin.id,
                    summary=_truncate(plugin.description),
                    status="available" if plugin.enabled else "disabled",
                    extra={
                        "transport": plugin.transport,
                        "command": plugin.command,
                    },
                )
            )
    except Exception as exc:
        logger.warning("收集 mcps 失败: %s", exc)
    return items


def _collect_subagents() -> list[CapabilityItem]:
    items: list[CapabilityItem] = []
    try:
        from utils.subagent_manager import discover_subagents

        for entry in discover_subagents():
            if not entry.enabled:
                status = "disabled"
            elif not entry.available:
                status = "missing_dep"
            else:
                status = "available"
            items.append(
                CapabilityItem(
                    kind="subagent",
                    name=entry.name,
                    summary=_truncate(entry.description),
                    status=status,
                    extra={
                        "model": entry.effective_model or entry.model,
                        "allowed_skills": list(entry.allowed_skills),
                        "allowed_mcps": list(entry.allowed_mcps),
                        "unavailable_reason": entry.unavailable_reason,
                    },
                )
            )
    except Exception as exc:
        logger.warning("收集 subagents 失败: %s", exc)
    return items


def collect_all_capabilities(kinds: list[str] | None = None) -> list[CapabilityItem]:
    """收集 skill / mcp / subagent 全集（含 disabled / unavailable）。

    kinds: 限制类别，默认全部。
    """
    allowed = set(kinds) if kinds else {"skill", "mcp", "subagent"}
    items: list[CapabilityItem] = []
    if "skill" in allowed:
        items.extend(_collect_skills())
    if "mcp" in allowed:
        items.extend(_collect_mcps())
    if "subagent" in allowed:
        items.extend(_collect_subagents())
    return items


def _score_entry(query: str, item: CapabilityItem) -> int:
    """简易打分：name 命中权重高，summary 命中次之，多关键词全中加权。"""
    q = query.strip().lower()
    if not q:
        return 1  # 空 query 视为列出全部，统一权重
    tokens = [t for t in q.replace("，", ",").replace("、", ",").replace(",", " ").split() if t]
    if not tokens:
        return 0
    name_l = item.name.lower()
    summary_l = item.summary.lower()
    score = 0
    for token in tokens:
        if token in name_l:
            score += 5
        if token in summary_l:
            score += 2
    return score


def search_capabilities(
    query: str,
    kinds: list[str] | None = None,
    top_k: int = _DEFAULT_TOP_K,
) -> list[CapabilityItem]:
    """根据 query 在能力全集中检索 top_k 条匹配项。

    若 query 为空，按 kind/name 字典序返回前 top_k 条（用于"列出全部"场景）。
    """
    items = collect_all_capabilities(kinds=kinds)
    if not query.strip():
        items.sort(key=lambda x: (x.kind, x.name))
        return items[:top_k]
    scored = [(item, _score_entry(query, item)) for item in items]
    scored = [pair for pair in scored if pair[1] > 0]
    scored.sort(key=lambda pair: (-pair[1], pair[0].kind, pair[0].name))
    return [item for item, _ in scored[:top_k]]


# ---- 主 Agent 工具：capability_search ----

CAPABILITY_SEARCH_TOOL_NAME = "capability_search"
DELEGATE_TO_SUBAGENT_TOOL_NAME = "delegate_to_subagent"


def get_capability_search_tool_definition() -> dict[str, Any]:
    """主 Agent 使用的检索工具定义。

    主 Agent 只能看到 subagent 路由表 + 这个搜索工具，不会预加载全部 skill/mcp 详情。
    """
    return {
        "type": "function",
        "function": {
            "name": CAPABILITY_SEARCH_TOOL_NAME,
            "description": (
                "在系统全集中检索可用能力（skill / mcp / subagent），用于：\n"
                "1) 选择合适的 subagent 委派任务；\n"
                "2) 在创建新 subagent 时挑选可组合的 skill 与 mcp；\n"
                "3) 回答用户'我有哪些能力'类问题。\n"
                "返回项包含 kind / name / summary / status，"
                "status=available 表示对主 Agent 直接可用；"
                "status=unavailable/disabled/missing_dep 表示需要先启用或修复依赖，"
                "但仍可被 subagent 在其内部强制激活。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索关键词，可包含多个空格分隔的词。留空则返回前若干条。",
                    },
                    "kinds": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["skill", "mcp", "subagent"]},
                        "description": "限制检索的类别，默认全部。",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数上限，默认 5。",
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "required": ["query"],
            },
        },
    }


def execute_capability_search(arguments: dict[str, Any]) -> dict[str, Any]:
    """主 Agent 调用 capability_search 工具时的执行入口。"""
    query = str(arguments.get("query") or "")
    kinds = arguments.get("kinds")
    if isinstance(kinds, list):
        kinds = [str(k) for k in kinds if str(k).strip()]
    else:
        kinds = None
    top_k = arguments.get("top_k") or _DEFAULT_TOP_K
    try:
        top_k = max(1, min(int(top_k), 50))
    except (TypeError, ValueError):
        top_k = _DEFAULT_TOP_K

    results = search_capabilities(query=query, kinds=kinds, top_k=top_k)
    return {
        "success": True,
        "query": query,
        "kinds": kinds or ["skill", "mcp", "subagent"],
        "count": len(results),
        "results": [item.to_dict() for item in results],
    }


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
