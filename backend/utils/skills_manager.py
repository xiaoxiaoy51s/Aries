from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Skills 目录：available 可加载，unavailable 仅展示不可加载
SKILLS_ROOT = Path.home() / ".Aries" / "skills"
SKILLS_AVAILABLE_DIR = SKILLS_ROOT / "available"
SKILLS_UNAVAILABLE_DIR = SKILLS_ROOT / "unavailable"
RESERVED_SKILL_DIRS = frozenset({"available", "unavailable"})

# 将 skills 目录的父目录添加到 Python 路径，以便导入 skills 模块
_skills_parent = SKILLS_ROOT.parent
if str(_skills_parent) not in sys.path:
    sys.path.insert(0, str(_skills_parent))

_layout_initialized = False
_legacy_cleanup_failed: set[str] = set()
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


def _touch_package_init(path: Path) -> None:
    init_file = path / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8")


def _clear_skill_module_cache(folder_name: str) -> None:
    for key in (
        f"skills.available.{folder_name}",
        f"skills.unavailable.{folder_name}",
        f"skills.{folder_name}",
    ):
        sys.modules.pop(key, None)


def _cleanup_empty_legacy_skill_dir(path: Path) -> None:
    """迁移失败后可能留下空目录，尽力清理一次；失败则静默跳过（不影响使用）。"""
    if path.parent != SKILLS_ROOT or not path.is_dir():
        return
    if path.name in RESERVED_SKILL_DIRS or path.name.startswith("."):
        return
    if path.name in _legacy_cleanup_failed:
        return
    try:
        if any(path.iterdir()):
            return
        path.rmdir()
    except OSError as exc:
        # WinError 32：目录被其他进程占用（常见于后端/IDE/Playwright 曾加载过该路径）
        # 空壳目录不影响 skill 加载（available/ 下已有完整副本），不再重复告警
        winerr = getattr(exc, "winerror", None)
        if winerr == 32 or exc.errno in (13, 16, 32):
            _legacy_cleanup_failed.add(path.name)
            return
        print(f"[skills] 清理空目录 {path.name} 失败: {exc}")


def _migrate_legacy_layout() -> None:
    """一次性迁移：顶层 skill 目录 → available；数据库中禁用的 → unavailable。"""
    SKILLS_ROOT.mkdir(parents=True, exist_ok=True)
    SKILLS_AVAILABLE_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_UNAVAILABLE_DIR.mkdir(parents=True, exist_ok=True)
    _touch_package_init(SKILLS_ROOT)
    _touch_package_init(SKILLS_AVAILABLE_DIR)
    _touch_package_init(SKILLS_UNAVAILABLE_DIR)

    for child in sorted(SKILLS_ROOT.iterdir()):
        if not child.is_dir() or child.name in RESERVED_SKILL_DIRS or child.name.startswith("."):
            continue
        target = SKILLS_AVAILABLE_DIR / child.name
        if target.exists():
            _cleanup_empty_legacy_skill_dir(child)
            continue
        if not _is_skill_dir(child):
            continue
        try:
            shutil.move(str(child), str(target))
        except OSError as exc:
            print(f"[skills] 迁移 {child.name} 到 available 失败: {exc}")
            if target.exists():
                _cleanup_empty_legacy_skill_dir(child)

    try:
        from db.database import get_connection

        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT folder_name FROM skills WHERE enabled = 0"
            ).fetchall()
        finally:
            conn.close()
        for row in rows:
            folder_name = (row["folder_name"] or "").strip()
            if not folder_name:
                continue
            src = SKILLS_AVAILABLE_DIR / folder_name
            dst = SKILLS_UNAVAILABLE_DIR / folder_name
            if src.is_dir() and not dst.exists():
                try:
                    shutil.move(str(src), str(dst))
                    _clear_skill_module_cache(folder_name)
                except OSError as exc:
                    print(f"[skills] 迁移 {folder_name} 到 unavailable 失败: {exc}")
    except Exception:
        pass


def ensure_skills_layout() -> None:
    global _layout_initialized
    if _layout_initialized:
        return
    _migrate_legacy_layout()
    _layout_initialized = True


def skill_import_path(folder_name: str, *, enabled: bool = True, skill_path: Path | None = None) -> str:
    if skill_path is not None:
        if skill_path.parent == SKILLS_AVAILABLE_DIR:
            return f"skills.available.{folder_name}"
        if skill_path.parent == SKILLS_UNAVAILABLE_DIR:
            return f"skills.unavailable.{folder_name}"
        return f"skills.{folder_name}"
    bucket = "available" if enabled else "unavailable"
    return f"skills.{bucket}.{folder_name}"


def find_skill_dir(folder_name: str) -> tuple[Path, bool] | None:
    """返回 (skill_path, enabled)。"""
    ensure_skills_layout()
    available = SKILLS_AVAILABLE_DIR / folder_name
    if available.is_dir() and _is_skill_dir(available):
        return available, True
    unavailable = SKILLS_UNAVAILABLE_DIR / folder_name
    if unavailable.is_dir() and _is_skill_dir(unavailable):
        return unavailable, False
    legacy = SKILLS_ROOT / folder_name
    if legacy.is_dir() and _is_skill_dir(legacy):
        return legacy, True
    return None


def is_skill_enabled(folder_name: str) -> bool:
    found = find_skill_dir(folder_name)
    return found is not None and found[1]


def set_skill_enabled(folder_name: str, enabled: bool) -> None:
    ensure_skills_layout()
    found = find_skill_dir(folder_name)
    if found is None:
        raise FileNotFoundError(f"技能 {folder_name} 不存在")

    current_path, currently_enabled = found
    if currently_enabled == enabled:
        return

    target_root = SKILLS_AVAILABLE_DIR if enabled else SKILLS_UNAVAILABLE_DIR
    target_path = target_root / folder_name
    if target_path.exists():
        raise FileExistsError(f"目标目录已存在: {target_path}")

    try:
        shutil.move(str(current_path), str(target_path))
    except OSError as exc:
        raise OSError(f"迁移技能目录失败: {exc}") from exc
    _clear_skill_module_cache(folder_name)


def _iter_skill_dirs() -> list[tuple[Path, bool]]:
    ensure_skills_layout()
    items: list[tuple[Path, bool]] = []
    seen: set[str] = set()

    for child in sorted(SKILLS_AVAILABLE_DIR.iterdir()):
        if _is_skill_dir(child):
            items.append((child, True))
            seen.add(child.name)
    for child in sorted(SKILLS_UNAVAILABLE_DIR.iterdir()):
        if _is_skill_dir(child):
            items.append((child, False))
            seen.add(child.name)

    # 兼容尚未迁移成功的顶层 skill 目录
    if SKILLS_ROOT.exists():
        for child in sorted(SKILLS_ROOT.iterdir()):
            if child.name in seen or child.name in RESERVED_SKILL_DIRS or child.name.startswith("."):
                continue
            if _is_skill_dir(child):
                items.append((child, True))
                seen.add(child.name)

    return items


def discover_skills() -> list[SkillEntry]:
    if not SKILLS_ROOT.exists():
        return []

    entries: list[SkillEntry] = []

    for child, enabled in _iter_skill_dirs():
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
                enabled=enabled,
            )
        )

    return entries


def get_skill_by_folder_name(folder_name: str) -> SkillEntry | None:
    for entry in discover_skills():
        if entry.folder_name == folder_name:
            return entry
    return None


def get_skill_by_name(name: str, *, enabled_only: bool = True) -> SkillEntry | None:
    for entry in discover_skills():
        if enabled_only and not entry.enabled:
            continue
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
    "write_agent_memory",
    "create_scheduled_task",
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
                skill_import_path(entry.folder_name, enabled=True, skill_path=entry.skill_path),
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

    # 3. 加载用户配置的 MCP 插件工具（仅 enabled 的服务）
    try:
        from utils.mcp_runtime import get_mcp_tool_definitions
        mcp_tools = get_mcp_tool_definitions()
        if mcp_tools:
            tools.extend(mcp_tools)
    except Exception as e:
        print(f"Failed to load MCP tool definitions: {e}")

    # 4. 注入 capability_search 工具，供主 Agent 检索 skill/mcp/subagent 全集
    try:
        from utils.capability_registry import (
            get_capability_search_tool_definition,
            get_delegate_to_subagent_tool_definition,
        )
        tools.append(get_capability_search_tool_definition())
        tools.append(get_delegate_to_subagent_tool_definition())
    except Exception as e:
        print(f"Failed to load capability_search tool definition: {e}")

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

    # 0a. capability_search：检索 skill / mcp / subagent 全集
    try:
        from utils.capability_registry import (
            CAPABILITY_SEARCH_TOOL_NAME,
            DELEGATE_TO_SUBAGENT_TOOL_NAME,
            execute_capability_search,
        )
        if tool_name == CAPABILITY_SEARCH_TOOL_NAME:
            return execute_capability_search(arguments)
        if tool_name == DELEGATE_TO_SUBAGENT_TOOL_NAME:
            return {
                "success": False,
                "error": "delegate_to_subagent 必须由主 Agent 的 async 执行路径处理",
                "output": "内部错误：delegate_to_subagent 不应进入同步执行通道",
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "output": f"执行 {tool_name} 失败: {str(e)}",
        }

    # 0. MCP 插件工具（来自 ~/.Aries/mcp.json 中已启用的服务）
    try:
        from utils.mcp_runtime import execute_mcp_tool
        mcp_result = execute_mcp_tool(tool_name, arguments)
        if mcp_result is not None:
            return mcp_result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "output": f"执行 MCP 工具 {tool_name} 失败: {str(e)}",
        }

    # 1. 先检查是否是 agent_tools 中的核心基础工具
    if tool_name in CORE_TOOL_NAMES:
        try:
            from utils.agent_tools import execute as execute_agent_tool
            return execute_agent_tool(
                tool=tool_name,
                work_dir=work_dir,
                session_id=session_id,
                invocation_id=invocation_id,
                **arguments,
            )
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
                skill_import_path(entry.folder_name, enabled=True, skill_path=entry.skill_path),
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
