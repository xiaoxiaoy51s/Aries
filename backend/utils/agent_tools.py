"""Agent 基础工具 - 委托给 file_manager / cli_executor 等核心能力

这些工具的 schema 必须在每次会话开始时注册到 LLM 工具列表中，
否则 AI 看不到 write_file / read_file 等基础文件操作能力，
会错误地选择 xlsx、pdf 等领域技能来写入纯文本文件。
"""
from __future__ import annotations

import traceback
from typing import Any


def get_tool_definitions() -> list[dict]:
    """返回核心基础工具的 OpenAI 风格 function calling 定义列表。"""
    definitions: list[dict] = []

    try:
        from utils.file_manager import FileManagerTool
        fm = FileManagerTool()
        definitions.extend(fm.get_tool_definitions())
    except Exception as exc:
        print(f"Failed to load file_manager tool definitions: {exc}")

    try:
        from utils.cli_executor import CLIExecutor
        executor = CLIExecutor()
        definitions.append(executor.get_tool_definition())
    except Exception as exc:
        print(f"Failed to load cli_executor tool definition: {exc}")

    try:
        from utils.skills_manager import get_skill_by_name
        definitions.append(_build_read_skill_file_definition())
    except Exception:
        pass

    return definitions


def _build_read_skill_file_definition() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "read_skill_file",
            "description": (
                "读取指定技能目录中的文件内容。"
                "当技能 SKILL.md 引用了其他文件（如 prompt 模板、脚本、说明文档）时使用。"
                "路径相对于技能目录。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "技能目录名（与 ~/.MIMOClaw/skills/ 下的子目录名一致）。",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "技能目录内的相对文件路径，例如 'templates/prompt.md'。",
                    },
                    "encoding": {
                        "type": "string",
                        "default": "utf-8",
                    },
                },
                "required": ["skill_name", "file_path"],
                "additionalProperties": False,
            },
        },
    }


def _get_file_manager(work_dir: str | None) -> Any:
    from utils.file_manager import FileManagerTool
    return FileManagerTool(work_dir=work_dir)


def _handle_read_skill_file(arguments: dict[str, Any]) -> dict[str, Any]:
    skill_name = str(arguments.get("skill_name") or "").strip()
    file_path = str(arguments.get("file_path") or "").strip()
    encoding = str(arguments.get("encoding") or "utf-8")
    if not skill_name or not file_path:
        return {
            "success": False,
            "error": "缺少 skill_name 或 file_path 参数",
            "output": "缺少 skill_name 或 file_path 参数",
        }
    try:
        from utils.skills_manager import get_skill_by_name
        entry = get_skill_by_name(skill_name)
        if entry is None:
            return {
                "success": False,
                "error": f"技能不存在: {skill_name}",
                "output": f"技能不存在: {skill_name}",
            }
        target = (entry.skill_path / file_path).resolve()
        if not str(target).startswith(str(entry.skill_path.resolve())):
            return {
                "success": False,
                "error": "非法的文件路径（越界）",
                "output": "非法的文件路径（越界）",
            }
        if not target.exists() or not target.is_file():
            return {
                "success": False,
                "error": f"技能文件不存在: {file_path}",
                "output": f"技能文件不存在: {file_path}",
            }
        content = target.read_text(encoding=encoding, errors="replace")
        return {
            "success": True,
            "error": "",
            "output": content,
            "file_path": str(target),
            "skill": skill_name,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "output": traceback.format_exc(),
        }


def execute(tool: str = "", work_dir: str = "", **kwargs) -> dict:
    """执行核心基础工具。"""
    try:
        if tool == "cli_executor":
            from utils.cli_executor import CLIExecutor
            executor = CLIExecutor(work_dir=work_dir)
            cli_kwargs = dict(kwargs)
            if work_dir and "working_dir" not in cli_kwargs:
                cli_kwargs["working_dir"] = work_dir
            return executor.execute(**cli_kwargs)

        if tool == "read_skill_file":
            return _handle_read_skill_file(kwargs)

        fm = _get_file_manager(work_dir)

        if tool == "read_file":
            return fm.execute_read_file(**kwargs)
        if tool == "write_file":
            return fm.execute_write_file(**kwargs)
        if tool == "edit_file":
            return fm.execute_edit_file(**kwargs)
        if tool == "list_files":
            return fm.execute_list_files(**kwargs)
        if tool == "search_file":
            return fm.execute_search_file(**kwargs)

        return {
            "success": False,
            "error": f"Unknown tool: {tool}",
            "output": f"未知的核心工具: {tool}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "output": traceback.format_exc(),
        }
