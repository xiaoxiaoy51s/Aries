"""
编辑代码专用 Prompt 模板（#2 意图分发 + #3 模板工程化）。

借鉴 VS Code Copilot 的 EditCodePrompt2 / defaultAgentInstructions 设计：
- 按"功能模块"拆分，每块有独立 priority，方便上层按 token 预算裁剪
- 支持条件渲染：根据可用工具集和模型家族输出不同指令
- 多策略编辑工具的使用指南（edit_file / multi_replace_string / apply_patch）

注入位置：build_agent_system_prompt_parts 的 base 段末尾，紧跟 CODING_BEHAVIOR_RULES。
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# 优先级常量（数字越大优先级越高，token 不足时先裁低优先级段）
# ---------------------------------------------------------------------------
PRIORITY_CORE = 100      # 核心编辑规则，不可裁剪
PRIORITY_TOOL_GUIDE = 90  # 工具使用指南
PRIORITY_REMINDER = 70    # 提醒事项
PRIORITY_EXAMPLES = 50    # 示例，token 紧张时可裁

# ---------------------------------------------------------------------------
# 模块化段落
# ---------------------------------------------------------------------------

EDIT_CODE_CORE_RULES = """# 编辑代码核心规则
- 修改文件前必须先 read_file 读取目标文件，确认当前内容再编辑。绝不编辑没读过的代码。
- 描述要做的修改，然后直接调用工具，不要在回复中贴出完整代码块。
- 按文件分组修改：同一文件的多次修改尽量合并到一次工具调用。
- 修改后不需要重复展示改动内容，工具会自动应用并展示给用户。
- 不做未被要求的额外修改：修 bug 不顺手清理周边，加功能不顺手改配置。"""

EDIT_TOOL_SELECTION_RULES = """# 编辑工具选择策略
根据修改场景选择最合适的工具，减少 LLM 往返次数：

## edit_file(search_replace)（首选，最精确）
- 场景：替换文件中的特定文本片段
- 要求：search_text 必须包含 3-5 行上下文（前后各几行未改动的代码），确保定位唯一
- 优势：精准定位，不需要行号，适合小范围修改
- 示例：修改变量名、调整函数参数、更新条件判断

## multi_replace_string（批量修改首选）
- 场景：同一文件有多处独立修改
- 要求：每条 replacement 的 old_text 都要包含足够上下文
- 优势：一次调用完成多处修改，减少 LLM 往返，降低 token 消耗
- 何时用：同一个文件需要改 3 处以上时，必须用 multi_replace_string 而不是多次 edit_file

## apply_patch（大范围修改）
- 场景：新增整个函数/类、删除大段代码、跨多文件重构
- 格式：标准 unified diff
- 优势：一次完成大范围改动，适合 50 行以上的变更
- 何时用：修改量太大用 edit_file(search_replace) 不划算时

## edit_file(line_range / insert_line)（按行号操作）
- 场景：需要按精确行号替换或插入时
- 方式：line_range（按行号范围替换）/ insert_line（在指定行前插入）
- 注意：line_range 需要精确行号，文件改动后行号会偏移，谨慎使用

## 工具选择决策树
1. 单处小修改（<10行）→ edit_file(search_replace)
2. 同文件多处修改 → multi_replace_string
3. 大范围新增/删除（>50行）→ apply_patch
4. 按行号精确操作 → edit_file(line_range)
5. 插入新代码到指定位置 → edit_file(insert_line)"""

EDIT_FILE_SEARCH_REPLACE_GUIDE = """# edit_file(search_replace) 使用指南
工具名：edit_file（edit_type=search_replace）
参数：
- file_path: 目标文件路径
- edit_type: "search_replace"
- search_text: 要搜索的原始文本（必须包含 3-5 行上下文确保唯一）
- new_content: 替换后的文本

规则：
- search_text 必须和文件中的实际内容完全匹配（包括缩进、空格、换行）
- 如果 search_text 在文件中出现多次，工具会报错，此时需要增加上下文行使其唯一
- 不要用 search_replace 替换大段代码（>30行），改用 apply_patch
- 一次 search_replace 只做一处替换，多处修改用 multi_replace_string

正确示例（search_text 含上下文）：
  search_text: |
    def calculate_total(items):
        total = 0
        for item in items:
            total += item.price
        return total

  new_content: |
    def calculate_total(items):
        total = 0
        for item in items:
            total += item.price * item.quantity
        return total

错误示例（search_text 无上下文，可能不唯一）：
  search_text: "total += item.price"
  new_content: "total += item.price * item.quantity\""""

MULTI_REPLACE_STRING_GUIDE = """# multi_replace_string 使用指南
工具名：multi_replace_string
参数：
- file_path: 目标文件路径
- replacements: 替换列表，每项含 {old_text, new_text}

规则：
- 所有替换在同一事务中执行，任一失败则全部回滚
- 各 replacement 的 old_text 互不重叠
- 比 N 次 edit_file(search_replace) 更高效：一次 LLM 调用 + 一次文件写入
- 同一文件需要修改 3 处以上时，必须用此工具

示例：
  file_path: "src/utils.py"
  replacements: [
    {"old_text": "def add(a, b):\\n    return a + b", "new_text": "def add(a, b):\\n    return a + b + 1"},
    {"old_text": "def sub(a, b):\\n    return a - b", "new_text": "def sub(a, b):\\n    return a - b - 1"},
    {"old_text": "RESULT_OK = 0", "new_text": "RESULT_OK = 200"}
  ]"""

APPLY_PATCH_GUIDE = """# apply_patch 使用指南
工具名：apply_patch
参数：
- file_path: 目标文件路径
- patch: 标准 unified diff 格式的补丁

格式：
  --- a/path/to/file
  +++ b/path/to/file
  @@ -10,5 +10,8 @@
   unchanged line
  -removed line
  +added line
  +added line 2
   unchanged line

规则：
- 适合新增整个函数/类、删除大段代码、大规模重构
- patch 中的行号必须基于文件当前状态（先 read_file 确认）
- 上下文行（空格开头的行）必须和文件完全匹配
- 一次 apply_patch 只改一个文件，多文件改多个 patch

何时用 apply_patch 而不是 edit_file(search_replace)：
- 新增超过 20 行代码
- 删除超过 10 行代码
- 修改散布在文件各处且每处改动较大
- 需要标准 diff 格式供 review"""

EDIT_REMINDER_RULES = """# 编辑提醒
- 修改前先 read_file，修改后不需要再 read_file 验证（工具会返回修改结果）
- 如果 edit_file(search_replace) 报"search_text not found"，先 read_file 重新确认文件内容，可能是文件已被其他操作修改
- 不要在同一轮中对同一文件既用 search_replace 又用 line_range/insert_line，选一种方式
- 多文件修改可以在同一轮 tool_calls 中并行调用多个工具
- 编辑后如需验证，用 run_command 执行测试或语法检查，不要用 read_file 反复确认"""

# ---------------------------------------------------------------------------
# 条件渲染：根据可用工具集组装指南
# ---------------------------------------------------------------------------

def build_edit_code_prompt(
    *,
    has_replace_string: bool = False,
    has_multi_replace: bool = False,
    has_apply_patch: bool = False,
    model_family: str = "",
) -> str:
    """根据可用工具和模型家族，条件渲染编辑代码 prompt。

    Args:
        has_replace_string: 是否注册了 edit_file 的 search_replace 模式
        has_multi_replace: 是否注册了 multi_replace_string 工具
        has_apply_patch: 是否注册了 apply_patch 工具
        model_family: 模型家族标识（anthropic / openai / gemini / ""）

    Returns:
        拼接好的编辑代码 prompt 段落，可直接附加到 system prompt
    """
    sections: list[str] = [EDIT_CODE_CORE_RULES]

    # 工具选择策略：根据可用工具调整
    tool_guides: list[str] = []
    if has_replace_string:
        tool_guides.append(EDIT_FILE_SEARCH_REPLACE_GUIDE)
    if has_multi_replace:
        tool_guides.append(MULTI_REPLACE_STRING_GUIDE)
    if has_apply_patch:
        tool_guides.append(APPLY_PATCH_GUIDE)

    if tool_guides:
        sections.append(EDIT_TOOL_SELECTION_RULES)
        sections.extend(tool_guides)

    sections.append(EDIT_REMINDER_RULES)

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# 意图识别 prompt（#2 意图分发）
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

判断规则：
1. 用户说"修改/修复/改/更新/重构" → edit/fix
2. 用户说"解释/为什么/是什么/怎么工作" → explain
3. 用户说"搜索/查找/找" → search
4. 用户说"审查/review" → review
5. 用户说"创建/生成/新建/写脚本" → create
6. 复杂多步任务 → agent
7. 不确定时默认 agent（最通用）"""


def build_intent_specific_prompt(intent: str, **kwargs: Any) -> str:
    """根据识别出的意图，返回该意图专用的补充 prompt。

    Args:
        intent: 意图标识（edit/fix/explain/search/review/create/agent）
        **kwargs: 传递给子构建器的参数

    Returns:
        该意图专用的 prompt 段落，空字符串表示无需补充
    """
    builders = {
        "edit": lambda: build_edit_code_prompt(
            has_replace_string=kwargs.get("has_replace_string", True),
            has_multi_replace=kwargs.get("has_multi_replace", True),
            has_apply_patch=kwargs.get("has_apply_patch", True),
            model_family=kwargs.get("model_family", ""),
        ),
        "fix": lambda: FIX_INTENT_PROMPT,
        "explain": lambda: EXPLAIN_INTENT_PROMPT,
        "search": lambda: SEARCH_INTENT_PROMPT,
        "review": lambda: "",  # review 用独立的 code_review_prompts
        "create": lambda: CREATE_INTENT_PROMPT,
        "agent": lambda: build_edit_code_prompt(
            has_replace_string=kwargs.get("has_replace_string", True),
            has_multi_replace=kwargs.get("has_multi_replace", True),
            has_apply_patch=kwargs.get("has_apply_patch", True),
            model_family=kwargs.get("model_family", ""),
        ),
    }
    builder = builders.get(intent, lambda: "")
    return builder()


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
- 确认文件路径：默认保存到工作目录下
- 用 write_file 创建文件，内容要完整可运行
- 创建后如需注册（如新增 Python 模块），提示用户必要的配置步骤
- 不要创建不必要的文件：用户没要求的不建，能用现有文件的不新建
- 临时脚本放 .Aries_tmp/ 目录"""


# ---------------------------------------------------------------------------
# Prompt 模板工程化：优先级渲染器（#3）
# ---------------------------------------------------------------------------

class PromptSection:
    """一个 prompt 段落，带优先级和 token 估算。"""

    def __init__(self, content: str, priority: int = PRIORITY_REMINDER, name: str = ""):
        self.content = content
        self.priority = priority
        self.name = name or content[:30]

    def estimate_tokens(self) -> int:
        return max(1, len(self.content) // 4)

    def __repr__(self) -> str:
        return f"PromptSection(name={self.name!r}, priority={self.priority}, tokens~{self.estimate_tokens()})"


class PromptBuilder:
    """按优先级和 token 预算组装 prompt。

    用法：
        builder = PromptBuilder(max_tokens=8000)
        builder.add(PromptSection(CORE_RULES, priority=PRIORITY_CORE, name="core"))
        builder.add(PromptSection(TOOL_GUIDE, priority=PRIORITY_TOOL_GUIDE, name="tools"))
        prompt = builder.render()
    """

    def __init__(self, max_tokens: int = 8000):
        self.max_tokens = max_tokens
        self.sections: list[PromptSection] = []

    def add(self, section: PromptSection) -> "PromptBuilder":
        self.sections.append(section)
        return self

    def add_text(self, content: str, priority: int = PRIORITY_REMINDER, name: str = "") -> "PromptBuilder":
        self.sections.append(PromptSection(content, priority, name))
        return self

    def render(self) -> str:
        """按优先级从高到低渲染，超出 token 预算时从低优先级开始裁剪。"""
        # 按优先级降序排列
        sorted_sections = sorted(self.sections, key=lambda s: s.priority, reverse=True)

        result: list[str] = []
        used_tokens = 0

        for section in sorted_sections:
            section_tokens = section.estimate_tokens()
            if used_tokens + section_tokens > self.max_tokens:
                # 超预算：低优先级的直接跳过
                continue
            result.append(section.content)
            used_tokens += section_tokens

        return "\n\n".join(result)

    def estimate_total_tokens(self) -> int:
        return sum(s.estimate_tokens() for s in self.sections)


def build_optimized_edit_prompt(
    *,
    has_replace_string: bool = True,
    has_multi_replace: bool = True,
    has_apply_patch: bool = True,
    model_family: str = "",
    max_tokens: int = 4000,
) -> str:
    """使用 PromptBuilder 按优先级渲染编辑代码 prompt。

    token 预算不足时，会自动裁剪低优先级段（示例 > 提醒 > 工具指南 > 核心规则）。
    """
    builder = PromptBuilder(max_tokens=max_tokens)

    builder.add_text(
        EDIT_CODE_CORE_RULES,
        priority=PRIORITY_CORE,
        name="edit_core_rules",
    )

    if has_replace_string or has_multi_replace or has_apply_patch:
        builder.add_text(
            EDIT_TOOL_SELECTION_RULES,
            priority=PRIORITY_TOOL_GUIDE,
            name="tool_selection",
        )

    if has_replace_string:
        builder.add_text(EDIT_FILE_SEARCH_REPLACE_GUIDE, priority=PRIORITY_TOOL_GUIDE, name="edit_file_search_replace_guide")
    if has_multi_replace:
        builder.add_text(MULTI_REPLACE_STRING_GUIDE, priority=PRIORITY_TOOL_GUIDE, name="multi_replace_guide")
    if has_apply_patch:
        builder.add_text(APPLY_PATCH_GUIDE, priority=PRIORITY_TOOL_GUIDE, name="apply_patch_guide")

    builder.add_text(EDIT_REMINDER_RULES, priority=PRIORITY_REMINDER, name="edit_reminder")

    return builder.render()


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
    """根据用户消息文本识别意图（规则匹配，不调 LLM）。

    Args:
        user_text: 用户当前消息的文本内容

    Returns:
        意图标识：edit / fix / explain / search / review / create / agent
    """
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
    "multi_replace_string", "apply_patch", "delete_file",
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
    """返回该意图下允许使用的工具名集合。

    Returns:
        工具名集合，或 None 表示全量工具（不过滤）
    """
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
    """根据意图过滤工具列表。

    只读意图（explain/search/review）只保留只读工具，
    编辑意图（edit/fix）保留编辑工具但不保留 MCP 等，
    agent 意图保留全部。

    Args:
        intent: 意图标识
        tools: 原始工具定义列表

    Returns:
        过滤后的工具定义列表
    """
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
            # 子 Agent 委派在 agent 意图才有
            pass
        # MCP / Skill 工具：只读意图不加载，编辑意图也不加载（避免误操作）
    return filtered


def get_prompt_for_intent(intent: str, **kwargs: Any) -> str:
    """根据意图返回专用补充 prompt。

    Args:
        intent: 意图标识
        **kwargs: 传递给子构建器的参数

    Returns:
        该意图专用的 prompt 段落，空字符串表示无需补充
    """
    prompts = {
        INTENT_EDIT: lambda: build_optimized_edit_prompt(
            has_replace_string=kwargs.get("has_replace_string", True),
            has_multi_replace=kwargs.get("has_multi_replace", True),
            has_apply_patch=kwargs.get("has_apply_patch", True),
        ),
        INTENT_FIX: lambda: FIX_INTENT_PROMPT + "\n\n" + build_optimized_edit_prompt(
            has_replace_string=kwargs.get("has_replace_string", True),
            has_multi_replace=kwargs.get("has_multi_replace", True),
            has_apply_patch=kwargs.get("has_apply_patch", True),
            max_tokens=2000,  # fix 意图不需要完整编辑指南，精简版
        ),
        INTENT_EXPLAIN: lambda: EXPLAIN_INTENT_PROMPT,
        INTENT_SEARCH: lambda: SEARCH_INTENT_PROMPT,
        INTENT_REVIEW: lambda: "",  # review 用独立的 code_review_prompts
        INTENT_CREATE: lambda: CREATE_INTENT_PROMPT,
        INTENT_AGENT: lambda: build_optimized_edit_prompt(
            has_replace_string=kwargs.get("has_replace_string", True),
            has_multi_replace=kwargs.get("has_multi_replace", True),
            has_apply_patch=kwargs.get("has_apply_patch", True),
        ),
    }
    builder = prompts.get(intent, lambda: "")
    return builder()


__all__ = [
    "EDIT_CODE_CORE_RULES",
    "EDIT_TOOL_SELECTION_RULES",
    "EDIT_FILE_SEARCH_REPLACE_GUIDE",
    "MULTI_REPLACE_STRING_GUIDE",
    "APPLY_PATCH_GUIDE",
    "EDIT_REMINDER_RULES",
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
