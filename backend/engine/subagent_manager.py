"""Subagent Manager - 子 Agent 配置加载与可用性管理

设计要点（Claude Code + Reasonix 风格）：
- 配置格式：Markdown 文件 + YAML frontmatter，路径 ~/.Aries/agent/<name>.md
- 插件 Agent：~/.Aries/plugins/agents/<name>/<name>.md
- 前端 API 不受影响（仍以 JSON 交互）
- 简化：不进行深层依赖校验（不检查 skill/mcp/model 是否存在）
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AGENT_ROOT = Path.home() / ".Aries" / "agent"
PLUGIN_AGENTS_ROOT = Path.home() / ".Aries" / "plugins" / "agents"

_NAME_SAFE_PATTERN = re.compile(r"^[A-Za-z0-9._\-]+$")


@dataclass
class SubagentEntry:
    name: str
    description: str
    model: str = ""
    enabled: bool = True
    allowed_skills: list[str] = field(default_factory=list)
    allowed_mcps: list[str] = field(default_factory=list)
    system_prompt: str = ""
    config_path: Path | None = None
    available: bool = True
    unavailable_reason: str = ""
    effective_model: str = ""

    def to_router_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "allowed_skills": list(self.allowed_skills),
            "allowed_mcps": list(self.allowed_mcps),
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
        }

    def to_api_dict(self) -> dict[str, Any]:
        data = self.to_router_dict()
        data["model"] = self.model
        data["system_prompt"] = self.system_prompt
        data["config_path"] = str(self.config_path) if self.config_path else ""
        return data


def ensure_agent_dir() -> None:
    AGENT_ROOT.mkdir(parents=True, exist_ok=True)


def _safe_filename(name: str) -> str:
    if not _NAME_SAFE_PATTERN.match(name):
        raise ValueError(f"名称只允许字母、数字、点、下划线、短横线：{name}")
    return name


def _config_path(name: str) -> Path:
    return AGENT_ROOT / f"{_safe_filename(name)}.md"


def _read_md(path: Path) -> tuple[dict[str, Any], str]:
    """读取 MD 文件，返回 (frontmatter, body)。"""
    from engine.skills_manager import parse_skill_frontmatter
    content = path.read_text(encoding="utf-8")
    frontmatter, body = parse_skill_frontmatter(content)
    return frontmatter, body.strip()


def _write_md(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    """写入 MD 文件（YAML frontmatter + body）。"""
    lines = ["---"]
    for k, v in frontmatter.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(v)}]")
        elif isinstance(v, bool):
            lines.append(f"{k}: {str(v).lower()}")
        elif v:
            lines.append(f"{k}: {v}")
    lines.append("---")
    if body:
        lines.append("")
        lines.append(body)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _str_list(value: Any) -> list[str]:
    """将 YAML 解析结果统一为字符串列表。兼容字符串和列表两种格式。"""
    if isinstance(value, list):
        return [str(s).strip() for s in value if str(s).strip()]
    if isinstance(value, str):
        # 兼容旧格式：逗号分隔字符串
        return [s.strip() for s in value.replace("[", "").replace("]", "").split(",") if s.strip()]
    return []


def _from_frontmatter(fm: dict[str, Any], name: str, path: Path) -> SubagentEntry:
    return SubagentEntry(
        name=name,
        description=str(fm.get("description") or "").strip(),
        model=str(fm.get("model") or "").strip(),
        enabled=bool(fm.get("enabled", True)),
        allowed_skills=_str_list(fm.get("allowed_skills")),
        allowed_mcps=_str_list(fm.get("allowed_mcps")),
        system_prompt="",  # body 在外层设置
        config_path=path,
    )


def discover_subagents() -> list[SubagentEntry]:
    """扫描 ~/.Aries/agent/*.md 和 ~/.Aries/plugins/agents/**/*.md，返回全部条目。

    用户目录的 agent 优先级高于插件 agent（同名覆盖）。
    不进行深层依赖校验。文件可读即可用。
    """
    ensure_agent_dir()
    entries: list[SubagentEntry] = []
    seen_names: set[str] = set()

    def _load_from(path: Path) -> None:
        name = path.stem
        if name in seen_names:
            return
        try:
            fm, body = _read_md(path)
        except (OSError, Exception) as exc:
            logger.warning("解析 subagent 失败 %s: %s", path, exc)
            return
        entry = _from_frontmatter(fm, name, path)
        entry.system_prompt = body
        entry.available = entry.enabled
        entry.unavailable_reason = "" if entry.enabled else "已被禁用"
        entry.effective_model = entry.model
        entries.append(entry)
        seen_names.add(name)

    # 1. 用户自定义 agent（优先级高）
    for path in sorted(AGENT_ROOT.glob("*.md")):
        _load_from(path)

    # 2. 插件 agent（优先级低，同名被跳过）
    if PLUGIN_AGENTS_ROOT.is_dir():
        for path in sorted(PLUGIN_AGENTS_ROOT.rglob("*.md")):
            _load_from(path)

    return entries


def get_subagent_by_name(name: str) -> SubagentEntry | None:
    for entry in discover_subagents():
        if entry.name == name:
            return entry
    return None


def list_available_subagents() -> list[SubagentEntry]:
    return [e for e in discover_subagents() if e.available]


def save_subagent(payload: dict[str, Any]) -> SubagentEntry:
    """新建或覆盖 subagent 配置。返回保存后的 entry。"""
    ensure_agent_dir()
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("name 不能为空")

    path = _config_path(name)

    frontmatter = {
        "name": name,
        "description": str(payload.get("description") or "").strip(),
    }
    model = str(payload.get("model") or "").strip()
    if model:
        frontmatter["model"] = model
    frontmatter["enabled"] = bool(payload.get("enabled", True))
    skills = [str(s).strip() for s in (payload.get("allowed_skills") or []) if str(s).strip()]
    if skills:
        frontmatter["allowed_skills"] = skills
    mcps = [str(m).strip() for m in (payload.get("allowed_mcps") or []) if str(m).strip()]
    if mcps:
        frontmatter["allowed_mcps"] = mcps

    body = str(payload.get("system_prompt") or "").strip()

    _write_md(path, frontmatter, body)

    entry = _from_frontmatter(frontmatter, name, path)
    entry.system_prompt = body
    entry.available = entry.enabled
    entry.effective_model = entry.model
    return entry


def delete_subagent(name: str) -> bool:
    path = _config_path(name)
    if path.is_file():
        path.unlink()
        return True
    return False


def set_subagent_enabled(name: str, enabled: bool) -> SubagentEntry:
    entry = get_subagent_by_name(name)
    if entry is None or entry.config_path is None:
        raise FileNotFoundError(f"Subagent {name} 不存在")

    fm, body = _read_md(entry.config_path)
    fm["enabled"] = enabled
    _write_md(entry.config_path, fm, body)

    new_entry = _from_frontmatter(fm, name, entry.config_path)
    new_entry.system_prompt = body
    new_entry.available = enabled
    new_entry.effective_model = new_entry.model
    return new_entry


def build_subagent_router_section(entries: list[SubagentEntry] | None = None) -> str:
    """构造给主 Agent system prompt 用的精简路由表。"""
    if entries is None:
        entries = list_available_subagents()
    if not entries:
        return ""

    lines = [
        "# Available Subagents（可委派的子 Agent）",
        "下列子 Agent 可由你委派任务。每个 Subagent 拥有独立上下文与能力组合。",
        "",
    ]
    for entry in entries:
        skills = ", ".join(entry.allowed_skills) if entry.allowed_skills else "-"
        mcps = ", ".join(entry.allowed_mcps) if entry.allowed_mcps else "-"
        lines.append(
            f"- {entry.name} | {entry.description or '(无描述)'} "
            f"| 技能: [{skills}] | MCP: [{mcps}]"
        )
    return "\n".join(lines)


# === 运行时上下文（以下函数保持原接口不变） ===

def _load_skill_entry_anywhere(skill_name: str):
    from engine.skills_manager import get_skill_by_name
    from engine.plugin_manager import discover_plugins

    entry = get_skill_by_name(skill_name)
    if entry is not None:
        return entry

    try:
        for plugin in discover_plugins():
            if plugin.kind == "skills" and (plugin.name == skill_name or plugin.display_name == skill_name):
                from dataclasses import dataclass
                from engine.skills_manager import SkillEntry
                from pathlib import Path

                target = Path(plugin.target_path)
                skill_md = target / "SKILL.md"
                if not skill_md.is_file():
                    skill_md = target / "skill.md"
                if not skill_md.is_file():
                    continue
                try:
                    from engine.skills_manager import parse_skill_markdown
                    parsed = parse_skill_markdown(skill_md, default_name=plugin.name)
                    return SkillEntry(
                        name=parsed["name"],
                        description=parsed["description"],
                        folder_name=plugin.name,
                        skill_path=target,
                        skill_md_path=skill_md,
                        content=parsed["content"],
                        body=parsed["body"],
                        frontmatter=parsed["frontmatter"],
                        enabled=True,
                    )
                except Exception:
                    continue
    except Exception as exc:
        logger.debug("加载内置插件 skill 失败: %s", exc)
    return None


def _build_subagent_skills_context(skill_names: list[str]) -> str:
    from engine.skills_manager import build_skills_context_from_entries
    COMMON_SKILLS = ("file_io", "cli")
    seen: set[str] = set()
    entries = []
    for name in list(skill_names) + list(COMMON_SKILLS):
        if name in seen:
            continue
        seen.add(name)
        entry = _load_skill_entry_anywhere(name)
        if entry is not None:
            entries.append(entry)
    return build_skills_context_from_entries(entries)


def build_subagent_runtime(name: str) -> dict[str, Any]:
    """根据 subagent 名称构造其运行时上下文。接口不变。"""
    from engine.plugin_manager import discover_plugins

    entry = get_subagent_by_name(name)
    if entry is None:
        raise ValueError(f"Subagent 不存在：{name}")

    skill_entries = []
    for skill_name in list(entry.allowed_skills):
        sk = _load_skill_entry_anywhere(skill_name)
        if sk is not None:
            skill_entries.append(sk)

    mcp_servers: list[str] = list(entry.allowed_mcps)

    skills_context = _build_subagent_skills_context(entry.allowed_skills)

    return {
        "entry": entry,
        "system_prompt": entry.system_prompt,
        "skills_context": skills_context,
        "skill_entries": skill_entries,
        "mcp_servers": mcp_servers,
        "effective_model": entry.effective_model or entry.model,
    }


def _build_subagent_skill_tool_definitions(skill_entries: list[Any]) -> list[dict[str, Any]]:
    from engine.skills_manager import CORE_TOOL_NAMES
    tools: list[dict[str, Any]] = []
    for entry in skill_entries:
        try:
            import importlib.util
            init_path = entry.skill_path / "__init__.py"
            if init_path.is_file():
                module_name = f"_subagent_direct_skill_{entry.folder_name}"
                spec = importlib.util.spec_from_file_location(module_name, init_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    skill_module = mod
                else:
                    continue
            else:
                from engine.skills_manager import skill_import_path
                skill_module = __import__(
                    skill_import_path(entry.folder_name),
                    fromlist=["get_tool_definition", "get_tool_definitions", "execute"],
                )
            if hasattr(skill_module, "get_tool_definitions"):
                defs = skill_module.get_tool_definitions()
                items = defs if isinstance(defs, list) else [defs]
                for item in items:
                    name = item.get("function", {}).get("name") if item else None
                    if name and name not in CORE_TOOL_NAMES:
                        tools.append(item)
            elif hasattr(skill_module, "get_tool_definition"):
                item = skill_module.get_tool_definition()
                name = item.get("function", {}).get("name") if item else None
                if name and name not in CORE_TOOL_NAMES:
                    tools.append(item)
        except Exception as exc:
            logger.warning("加载子 Agent skill %s 工具失败: %s", entry.folder_name, exc)
    return tools


def _filter_mcp_tools_by_servers(all_tools: list[dict[str, Any]], allowed_mcps: list[str]) -> list[dict[str, Any]]:
    if not allowed_mcps:
        return []
    try:
        from aries_mcp.runtime import _slug
    except Exception:
        return []
    allowed_slugs = {_slug(m) for m in allowed_mcps}
    result: list[dict[str, Any]] = []
    for tool in all_tools:
        name = tool.get("function", {}).get("name", "")
        if not name.startswith("mcp_"):
            continue
        rest = name[len("mcp_"):]
        for slug in allowed_slugs:
            if rest == slug or rest.startswith(slug + "_"):
                result.append(tool)
                break
    return result


def build_subagent_direct_chat_config(
    name: str,
    work_dir: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """构建子 Agent 直接作为对话主体时所需的覆盖配置。接口不变。"""
    try:
        runtime = build_subagent_runtime(name)
    except ValueError as exc:
        return {"entry": None, "override_model": "", "override_system_prompt": "", "override_tools": [], "error": str(exc)}

    entry = runtime["entry"]
    skills_context = runtime["skills_context"]
    skill_entries = runtime["skill_entries"]
    mcp_servers = runtime["mcp_servers"]

    override_base_url = ""
    override_api_key = ""
    effective_model = runtime["effective_model"]
    if effective_model:
        try:
            from models.model_manager import model_manager
            for m in model_manager.list_models():
                if m.model == effective_model:
                    override_base_url = m.baseUrl or ""
                    override_api_key = m.apiKey or ""
                    break
        except Exception as exc:
            logger.warning("解析子 Agent 模型凭证失败: %s", exc)

    import platform
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    parts: list[str] = [
        f"# 你的身份\n你是一个 AI 助手：`{entry.name}`。今天的日期是 {today}，当前操作系统：{platform.system()}。\n",
    ]
    if entry.system_prompt.strip():
        parts.append(f"# 详细职责\n{entry.system_prompt.strip()}\n")
    if work_dir and work_dir.strip():
        try:
            from memory.agent_memory import build_agent_memory_system_section
            memory_section = build_agent_memory_system_section(work_dir)
            if memory_section:
                parts.append(memory_section)
        except Exception:
            pass
    try:
        from prompt.coding_agent_prompts import DOING_TASKS_RULES, CODE_STYLE_RULES, COMPLETION_HONESTY_RULES
        parts.append(
            "# 编码行为约束\n"
            + DOING_TASKS_RULES + "\n\n"
            + CODE_STYLE_RULES + "\n\n"
            + COMPLETION_HONESTY_RULES
        )
    except Exception:
        pass
    parts.append("# 输出规范\n请保持回答简洁、可执行。")
    if skills_context:
        parts.append("# 可用本地 Skills\n" + skills_context)
    override_system_prompt = "\n\n".join(parts)

    try:
        from engine.tool_definitions import get_tool_definitions as get_core_tool_definitions
        core_tools = [
            d for d in (get_core_tool_definitions() or [])
            if d.get("function", {}).get("name") != "delegate_to_subagent"
        ]
    except Exception as exc:
        logger.warning("加载子 Agent 核心工具失败: %s", exc)
        core_tools = []

    skill_tools = _build_subagent_skill_tool_definitions(skill_entries)

    try:
        from aries_mcp.runtime import get_mcp_tool_definitions
        all_mcp_tools = get_mcp_tool_definitions()
    except Exception:
        all_mcp_tools = []
    mcp_tools = _filter_mcp_tools_by_servers(all_mcp_tools, mcp_servers)

    override_tools: list[dict[str, Any]] = []
    override_tools.extend(core_tools)
    override_tools.extend(skill_tools)
    override_tools.extend(mcp_tools)

    return {
        "entry": entry,
        "override_model": effective_model,
        "override_base_url": override_base_url,
        "override_api_key": override_api_key,
        "override_system_prompt": override_system_prompt,
        "override_tools": override_tools,
        "error": None,
    }
