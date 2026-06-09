from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Skills 目录
SKILLS_ROOT = Path.home() / ".MIMOClaw" / "skills"

# 将 skills 目录的父目录添加到 Python 路径，以便导入 skills 模块
_skills_parent = SKILLS_ROOT.parent
if str(_skills_parent) not in sys.path:
    sys.path.insert(0, str(_skills_parent))
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


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


def discover_skills() -> list[SkillEntry]:
    from db.skill_status import get_skill_status

    if not SKILLS_ROOT.exists():
        return []

    entries: list[SkillEntry] = []

    for child in sorted(SKILLS_ROOT.iterdir()):
        if child.name.startswith("."):
            continue

        if child.is_dir():
            skill_md_path = child / "SKILL.md"
            if not skill_md_path.is_file():
                skill_md_path = child / "skill.md"
            if not skill_md_path.is_file():
                continue
            try:
                parsed = parse_skill_markdown(skill_md_path, default_name=child.name)
            except UnicodeDecodeError:
                continue

            enabled = get_skill_status(child.name)

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
                    enabled=enabled,
                )
            )

    return entries


def get_skill_by_name(name: str) -> SkillEntry | None:
    for entry in discover_skills():
        if entry.name == name or entry.folder_name == name:
            return entry
    return None


def build_skill_runtime_context(entry: SkillEntry, task: str = "") -> str:
    lines = [
        f"已激活技能: {entry.name}",
        f"描述: {entry.description or '无描述'}",
    ]
    if task.strip():
        lines.append(f"当前任务: {task.strip()}")

    lines.extend(
        [
            "",
            f"[Skill directory: {entry.skill_path}]",
            "请将该技能中的相对路径都相对于这个目录解析。",
        ]
    )

    content = entry.content.strip()
    server_url = os.getenv("SERVER_URL", "http://localhost:8000")
    content = content.replace("{{SERVER_URL}}", server_url)
    content = content.replace("{{USER_EMAIL}}", "default")

    lines.extend(
        [
            "",
            "=== SKILL.md 内容 ===",
            content,
        ]
    )
    return "\n".join(lines).strip()


def build_skills_context_from_entries(relevant_skills: list[SkillEntry]) -> str:
    if not relevant_skills:
        return ""

    lines = [
        "【相关本地技能】",
        "以下技能与当前请求相关。优先参考这些技能的说明。",
    ]
    for entry in relevant_skills:
        lines.append(f"- {entry.name}: {entry.description or '无描述'}")

    lines.append("")
    for entry in relevant_skills:
        lines.append(f"【技能: {entry.name}】")
        lines.append(build_skill_runtime_context(entry))
        lines.append("")
    return "\n".join(lines).strip()


# 核心基础工具名称集合（这些工具由 agent_tools 提供，不应从 skills 重复加载）
CORE_TOOL_NAMES = {
    "read_file", "write_file", "edit_file", "list_files", "search_file",
    "cli_executor",
    "read_skill_file",
}


def get_all_tool_definitions() -> list[dict]:
    tools = []

    # 1. 加载 utils.agent_tools 中的核心基础工具
    try:
        from utils.agent_tools import get_tool_definitions as get_agent_tool_definitions
        agent_tools = get_agent_tool_definitions()
        if agent_tools:
            tools.extend(agent_tools)
    except Exception as e:
        print(f"Failed to load agent_tools: {e}")

    # 2. 加载 skills 目录中的工具（排除已由 agent_tools 提供的基础工具）
    for entry in discover_skills():
        if not entry.enabled:
            continue

        try:
            skill_module = __import__(
                f"skills.{entry.folder_name}",
                fromlist=["get_tool_definition", "get_tool_definitions"]
            )

            # Support skills with multiple tool definitions
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

    return tools


def execute_tool(tool_name: str, arguments: dict[str, Any] | None = None, work_dir: str | None = None) -> dict[str, Any]:
    if arguments is None:
        arguments = {}

    # 1. 先检查是否是 agent_tools 中的核心基础工具
    if tool_name in CORE_TOOL_NAMES:
        try:
            from utils.agent_tools import execute as execute_agent_tool
            return execute_agent_tool(tool=tool_name, work_dir=work_dir, **arguments)
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": f"执行 {tool_name} 失败: {str(e)}",
            }

    # 2. 查找 skills 目录中的工具
    for entry in discover_skills():
        if not entry.enabled:
            continue
        
        try:
            skill_module = __import__(
                f"skills.{entry.folder_name}",
                fromlist=["execute", "get_tool_definition", "get_tool_definitions"]
            )
            
            # Check if skill has the requested tool
            has_tool = False
            
            # Support skills with multiple tool definitions
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
            
            # Fallback to single tool definition
            if not has_tool and hasattr(skill_module, "get_tool_definition"):
                tool_def = skill_module.get_tool_definition()
                if tool_def and tool_def.get("function", {}).get("name") == tool_name:
                    has_tool = True
            
            if has_tool and hasattr(skill_module, "execute"):
                # Only pass tool name for multi-tool skills (those with get_tool_definitions)
                if hasattr(skill_module, "get_tool_definitions"):
                    arguments["tool"] = tool_name
                return skill_module.execute(**arguments)
                
        except Exception as e:
            continue
    
    return {
        "success": False,
        "error": f"Unknown tool: {tool_name}",
        "output": f"❌ 未知的工具: {tool_name}",
    }
