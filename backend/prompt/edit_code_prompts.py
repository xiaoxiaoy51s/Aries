"""编辑代码 Prompt + 意图识别（精简版）。"""

from __future__ import annotations

from typing import Any


# 编辑代码规则（每个工具的具体用法见工具本身的 description）
EDIT_CODE_RULES = """# 编辑代码规则
- 修改前先 read_file 确认内容。改完后不需要再读文件验证（工具会返回结果）。
- 单处修改用 edit_file(search_replace)，search_text 带 3-5 行上下文确保唯一。
- 同一文件改多处用 edit_file(multi_replace)，一次完成原子性批量替换。
- 不要在同一轮中对同一文件混用多种编辑方式。"""

# 兼容旧导出名
EDIT_CODE_CORE_RULES = EDIT_CODE_RULES
PRIORITY_CORE = 100
PRIORITY_TOOL_GUIDE = 90
PRIORITY_REMINDER = 70
PRIORITY_EXAMPLES = 50


def build_edit_code_prompt(**kwargs) -> str:
    return EDIT_CODE_RULES


def build_optimized_edit_prompt(**kwargs) -> str:
    return EDIT_CODE_RULES


def build_intent_specific_prompt(intent: str, **kwargs: Any) -> str:
    """根据识别出的意图，返回该意图专用的补充 prompt。"""
    builders = {
        "edit": lambda: EDIT_CODE_RULES,
        "fix": lambda: FIX_INTENT_PROMPT,
        "explain": lambda: EXPLAIN_INTENT_PROMPT,
        "search": lambda: SEARCH_INTENT_PROMPT,
        "review": lambda: "",
        "create": lambda: CREATE_INTENT_PROMPT,
        "agent": lambda: EDIT_CODE_RULES,
    }
    builder = builders.get(intent, lambda: "")
    return builder()


# 兼容旧导出：空类定义（被 import 时不报错即可）
class PromptSection:
    pass


class PromptBuilder:
    pass


# ---------------------------------------------------------------------------
# 意图识别 prompt
# ---------------------------------------------------------------------------

INTENT_CLASSIFICATION_PROMPT = """# 意图识别
分析用户请求，判断属于以下哪种意图，然后选择对应的处理策略：

- **edit**: 修改代码、修复 bug、重构、添加功能 → 使用编辑工具
- **fix**: 修复错误、解决诊断问题 → 先获取错误信息，再编辑
- **explain**: 解释代码、回答问题 → 只读，不调用编辑工具
- **search**: 搜索代码库、查找定义 → 只读，使用 search_file
- **review**: 代码审查 → 只读分析，不修改
- **create**: 创建新文件、生成脚本 → 使用 write_file
- **agent**: 复杂多步任务 → 完整 Agent 模式，所有工具可用
- 不确定时默认 agent（最通用）"""


FIX_INTENT_PROMPT = """# 修复错误意图
- 先用 run_command 运行测试或构建命令，获取完整错误输出
- 分析错误根因，不要只看第一行报错
- 修复前先 read_file 读取报错文件的相关代码
- 修复后重新运行验证命令，确认问题解决
- 如果错误涉及多个文件，逐个修复后统一验证
- 不要为了消除报错而注释掉代码或添加 try/except 吞异常"""


EXPLAIN_INTENT_PROMPT = """# 解释代码意图
- 只读模式：不调用任何编辑工具（edit_file/write_file）
- 先 read_file 读取用户询问的代码
- 如需理解上下文，用 search_file 查找相关定义和调用
- 解释时引用具体文件路径和行号
- 不要主动修改代码，如果发现问题只描述"建议怎么改"，不实际执行"""


SEARCH_INTENT_PROMPT = """# 搜索代码意图
- 只读模式：不调用任何编辑工具
- 用 search_file 搜索关键词（支持正则）
- 用 list_files 浏览目录结构
- 搜索后归纳结果，给出文件路径、行号、关键代码片段
- 如果搜索结果不够，可以用 read_file 读取完整文件确认
- 不要修改任何文件"""


CREATE_INTENT_PROMPT = """# 创建文件意图
- 用 write_file 创建文件到工作目录下，内容完整可运行。
- 不要建用户没要求的文件。临时脚本放 .Aries_tmp/ 目录。"""


# ===========================================================================
# 意图识别（规则匹配，不调 LLM，零额外成本）
# ===========================================================================

# 意图类型
INTENT_EDIT = "edit"        # 修改代码、修复 bug、重构、添加功能
INTENT_FIX = "fix"          # 修复错误、解决诊断问题
INTENT_EXPLAIN = "explain"  # 解释代码、回答问题（只读）
INTENT_SEARCH = "search"    # 搜索代码库、查找定义（只读）
INTENT_REVIEW = "review"    # 代码审查（只读）
INTENT_CREATE = "create"    # 创建新文件、生成脚本
INTENT_AGENT = "agent"      # 复杂多步任务（默认，全量工具）

# 意图关键词映射（按优先级从高到低匹配）
_INTENT_KEYWORDS: list[tuple[str, list[str]]] = [
    # review 最高优先级，避免被 edit/fix 覆盖
    (INTENT_REVIEW, [
        "审查", "review", "代码审查", "code review", "cr ", "@code_review",
    ]),
    # fix：修复错误相关
    (INTENT_FIX, [
        "修复", "fix ", "bug", "报错", "错误", "异常", "失败", "崩溃",
        "traceback", "error", "exception", "failed", "诊断", "lint",
    ]),
    # create：创建新文件
    (INTENT_CREATE, [
        "创建", "新建", "生成", "初始化", "create ", "init ",
        "写脚本", "生成脚本", "写一个脚本", "新建文件",
    ]),
    # explain：解释/问答（只读）
    (INTENT_EXPLAIN, [
        "解释", "为什么", "是什么", "什么是", "怎么工作", "原理",
        "讲解", "说明一下", "解释一下", "什么意思", "explain",
        "文档", "注释什么意思",
    ]),
    # search：搜索/查找（只读）
    (INTENT_SEARCH, [
        "搜索", "查找", "查找一下", "找一下", "在哪", "哪里",
        "找到", "search ", "find ", "grep ", "定位",
        "哪些文件", "哪个文件", "有没有", "是否存在",
    ]),
    # edit：修改代码
    (INTENT_EDIT, [
        "修改", "改一下", "改成", "更新", "重构", "实现", "添加",
        "删除", "优化", "调整", "替换", "重命名", "移动",
        "edit ", "modify ", "update ", "refactor ", "rename ",
        "添加功能", "增加", "去掉", "注释掉", "取消注释",
    ]),
]


def classify_intent(user_text: str) -> str:
    """根据用户消息文本识别意图（规则匹配，不调 LLM）。"""
    if not user_text or not user_text.strip():
        return INTENT_AGENT

    text = user_text.lower().strip()

    # 按优先级匹配关键词
    for intent, keywords in _INTENT_KEYWORDS:
        for kw in keywords:
            if kw in text:
                return intent

    # 默认：agent（最通用，全量工具）
    return INTENT_AGENT


# 各意图对应的工具集白名单（None 表示全量工具）
_READONLY_TOOLS = {
    "read_file", "list_files", "search_file",
    "todo_write",
}

_EDIT_TOOLS = {
    "read_file", "write_file", "edit_file", "list_files", "search_file",
    "delete_file",
    "cli_executor",
    "todo_write",
    "create_scheduled_task",
}

_CREATE_TOOLS = {
    "read_file", "write_file", "list_files", "search_file",
    "cli_executor", "todo_write",
}

_FULL_TOOLS = None  # None 表示不做过滤


def get_tools_for_intent(intent: str) -> set[str] | None:
    """返回该意图下允许使用的工具名集合。"""
    tool_sets = {
        INTENT_EXPLAIN: _READONLY_TOOLS,
        INTENT_SEARCH: _READONLY_TOOLS,
        INTENT_REVIEW: _READONLY_TOOLS,
        INTENT_EDIT: _EDIT_TOOLS,
        INTENT_FIX: _EDIT_TOOLS,
        INTENT_CREATE: _CREATE_TOOLS,
        INTENT_AGENT: _FULL_TOOLS,
    }
    return tool_sets.get(intent, _FULL_TOOLS)


def filter_tools_for_intent(
    intent: str,
    tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """根据意图过滤工具列表。"""
    allowed = get_tools_for_intent(intent)
    if allowed is None:
        return tools

    filtered: list[dict[str, Any]] = []
    for tool in tools:
        func = tool.get("function", {})
        name = func.get("name", "")
        if name in allowed:
            filtered.append(tool)
        elif name == "delegate_to_subagent":
            pass
    return filtered


def get_prompt_for_intent(intent: str, **kwargs: Any) -> str:
    """根据意图返回专用补充 prompt。"""
    prompts = {
        INTENT_EDIT: lambda: EDIT_CODE_RULES,
        INTENT_FIX: lambda: FIX_INTENT_PROMPT + "\n\n" + EDIT_CODE_RULES,
        INTENT_EXPLAIN: lambda: EXPLAIN_INTENT_PROMPT,
        INTENT_SEARCH: lambda: SEARCH_INTENT_PROMPT,
        INTENT_REVIEW: lambda: "",
        INTENT_CREATE: lambda: CREATE_INTENT_PROMPT,
        INTENT_AGENT: lambda: EDIT_CODE_RULES,
    }
    builder = prompts.get(intent, lambda: "")
    return builder()


__all__ = [
    "EDIT_CODE_RULES",
    "EDIT_CODE_CORE_RULES",
    "FIX_INTENT_PROMPT",
    "EXPLAIN_INTENT_PROMPT",
    "SEARCH_INTENT_PROMPT",
    "CREATE_INTENT_PROMPT",
    "INTENT_CLASSIFICATION_PROMPT",
    "build_edit_code_prompt",
    "build_intent_specific_prompt",
    "build_optimized_edit_prompt",
    "PromptSection",
    "PromptBuilder",
    "PRIORITY_CORE",
    "PRIORITY_TOOL_GUIDE",
    "PRIORITY_REMINDER",
    "PRIORITY_EXAMPLES",
    # 意图识别
    "INTENT_EDIT",
    "INTENT_FIX",
    "INTENT_EXPLAIN",
    "INTENT_SEARCH",
    "INTENT_REVIEW",
    "INTENT_CREATE",
    "INTENT_AGENT",
    "classify_intent",
    "get_tools_for_intent",
    "filter_tools_for_intent",
    "get_prompt_for_intent",
]
