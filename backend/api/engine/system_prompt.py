"""系统提示词构建 + 技能/工具解析。"""
import platform
from datetime import datetime

from engine.skills_manager import (
    discover_skills,
    get_all_tool_definitions,
    build_skills_context_from_entries,
)
from memory.agent_memory import build_agent_memory_system_section
from prompt import CODING_BEHAVIOR_RULES
from prompt.edit_code_prompts import build_optimized_edit_prompt


def _session_context_note(session_id: str | None) -> str:
    """生成当前会话说明，供 system prompt 与工具默认行为使用。"""
    sid = (session_id or "").strip()
    if not sid:
        return "当前 session_id：未知"

    from db.scheduled_task import infer_platform

    platform_name = infer_platform(sid)
    platform_labels = {"wechat": "微信", "qq": "QQ", "feishu": "飞书"}
    if platform_name:
        label = platform_labels.get(platform_name, platform_name)
        return (
            f"当前 session_id：`{sid}`\n"
            f"消息来源：{label}（用户从此平台发来消息；"
            f"创建定时任务时若用户未指定推送平台，默认推送到{label}）"
        )
    return (
        f"当前 session_id：`{sid}`\n"
        "消息来源：网页聊天（创建定时任务时若用户未指定推送平台，默认在当前网页会话中继续）"
    )


_SUBAGENT_USAGE_RULES = (
    "\n"
    "# Subagent 使用规范\n"
    "下方「Available Subagents」列出了系统中可委派的子 Agent。每个 Subagent 拥有独立上下文与能力组合，适合复杂、多步、可被打包成角色的任务。\n"
    "- 你也可以基于检索结果生成新的 Subagent 配置文件（写到 ~/.Aries/agent/<name>.json）。\n"
    "\n"
    "# Subagent 调用约束\n"
    "- 通过 `delegate_to_subagent` 工具委派任务。委派时 task 必须详尽，子 Agent 看不到当前对话历史。\n"
    "- 子 Agent 一次性返回最终结果（result 或 error），不能交互式追问；它会通过自己的 `report_to_main` 工具提交结论。\n"
    "- 何时委派：复杂多步任务、需要保护主上下文不被淹没、独立可并行的子查询。\n"
    "- 何时不要委派：简单任务、答案已知、必须串行依赖前序结果、能用一两个工具直接搞定。\n"
    "- 同一轮 tool_calls 中可以并发委派多个不同 Subagent，它们会被真正并行执行；返回后用一段简洁文字向用户汇报整合结论。\n"
    "- 并行委派多个会修改文件的 Subagent 时，建议设置 `isolation: \"worktree\"` 参数，让每个子 Agent 在独立的 git worktree 中工作，避免写入冲突。\n"
)


def build_agent_system_prompt_parts(
    skills_context: str,
    work_dir: str | None = None,
    session_id: str | None = None,
    mcp_context: str = "",
    subagents_context: str = "",
) -> dict[str, str]:
    """构建 Agent 模式的系统提示词，并按"功能模块"分块返回。

    返回 dict:
        base: 身份/会话/工作目录/输出规范/Skill 使用规范（不含 skills 详情、rules、mcp）
        rules: 用户 rules.md + AI 项目记忆（agent.md）
        skills: 已安装本地 Skills 详情
        mcp: MCP 插件描述
        subagents: 可委派的子 Agent 精简路由表
        full: 拼接完整 system prompt（与旧版一致）
    """
    from pathlib import Path
    today_str = datetime.now().strftime("%Y-%m-%d")

    if work_dir and work_dir.strip():
        wd = str(Path(work_dir).expanduser().resolve())
        tmp_dir = str(Path(wd) / ".Aries_tmp")
        target_note = wd
    else:
        wd_path = Path.home() / ".Aries" / "work_dir"
        wd_path.mkdir(parents=True, exist_ok=True)
        wd = str(wd_path)
        tmp_dir = str(Path.home() / ".Aries" / "tmp")
        target_note = wd

    base = (
        "# 身份\n"
        "你是一个强大的多用途 AI 助手，擅长任务规划、文档创建、网络研究和代码执行。"
        f"今天的日期是 {today_str}，当前操作系统：{platform.system()}。\n"
        "\n"
        "# 当前会话\n"
        f"{_session_context_note(session_id)}\n"
        "\n"
        "# 工作目录\n"
        f"工作目录：`{wd}`\n"
        f"临时脚本目录：`{tmp_dir}`\n"
        f"⚠️ 所有生成的文件都应保存到工作目录：`{target_note}` 下！\n"
        "\n"
        "# 输出规范\n"
        "- 工具轮：输出「分析+计划」，再调用工具\n"
        "- 最终轮：直接输出精炼总结\n"
        "- 批量调用：无依赖的工具可同一轮调用\n"
        "- 所有工具失败时：2次尝试内停止，告知障碍，禁止伪造结果\n"
        "\n"
        "# Skill 使用规范\n"
        "在使用skill前，必须阅读SKILL.md文件，了解技能的用途和使用方法。不要直接上来就调用工具，有些工具虽然可以通过描述知道对应的使用方法，但是md文件中会有更加详细的使用说明。\n"
        "\n"
        + CODING_BEHAVIOR_RULES
        + "\n\n"
        + build_optimized_edit_prompt(
            has_replace_string=True,
            has_multi_replace=True,
            has_apply_patch=True,
        )
    )

    rules = build_agent_memory_system_section(wd) or ""

    skills_section = ""
    if skills_context:
        skills_section = "\n# 已安装的本地 Skills\n" + skills_context

    mcp_section = ""
    if mcp_context:
        mcp_section = f"\n# MCP 插件\n{mcp_context}"

    subagents_section = ""
    if subagents_context:
        subagents_section = _SUBAGENT_USAGE_RULES + "\n" + subagents_context

    # 内置插件简短列表
    plugins_section = ""
    try:
        from engine.plugin_manager import build_plugins_context
        plugins_ctx = build_plugins_context()
        if plugins_ctx:
            plugins_section = "\n" + plugins_ctx
    except Exception:
        pass

    full = base + rules + subagents_section + plugins_section + skills_section + mcp_section

    return {
        "base": base,
        "rules": rules,
        "skills": skills_section,
        "mcp": mcp_section,
        "subagents": subagents_section,
        "full": full,
    }


def build_agent_system_prompt(
    skills_context: str,
    work_dir: str | None = None,
    session_id: str | None = None,
    mcp_context: str = "",
    subagents_context: str = "",
) -> str:
    """构建 Agent 模式的系统提示词（精简版）"""
    return build_agent_system_prompt_parts(
        skills_context=skills_context,
        work_dir=work_dir,
        session_id=session_id,
        mcp_context=mcp_context,
        subagents_context=subagents_context,
    )["full"]


def get_agent_skills_and_tools():
    from mcp.runtime import build_mcp_prompt_context
    from engine.subagent_manager import build_subagent_router_section
    from utils.main_agent_config import get_main_agent_allowed_skills

    allowed_skills = get_main_agent_allowed_skills()
    all_skills = discover_skills()
    # 主 Agent 只加载 allowed_skills 中配置的技能
    if allowed_skills:
        enabled_skills = [s for s in all_skills if s.folder_name in allowed_skills]
    else:
        enabled_skills = []
    skills_context = build_skills_context_from_entries(enabled_skills)
    tool_definitions = get_all_tool_definitions()
    mcp_context = build_mcp_prompt_context()
    subagents_context = build_subagent_router_section()

    # 虚拟工具分组（#7）：工具数过多时自动分组，减少 prompt token 占用
    try:
        from utils.tool_grouper import maybe_group_tools
        tool_definitions, group_context = maybe_group_tools(tool_definitions)
        if group_context:
            skills_context = (skills_context or "") + "\n\n" + group_context
    except Exception:
        pass

    return skills_context, tool_definitions, mcp_context, subagents_context
