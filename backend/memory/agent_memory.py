"""work_dir 级别的 Agent 记忆。

用于保存 AI 对当前工作目录代码结构、命令、约定的总结，避免把 AGENTS.md 写入项目根目录。
同时支持用户自定义的 rules.md 约束文件（AI 只读，用户可编辑）。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

MAX_AGENT_MEMORY_CHARS = 16_000
MAX_ROLE_RULES_CHARS = 8_000


def _normalize_work_dir(work_dir: str | None) -> str:
    if work_dir and work_dir.strip():
        return str(Path(work_dir).expanduser().resolve())
    return str((Path.home() / ".Aries" / "work_dir").resolve())


def _safe_work_dir_name(work_dir: str) -> str:
    digest = hashlib.sha1(work_dir.encode("utf-8", errors="ignore")).hexdigest()[:10]
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", work_dir.replace(":", ""))
    name = name.strip("._-") or "work_dir"
    if len(name) > 80:
        name = name[-80:]
    return f"{name}_{digest}"


def get_agent_memory_path(work_dir: str | None) -> Path:
    normalized = _normalize_work_dir(work_dir)
    return Path.home() / ".Aries" / "memory" / _safe_work_dir_name(normalized) / "agent.md"


def get_role_rules_path(work_dir: str | None) -> Path:
    """用户自定义约束文件路径（AI 只读）"""
    normalized = _normalize_work_dir(work_dir)
    return Path.home() / ".Aries" / "memory" / _safe_work_dir_name(normalized) / "rules.md"


def read_role_rules(work_dir: str | None) -> str:
    """读取用户自定义约束（AI 只读）"""
    path = get_role_rules_path(work_dir)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:MAX_ROLE_RULES_CHARS]


def write_role_rules(work_dir: str | None, content: str) -> dict[str, str | bool]:
    """保存用户自定义约束（仅用户调用）"""
    text = (content or "").strip()
    if not text:
        return {"success": False, "error": "rules 内容为空", "output": "rules 内容为空"}

    path = get_role_rules_path(work_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    return {
        "success": True,
        "error": "",
        "output": f"已保存用户约束：{path}",
        "file_path": str(path),
    }


def read_agent_memory(work_dir: str | None) -> str:
    path = get_agent_memory_path(work_dir)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:MAX_AGENT_MEMORY_CHARS]


def write_agent_memory(work_dir: str | None, content: str) -> dict[str, str | bool]:
    text = (content or "").strip()
    if not text:
        return {"success": False, "error": "agent memory 内容为空", "output": "agent memory 内容为空"}

    path = get_agent_memory_path(work_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    return {
        "success": True,
        "error": "",
        "output": f"已写入 work_dir 记忆：{path}",
        "file_path": str(path),
    }


def build_agent_memory_system_section(work_dir: str | None) -> str:
    sections: list[str] = []

    # 用户自定义约束（rules.md）— 优先级最高，放在最前面
    rules = read_role_rules(work_dir).strip()
    if rules:
        rules_path = get_role_rules_path(work_dir)
        sections.append(
            "# 用户自定义约束（Role Rules）\n"
            f"来源：`{rules_path}`\n"
            "以下是用户为你设定的行为约束，你必须严格遵守。\n\n"
            f"{rules}\n"
        )

    # AI 生成的项目记忆（agent.md）
    memory = read_agent_memory(work_dir).strip()
    if memory:
        path = get_agent_memory_path(work_dir)
        sections.append(
            "# 当前工作目录的 Agent 记忆\n"
            f"来源：`{path}`\n"
            "以下内容是你之前对当前 work_dir 的结构、命令和约定总结；可能过时，涉及代码状态时必须以实际文件为准。\n\n"
            f"{memory}\n"
        )

    if not sections:
        return ""
    return "\n" + "\n".join(sections)
