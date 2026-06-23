from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Skills 根目录
SKILLS_ROOT = Path.home() / ".Aries" / "skills"

# 将 skills 父目录添加到 Python 路径，以便导入 skills.{folder_name}
_skills_parent = SKILLS_ROOT.parent
if str(_skills_parent) not in sys.path:
    sys.path.insert(0, str(_skills_parent))


@dataclass
class SkillEntry:
    name: str
    description: str
    folder_name: str
    skill_path: Path
    skill_md_path: Path
    content: str
    body: str
    frontmatter: dict[str, Any]
    enabled: bool = True

    def to_api_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "folder_name": self.folder_name,
            "path": str(self.skill_path),
            "skill_md_path": str(self.skill_md_path),
            "enabled": self.enabled,
            "group": "personal",
        }


def _yaml_load(content: str) -> dict[str, Any]:
    lines = content.strip().splitlines()
    result: dict[str, Any] = {}
    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip("\"'")
    return result


def parse_skill_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith("---"):
        return {}, content
    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return {}, content
    yaml_content = content[3 : end_match.start() + 3]
    body = content[end_match.end() + 3 :]
    try:
        return _yaml_load(yaml_content), body
    except Exception:
        return {}, body


def parse_skill_markdown(skill_md_path: Path, default_name: str) -> dict[str, Any]:
    content = skill_md_path.read_text(encoding="utf-8")
    frontmatter, body = parse_skill_frontmatter(content)
    name = str(frontmatter.get("name") or default_name).strip().strip("\"'")
    description = str(frontmatter.get("description") or "").strip().strip("\"'")
    if not description:
        title_match = re.search(r"^#\s+(.+)$", body or content, re.MULTILINE)
        if title_match:
            description = title_match.group(1).strip()
    return {
        "name": name or default_name,
        "description": description,
        "content": content,
        "body": body,
        "frontmatter": frontmatter,
    }


def _is_skill_dir(path: Path) -> bool:
    if not path.is_dir() or path.name.startswith("."):
        return False
    return (path / "SKILL.md").is_file() or (path / "skill.md").is_file()


def skill_import_path(folder_name: str) -> str:
    """技能模块导入路径。"""
    return f"skills.{folder_name}"


def _iter_skill_dirs() -> list[Path]:
    """遍历 skills/ 目录下所有技能目录。"""
    items: list[Path] = []
    if not SKILLS_ROOT.exists():
        return items
    for child in sorted(SKILLS_ROOT.iterdir()):
        if _is_skill_dir(child):
            items.append(child)
    return items


def discover_skills() -> list[SkillEntry]:
    if not SKILLS_ROOT.exists():
        return []
    entries: list[SkillEntry] = []
    for child in _iter_skill_dirs():
        skill_md_path = child / "SKILL.md"
        if not skill_md_path.is_file():
            skill_md_path = child / "skill.md"
        try:
            parsed = parse_skill_markdown(skill_md_path, default_name=child.name)
        except UnicodeDecodeError:
            continue
        entries.append(
            SkillEntry(
                name=parsed["name"],
                description=parsed["description"],
                folder_name=child.name,
                skill_path=child,
                skill_md_path=skill_md_path,
                content=parsed["content"],
                body=parsed["body"],
                frontmatter=parsed["frontmatter"],
                enabled=True,
            )
        )
    return entries


def get_skill_by_folder_name(folder_name: str) -> SkillEntry | None:
    for entry in discover_skills():
        if entry.folder_name == folder_name:
            return entry
    return None


def get_skill_by_name(name: str) -> SkillEntry | None:
    for entry in discover_skills():
        if entry.name == name or entry.folder_name == name:
            return entry
    return None


def build_skill_runtime_context(entry: SkillEntry, task: str = "") -> str:
    lines = [f"已激活技能: {entry.name}", f"描述: {entry.description or '无描述'}"]
    if task.strip():
        lines.append(f"当前任务: {task.strip()}")
    lines.extend(["", f"[Skill directory: {entry.skill_path}]", "请将该技能中的相对路径都相对于这个目录解析。"])
    content = entry.content.strip()
    server_url = os.getenv("SERVER_URL", "http://localhost:8000")
    content = content.replace("{{SERVER_URL}}", server_url)
    content = content.replace("{{USER_EMAIL}}", "default")
    lines.extend(["", "=== SKILL.md 内容 ===", content])
    return "\n".join(lines).strip()


def build_skills_context_from_entries(relevant_skills: list[SkillEntry]) -> str:
    if not relevant_skills:
        return ""
    lines = ["【相关本地技能】", "以下技能与当前请求相关。优先参考这些技能的说明。"]
    for entry in relevant_skills:
        lines.append(f"- {entry.name}: {entry.description or '无描述'}")
    lines.append("")
    for entry in relevant_skills:
        lines.append(f"【技能: {entry.name}】")
        lines.append(build_skill_runtime_context(entry))
        lines.append("")
    return "\n".join(lines).strip()


CORE_TOOL_NAMES = {
    "read_file", "write_file", "edit_file", "list_files", "search_file",
    "cli_executor",
    "read_skill_file",
    "write_agent_memory",
    "create_scheduled_task",
    "replace_string", "multi_replace_string", "apply_patch",
}


def get_all_tool_definitions() -> list[dict]:
    from utils.main_agent_config import get_main_agent_allowed_skills, get_main_agent_allowed_mcps
    allowed_skills = get_main_agent_allowed_skills()
    tools = []

    try:
        from utils.agent_tools import get_tool_definitions as get_agent_tool_definitions
        agent_tools = get_agent_tool_definitions()
        if agent_tools:
            tools.extend(agent_tools)
    except Exception as e:
        print(f"Failed to load agent_tools: {e}")

    for entry in discover_skills():
        if not allowed_skills or entry.folder_name not in allowed_skills:
            continue
        try:
            skill_module = __import__(
                skill_import_path(entry.folder_name),
                fromlist=["get_tool_definition", "get_tool_definitions"]
            )
            if hasattr(skill_module, "get_tool_definitions"):
                tool_defs = skill_module.get_tool_definitions()
                if tool_defs:
                    if isinstance(tool_defs, list):
                        for tool_def in tool_defs:
                            name = tool_def.get("function", {}).get("name")
                            if name not in CORE_TOOL_NAMES:
                                tools.append(tool_def)
                    else:
                        name = tool_defs.get("function", {}).get("name")
                        if name not in CORE_TOOL_NAMES:
                            tools.append(tool_defs)
            elif hasattr(skill_module, "get_tool_definition"):
                tool_def = skill_module.get_tool_definition()
                if tool_def:
                    name = tool_def.get("function", {}).get("name")
                    if name not in CORE_TOOL_NAMES:
                        tools.append(tool_def)
        except Exception as e:
            print(f"Failed to load tool definition for {entry.name}: {e}")

    try:
        from utils.mcp_runtime import get_mcp_tool_definitions
        mcp_tools = get_mcp_tool_definitions(allowed_mcp_ids=get_main_agent_allowed_mcps())
        if mcp_tools:
            tools.extend(mcp_tools)
    except Exception as e:
        print(f"Failed to load MCP tool definitions: {e}")

    # capability_search 暂时注释，避免 AI 每次都去检索
    # try:
    #     from utils.capability_registry import get_capability_search_tool_definition
    #     tools.append(get_capability_search_tool_definition())
    # except Exception as e:
    #     print(f"Failed to load capability_search tool definition: {e}")

    try:
        from utils.capability_registry import get_delegate_to_subagent_tool_definition
        tools.append(get_delegate_to_subagent_tool_definition())
    except Exception as e:
        print(f"Failed to load delegate_to_subagent tool definition: {e}")

    return tools


def execute_tool(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    work_dir: str | None = None,
    session_id: str | None = None,
    invocation_id: str | None = None,
) -> dict[str, Any]:
    if arguments is None:
        arguments = {}

    try:
        from utils.capability_registry import CAPABILITY_SEARCH_TOOL_NAME, DELEGATE_TO_SUBAGENT_TOOL_NAME, execute_capability_search
        if tool_name == CAPABILITY_SEARCH_TOOL_NAME:
            return execute_capability_search(arguments)
        if tool_name == DELEGATE_TO_SUBAGENT_TOOL_NAME:
            return {"success": False, "error": "delegate_to_subagent 必须由主 Agent 的 async 执行路径处理", "output": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "output": f"执行 {tool_name} 失败: {str(e)}"}

    try:
        from utils.mcp_runtime import execute_mcp_tool
        mcp_result = execute_mcp_tool(tool_name, arguments)
        if mcp_result is not None:
            return mcp_result
    except Exception as e:
        return {"success": False, "error": str(e), "output": f"执行 MCP 工具 {tool_name} 失败: {str(e)}"}

    if tool_name in CORE_TOOL_NAMES:
        try:
            from utils.agent_tools import execute as execute_agent_tool
            return execute_agent_tool(tool=tool_name, work_dir=work_dir, session_id=session_id, invocation_id=invocation_id, **arguments)
        except Exception as e:
            return {"success": False, "error": str(e), "output": f"执行 {tool_name} 失败: {str(e)}"}

    for entry in discover_skills():
        try:
            skill_module = __import__(
                skill_import_path(entry.folder_name),
                fromlist=["execute", "get_tool_definition", "get_tool_definitions"]
            )
            has_tool = False
            if hasattr(skill_module, "get_tool_definitions"):
                tool_defs = skill_module.get_tool_definitions()
                if tool_defs:
                    if isinstance(tool_defs, list):
                        for tool_def in tool_defs:
                            if tool_def.get("function", {}).get("name") == tool_name:
                                has_tool = True
                                break
                    elif tool_defs.get("function", {}).get("name") == tool_name:
                        has_tool = True
            if not has_tool and hasattr(skill_module, "get_tool_definition"):
                tool_def = skill_module.get_tool_definition()
                if tool_def and tool_def.get("function", {}).get("name") == tool_name:
                    has_tool = True
            if has_tool and hasattr(skill_module, "execute"):
                if hasattr(skill_module, "get_tool_definitions"):
                    arguments["tool"] = tool_name
                return skill_module.execute(**arguments)
        except Exception:
            continue

    return {"success": False, "error": f"Unknown tool: {tool_name}", "output": f"❌ 未知的工具: {tool_name}"}