"""Subagent Manager - 子 Agent 配置加载与可用性管理

设计要点：
- 配置目录：~/.Aries/agent/*.json，单目录扁平结构
- 可用性：由 enabled 字段 + 依赖检查（skill/mcp 是否存在 + 模型是否可用）共同决定
- Subagent 的 allowed_skills / allowed_mcps 对内强制激活：
    即使 skill 在全局未配置给主 Agent，只要 Subagent 声明就强制可用
    （但前提是文件/配置必须存在，不存在则视为加载失败）
- model 为空 → 走系统默认模型（~/.Aries/config.json 中的 active 模型）
- 主 Agent 看到的精简字段：name / description / enabled /
  allowed_skills / allowed_mcps
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AGENT_ROOT = Path.home() / ".Aries" / "agent"

# 所有 subagent 默认继承的公共技能（在 Subagent 上下文中自动注入）
COMMON_SKILLS: tuple[str, ...] = ("file_io", "cli")

# 子 Agent 配置文件名合法字符（落盘文件名）
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
    # 运行时计算字段
    available: bool = True
    unavailable_reason: str = ""
    # 实际使用的模型（model 为空时走系统默认模型）
    effective_model: str = ""

    def to_router_dict(self) -> dict[str, Any]:
        """给主 Agent 路由表用的精简视图（不含 system_prompt 和模型信息）。"""
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
        """给前端 UI 用的完整视图（含 system_prompt 与路径）。"""
        data = self.to_router_dict()
        data["model"] = self.model
        data["system_prompt"] = self.system_prompt
        data["config_path"] = str(self.config_path) if self.config_path else ""
        return data


def ensure_agent_dir() -> None:
    AGENT_ROOT.mkdir(parents=True, exist_ok=True)


def _is_valid_filename(name: str) -> bool:
    return bool(_NAME_SAFE_PATTERN.match(name))


def _config_path_for(name: str) -> Path:
    if not _is_valid_filename(name):
        raise ValueError(f"Subagent 名称只允许字母、数字、点、下划线、短横线：{name}")
    return AGENT_ROOT / f"{name}.json"


def _normalize_entry(raw: dict[str, Any], fallback_name: str, path: Path) -> SubagentEntry:
    name = str(raw.get("name") or fallback_name).strip()
    description = str(raw.get("description") or "").strip()
    model = str(raw.get("model") or "").strip()
    enabled = bool(raw.get("enabled", True))
    raw_sp = raw.get("system_prompt")
    if isinstance(raw_sp, list):
        system_prompt = "\n".join(str(line).strip() for line in raw_sp if str(line).strip())
    else:
        system_prompt = str(raw_sp or "").strip()

    def _str_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    return SubagentEntry(
        name=name,
        description=description,
        model=model,
        enabled=enabled,
        allowed_skills=_str_list(raw.get("allowed_skills")),
        allowed_mcps=_str_list(raw.get("allowed_mcps")),
        system_prompt=system_prompt,
        config_path=path,
    )
def _check_model_available(model: str) -> bool:
    """检查模型是否可用。空字符串视为不可用。

    比对的是 ModelItem.model（实际模型名，如 kimi-k2.6），
    而非 ModelItem.id（内部 UUID 如 model-a1b2c3d4）。
    """
    if not model or not model.strip():
        return False
    try:
        from models.model_manager import model_manager  # type: ignore

        models = model_manager.list_models()
        for m in models:
            if isinstance(m, dict):
                mid = m.get("model") or m.get("id") or m.get("name") or ""
            else:
                mid = getattr(m, "model", "") or getattr(m, "id", "") or getattr(m, "name", "") or ""
            if mid == model:
                return True
        return False
    except Exception as exc:
        logger.debug("model_manager 不可用，跳过模型校验: %s", exc)
    # 没有 model_manager 时不阻塞 subagent，默认通过
    return True


def _check_skill_exists(skill_name: str) -> bool:
    """检查 skill 是否在用户目录或内置插件中存在。"""
    try:
        from engine.skills_manager import get_skill_by_folder_name
        from engine.plugin_manager import get_plugin_skill_dirs

        # 用户 skills
        if get_skill_by_folder_name(skill_name) is not None:
            return True
        # 内置插件 skills
        for plugin_dir in get_plugin_skill_dirs():
            if plugin_dir.name == skill_name:
                return True
        return False
    except Exception as exc:
        logger.debug("检查 skill 存在性失败: %s", exc)
        return False


def _check_mcp_exists(mcp_name: str) -> bool:
    """检查 mcp 是否在 ~/.Aries/mcp.json 中配置。"""
    try:
        from aries_mcp.config import load_mcp_config

        config = load_mcp_config()
        servers = config.get("mcpServers") or {}
        return isinstance(servers, dict) and mcp_name in servers
    except Exception as exc:
        logger.debug("mcp_config.load_mcp_config 调用失败: %s", exc)
        return False


def _compute_availability(entry: SubagentEntry) -> None:
    """根据 enabled + 依赖检查计算 available / effective_model。结果写回 entry。

    model 为空 → 走系统默认模型（不阻塞加载）。
    model 非空但不存在 → 标记不可用。
    """
    if not entry.enabled:
        entry.available = False
        entry.unavailable_reason = "已被用户禁用"
        entry.effective_model = entry.model
        return

    # model 为空 → 走系统默认模型
    if not entry.model:
        entry.effective_model = ""
    elif _check_model_available(entry.model):
        entry.effective_model = entry.model
    else:
        entry.effective_model = entry.model
        entry.available = False
        entry.unavailable_reason = f"模型 {entry.model} 不可用"
        return

    # 依赖 skill / mcp 是否"存在"（不要求 available/enabled）
    for skill in entry.allowed_skills:
        if not _check_skill_exists(skill):
            entry.available = False
            entry.unavailable_reason = f"依赖 skill 不存在：{skill}"
            return
    for mcp in entry.allowed_mcps:
        if not _check_mcp_exists(mcp):
            entry.available = False
            entry.unavailable_reason = f"依赖 mcp 配置不存在：{mcp}"
            return

    entry.available = True
    entry.unavailable_reason = ""


def discover_subagents() -> list[SubagentEntry]:
    """扫描 ~/.Aries/agent/*.json，返回全部条目（含 disabled / unavailable）。

    自动跳过 main_agent.json（主 Agent 配置，不是子 Agent）。
    同时加载内置插件 agents（~/.Aries/plugins/agents/）。
    """
    ensure_agent_dir()
    entries: list[SubagentEntry] = []
    seen_names: set[str] = set()

    from utils._config_loader import discover_json_configs

    for path in discover_json_configs(AGENT_ROOT):
        if path.name == "main_agent.json":
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"), strict=False)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("解析 subagent 配置失败 %s: %s", path, exc)
            continue
        if not isinstance(raw, dict):
            logger.warning("subagent 配置必须是 JSON 对象：%s", path)
            continue
        fallback_name = path.stem
        entry = _normalize_entry(raw, fallback_name=fallback_name, path=path)
        _compute_availability(entry)
        entries.append(entry)
        seen_names.add(entry.name)

    # 加载内置插件 agents
    try:
        from engine.plugin_manager import get_plugin_agent_configs
        for raw in get_plugin_agent_configs():
            name = str(raw.get("name") or "").strip()
            if not name or name in seen_names:
                continue
            # 插件 agent 没有实际文件路径，用 name 作为 fallback
            entry = _normalize_entry(raw, fallback_name=name, path=Path(raw.get("_source_path", "")))
            _compute_availability(entry)
            entries.append(entry)
            seen_names.add(name)
    except Exception as exc:
        logger.debug("加载插件 agents 失败: %s", exc)

    return entries


def get_subagent_by_name(name: str) -> SubagentEntry | None:
    for entry in discover_subagents():
        if entry.name == name or (entry.config_path and entry.config_path.stem == name):
            return entry
    return None


def list_available_subagents() -> list[SubagentEntry]:
    """仅返回可被主 Agent 路由的 subagent。"""
    return [e for e in discover_subagents() if e.available]


def save_subagent(payload: dict[str, Any]) -> SubagentEntry:
    """新建或覆盖 subagent 配置。返回保存后的 entry。"""
    ensure_agent_dir()
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("name 不能为空")
    if not _is_valid_filename(name):
        raise ValueError("name 只允许字母、数字、点、下划线、短横线")

    path = _config_path_for(name)
    # 仅保留已知字段，避免脏数据
    data = {
        "name": name,
        "description": str(payload.get("description") or "").strip(),
        "model": str(payload.get("model") or "").strip(),
        "enabled": bool(payload.get("enabled", True)),
        "allowed_skills": [
            str(item).strip()
            for item in (payload.get("allowed_skills") or [])
            if str(item).strip()
        ],
        "allowed_mcps": [
            str(item).strip()
            for item in (payload.get("allowed_mcps") or [])
            if str(item).strip()
        ],
        "system_prompt": str(payload.get("system_prompt") or ""),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    entry = _normalize_entry(data, fallback_name=name, path=path)
    _compute_availability(entry)
    return entry


def delete_subagent(name: str) -> bool:
    path = _config_path_for(name)
    if path.is_file():
        path.unlink()
        return True
    return False


def set_subagent_enabled(name: str, enabled: bool) -> SubagentEntry:
    entry = get_subagent_by_name(name)
    if entry is None or entry.config_path is None:
        raise FileNotFoundError(f"Subagent {name} 不存在")
    raw = json.loads(entry.config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Subagent 配置异常：{entry.config_path}")
    raw["enabled"] = bool(enabled)
    entry.config_path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return _reload(entry.config_path)


def _reload(path: Path) -> SubagentEntry:
    raw = json.loads(path.read_text(encoding="utf-8"), strict=False)
    entry = _normalize_entry(raw, fallback_name=path.stem, path=path)
    _compute_availability(entry)
    return entry


def build_subagent_router_section(entries: list[SubagentEntry] | None = None) -> str:
    """构造给主 Agent system prompt 用的精简路由表（仅展示 available=True 的条目）。

    输出格式：
        ## Available Subagents
        - <name> | 描述 | 技能: [a, b] | MCP: [x]
    """
    if entries is None:
        entries = list_available_subagents()
    if not entries:
        return ""

    lines = [
        "# Available Subagents（可委派的子 Agent）",
        "下列子 Agent 可由你委派任务。每个 Subagent 拥有独立上下文与能力组合，",
        f"所有 Subagent 默认自动注入公共技能：{', '.join(COMMON_SKILLS)}（无需在 allowed_skills 中声明）。",
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


# ---- Subagent 运行时上下文 ----
# 供后续 Subagent 执行引擎调用。核心要点：
# - allowed_skills 强制激活：即使 skill 未配置给主 Agent 也会被加载
# - allowed_mcps 强制激活：即使 mcp.json 中 enabled=false 也会为该 subagent 暴露工具
# - 公共技能 COMMON_SKILLS 默认追加（去重）

def _load_skill_entry_anywhere(skill_name: str):
    """加载 skill 完整信息（用户 skills 优先，其次内置插件 skills）。"""
    from engine.skills_manager import get_skill_by_name
    from engine.plugin_manager import discover_plugins

    entry = get_skill_by_name(skill_name)
    if entry is not None:
        return entry

    # 内置插件 skills
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
    """拼接 subagent 持有的所有 skill 的 SKILL.md 内容（去重，含 COMMON_SKILLS）。"""
    from engine.skills_manager import build_skills_context_from_entries

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
    """根据 subagent 名称构造其运行时上下文。

    返回字段：
        entry: SubagentEntry 本身
        system_prompt: subagent 自身的 system_prompt（用户在 yaml 中写的）
        skills_context: 强制激活的全部 skill 内容拼接
        skill_entries: list[SkillEntry]，供执行引擎按需取 import path
        mcp_servers: list[str]，subagent 持有的 mcp 名称（强制激活）
        effective_model: 实际使用的模型 id（空字符串表示走系统默认）

    若 subagent 不存在或依赖的 skill / mcp 在系统中根本找不到，抛 ValueError。
    """
    entry = get_subagent_by_name(name)
    if entry is None:
        raise ValueError(f"Subagent 不存在：{name}")

    # 1. 检查 skill 存在性（含 unavailable；用户 skills + 内置插件 skills）
    skill_entries = []
    for skill_name in list(entry.allowed_skills) + list(COMMON_SKILLS):
        sk = _load_skill_entry_anywhere(skill_name)
        if sk is None and skill_name not in COMMON_SKILLS:
            # 公共技能允许缺失（向后兼容），声明的 skill 必须存在
            raise ValueError(f"Subagent {name} 依赖的 skill 不存在：{skill_name}")
        if sk is not None:
            skill_entries.append(sk)

    # 2. 检查 mcp 配置存在性（不要求 enabled）
    from aries_mcp.config import load_mcp_config

    mcp_servers_cfg = load_mcp_config().get("mcpServers") or {}
    for mcp_name in entry.allowed_mcps:
        if mcp_name not in mcp_servers_cfg:
            raise ValueError(f"Subagent {name} 依赖的 mcp 配置不存在：{mcp_name}")

    skills_context = _build_subagent_skills_context(entry.allowed_skills)

    return {
        "entry": entry,
        "system_prompt": entry.system_prompt,
        "skills_context": skills_context,
        "skill_entries": skill_entries,
        "mcp_servers": list(entry.allowed_mcps),
        "effective_model": entry.effective_model or entry.model,
    }


def _build_subagent_skill_tool_definitions(skill_entries: list[Any]) -> list[dict[str, Any]]:
    """基于 skill_entries 加载工具定义 schema（强制激活，不检查 enabled）。"""
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
    """按 server_id 过滤 MCP 工具定义。MCP 工具名约定为 `mcp_{server_id}_{tool}`。"""
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
    """构建子 Agent 直接作为对话主体时所需的覆盖配置。

    返回：
        {
            "entry": SubagentEntry,
            "override_model": str,              # 实际使用的模型（可能为空，表示走系统默认）
            "override_system_prompt": str,      # 完整 system prompt
            "override_tools": list[dict],       # 工具定义（含核心工具 + allowed skills + allowed mcps）
            "error": str | None,
        }
    """
    try:
        runtime = build_subagent_runtime(name)
    except ValueError as exc:
        return {"entry": None, "override_model": "", "override_system_prompt": "", "override_tools": [], "error": str(exc)}

    entry = runtime["entry"]
    skills_context = runtime["skills_context"]
    skill_entries = runtime["skill_entries"]
    mcp_servers = runtime["mcp_servers"]

    # 解析子 Agent 模型对应的 API 凭证（baseUrl / apiKey）
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
    # 若子 Agent 未指定模型或未匹配到，回退到当前 request 的凭证（由调用方处理）


    # 构造 system prompt
    import platform
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    parts: list[str] = [
        f"# 你的身份\n你是一个 AI 助手：`{entry.name}`。今天的日期是 {today}，当前操作系统：{platform.system()}。\n",
    ]
    if entry.system_prompt.strip():
        parts.append(f"# 详细职责\n{entry.system_prompt.strip()}\n")

    # 注入项目记忆
    if work_dir and work_dir.strip():
        try:
            from memory.agent_memory import build_agent_memory_system_section
            memory_section = build_agent_memory_system_section(work_dir)
            if memory_section:
                parts.append(memory_section)
        except Exception:
            pass

    # 注入编码行为约束
    try:
        from prompt.coding_agent_prompts import (
            DOING_TASKS_RULES,
            CODE_STYLE_RULES,
            COMPLETION_HONESTY_RULES,
        )
        parts.append(
            "# 编码行为约束\n"
            + DOING_TASKS_RULES + "\n\n"
            + CODE_STYLE_RULES + "\n\n"
            + COMPLETION_HONESTY_RULES
        )
    except Exception:
        pass

    # 注入 session 上下文（仅作提示）
    if session_id:
        parts.append(f"# 当前会话\n当前 session_id：`{session_id}`。请保持回答简洁、可执行。")

    if skills_context:
        parts.append("# 可用本地 Skills\n" + skills_context)

    override_system_prompt = "\n\n".join(parts)

    # 构造工具集：核心工具 + 子 Agent 技能 + 过滤后的 MCP
    # 显式不暴露 delegate_to_subagent，防止递归
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
