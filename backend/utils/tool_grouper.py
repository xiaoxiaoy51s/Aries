"""
虚拟工具分组（#7）。

借鉴 VS Code Copilot 的 virtualToolGrouper.ts：
当工具数量超过阈值时，自动将工具按类别分组，每组生成摘要描述，
避免把所有工具的完整 schema 都塞进 prompt 导致 token 爆炸。

策略：
1. 工具数 ≤ START_GROUPING_AFTER_TOOL_COUNT：不分组，直接返回
2. 工具数 > 阈值：按类别分组，每组生成摘要
3. 分组维度：
   - 内置工具（file/cli/search/edit 等）→ 按功能域分组
   - MCP 工具 → 按来源 server 分组
   - Skill 工具 → 按技能分组
4. 每组生成一个"虚拟工具"描述，包含该组工具的能力摘要
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 分组阈值
START_GROUPING_AFTER_TOOL_COUNT = 15  # 工具数超过此值才分组

# 摘要长度限制
SUMMARY_MAX_CHARS = 200
GROUP_DESCRIPTION_MAX_CHARS = 300

# 内置工具的分类映射
BUILTIN_TOOL_CATEGORIES: dict[str, list[str]] = {
    "文件操作": [
        "read_file", "write_file", "edit_file", "list_files", "search_file",
        "multi_replace_string", "apply_patch", "delete_file",
    ],
    "命令执行": [
        "cli_executor", "run_command",
    ],
    "记忆与任务": [
        "todo_write", "create_scheduled_task",
        "delegate_to_subagent",
    ],
}

# 类别描述模板
CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "文件操作": "读取、写入、编辑、搜索文件的工具集合。包括精确替换、批量替换、补丁等编辑策略。",
    "命令执行": "执行本地 CLI 命令、运行脚本、安装依赖等。",
    "记忆与任务": "管理 Agent 记忆、读取技能文件、创建定时任务、委派子 Agent 等。",
    "MCP": "MCP 插件提供的工具。",
    "Skill": "已安装技能提供的领域工具。",
}


@dataclass
class ToolGroup:
    """一个工具分组。"""
    name: str
    description: str
    tool_names: list[str] = field(default_factory=list)
    tool_definitions: list[dict[str, Any]] = field(default_factory=list)
    source: str = ""  # builtin / mcp_<id> / skill_<name>

    @property
    def tool_count(self) -> int:
        return len(self.tool_names)

    def to_summary(self) -> str:
        """生成分组摘要（不含完整 schema）。"""
        tools_str = ", ".join(self.tool_names[:8])
        if len(self.tool_names) > 8:
            tools_str += f" 等 {len(self.tool_names)} 个"
        desc = self.description[:SUMMARY_MAX_CHARS]
        return f"[{self.name}] {desc}\n工具: {tools_str}"


@dataclass
class GroupingResult:
    """分组结果。"""
    grouped: bool
    groups: list[ToolGroup] = field(default_factory=list)
    ungrouped_tools: list[dict[str, Any]] = field(default_factory=list)
    total_tools: int = 0

    @property
    def prompt_savings(self) -> int:
        """估算分组后节省的 token 数（粗估）。"""
        if not self.grouped:
            return 0
        # 每个 ungrouped 工具的完整 schema 约 200-500 tokens
        # 分组后的摘要约 50-100 tokens
        grouped_tokens = sum(len(g.to_summary()) // 4 for g in self.groups)
        ungrouped_tokens = sum(
            len(str(t.get("function", {}).get("description", ""))) // 4
            for t in self.ungrouped_tools
        )
        full_tokens = self.total_tools * 300  # 平均每个工具 300 tokens
        return max(0, full_tokens - grouped_tokens - ungrouped_tokens)


class ToolGrouper:
    """工具分组器。

    用法：
        grouper = ToolGrouper()
        result = grouper.group_tools(tool_definitions)
        if result.grouped:
            # 用分组摘要替换部分工具定义
            prompt_context = grouper.build_grouped_prompt_context(result)
        else:
            # 工具不多，直接用原始定义
            prompt_context = ""
    """

    def group_tools(
        self,
        tools: list[dict[str, Any]],
        force: bool = False,
    ) -> GroupingResult:
        """对工具列表进行分组。

        Args:
            tools: OpenAI function calling 格式的工具定义列表
            force: 强制分组（忽略阈值检查）

        Returns:
            GroupingResult
        """
        if not tools:
            return GroupingResult(grouped=False, total_tools=0)

        if not force and len(tools) <= START_GROUPING_AFTER_TOOL_COUNT:
            return GroupingResult(
                grouped=False,
                ungrouped_tools=tools,
                total_tools=len(tools),
            )

        # 分组
        groups = self._categorize_tools(tools)

        # 小分组（≤2 个工具）不合入摘要，保留完整定义
        large_groups: list[ToolGroup] = []
        small_group_tools: list[dict[str, Any]] = []

        for group in groups:
            if group.tool_count <= 2:
                small_group_tools.extend(group.tool_definitions)
            else:
                large_groups.append(group)

        return GroupingResult(
            grouped=bool(large_groups),
            groups=large_groups,
            ungrouped_tools=small_group_tools,
            total_tools=len(tools),
        )

    def _categorize_tools(self, tools: list[dict[str, Any]]) -> list[ToolGroup]:
        """按类别分组工具。"""
        groups_map: dict[str, ToolGroup] = {}
        ungrouped: list[dict[str, Any]] = []

        for tool in tools:
            func = tool.get("function", {})
            name = func.get("name", "")
            if not name:
                continue

            category = self._find_category(name, tool)

            if category:
                if category not in groups_map:
                    groups_map[category] = ToolGroup(
                        name=category,
                        description=CATEGORY_DESCRIPTIONS.get(category, f"{category} 相关工具"),
                        source="builtin" if category in BUILTIN_TOOL_CATEGORIES else category.lower(),
                    )
                groups_map[category].tool_names.append(name)
                groups_map[category].tool_definitions.append(tool)
            else:
                ungrouped.append(tool)

        result = list(groups_map.values())

        # 未分类的工具放入"其他"组
        if ungrouped:
            other_group = ToolGroup(
                name="其他工具",
                description="未分类的工具集合。",
                source="misc",
            )
            for tool in ungrouped:
                func = tool.get("function", {})
                other_group.tool_names.append(func.get("name", ""))
                other_group.tool_definitions.append(tool)
            result.append(other_group)

        return result

    def _find_category(self, tool_name: str, tool: dict[str, Any]) -> str | None:
        """查找工具所属类别。"""
        # 1. 检查内置工具映射
        for category, names in BUILTIN_TOOL_CATEGORIES.items():
            if tool_name in names:
                return category

        # 2. 检查 MCP 来源
        source = tool.get("source", "")
        if source and source.startswith("mcp_"):
            server_id = source[4:]
            return f"MCP:{server_id}"

        # 3. 检查 Skill 来源
        if source and source.startswith("skill_"):
            skill_name = source[6:]
            return f"Skill:{skill_name}"

        # 4. 根据 description 关键词推断
        desc = tool.get("function", {}).get("description", "").lower()
        if any(kw in desc for kw in ["文件", "file", "read", "write", "edit"]):
            return "文件操作"
        if any(kw in desc for kw in ["命令", "command", "exec", "terminal", "shell"]):
            return "命令执行"
        if any(kw in desc for kw in ["搜索", "search", "find", "grep"]):
            return "文件操作"
        if any(kw in desc for kw in ["记忆", "memory", "task", "schedule"]):
            return "记忆与任务"

        return None

    def build_grouped_prompt_context(self, result: GroupingResult) -> str:
        """生成分组后的 prompt 上下文文本。

        这段文本会替换被分组的工具的完整 schema，减少 token 占用。
        """
        if not result.grouped:
            return ""

        lines = ["# 工具分组说明", "以下工具按功能分组，调用时工具名仍使用原始名称：", ""]

        for group in result.groups:
            lines.append(group.to_summary())
            lines.append("")

        if result.ungrouped_tools:
            lines.append(f"另有 {len(result.ungrouped_tools)} 个工具未分组，直接可用。")

        return "\n".join(lines)

    def build_compact_tool_list(self, result: GroupingResult) -> list[dict[str, Any]]:
        """生成压缩后的工具列表。

        被分组的工具只保留 name 和简短 description（去掉 parameters schema），
        未分组的工具保留完整定义。

        这样 LLM 仍能看到所有工具名，但 prompt 更短。
        被分组的工具在被调用时，Agent 需要"展开"查看完整参数。
        """
        compact_tools: list[dict[str, Any]] = []

        for group in result.groups:
            for tool_def in group.tool_definitions:
                func = tool_def.get("function", {})
                compact_tools.append({
                    "type": "function",
                    "function": {
                        "name": func.get("name", ""),
                        "description": func.get("description", "")[:GROUP_DESCRIPTION_MAX_CHARS],
                        "parameters": func.get("parameters", {}),
                    },
                })

        for tool_def in result.ungrouped_tools:
            compact_tools.append(tool_def)

        return compact_tools


# 全局单例
_grouper: ToolGrouper | None = None


def get_grouper() -> ToolGrouper:
    """获取全局 ToolGrouper 实例。"""
    global _grouper
    if _grouper is None:
        _grouper = ToolGrouper()
    return _grouper


def maybe_group_tools(
    tools: list[dict[str, Any]],
    force: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    """便捷函数：如果工具数多则分组，返回 (压缩后工具列表, 分组说明文本)。

    用法：
        tools, group_context = maybe_group_tools(all_tool_definitions)
        # tools 可以直接放进 LLM 请求
        # group_context 可以拼到 system prompt 中
    """
    grouper = get_grouper()
    result = grouper.group_tools(tools, force=force)

    if not result.grouped:
        return tools, ""

    compact_tools = grouper.build_compact_tool_list(result)
    group_context = grouper.build_grouped_prompt_context(result)

    logger.info(
        "[ToolGrouper] 分组完成: %d 工具 → %d 组 + %d 未分组, 节省约 %d tokens",
        result.total_tools, len(result.groups), len(result.ungrouped_tools),
        result.prompt_savings,
    )

    return compact_tools, group_context


__all__ = [
    "ToolGroup",
    "GroupingResult",
    "ToolGrouper",
    "get_grouper",
    "maybe_group_tools",
    "START_GROUPING_AFTER_TOOL_COUNT",
]
