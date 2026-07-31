"""Subagent Manager - 子 Agent 配置加载（cloud 多租户）。

目录结构：
- 公共：~/.Aries/agent/<name>/AGENT.md + icon.*
- 私有：~/.Aries/{email}/agent/<name>/AGENT.md + icon.*
- 启用清单：~/.Aries/{email}/agents_config.yaml
    main_enabled: [code-reviewer, ...]
"""

from __future__ import annotations

import base64
import logging
import re
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.utils.yaml_config import (
    load_config_file,
    parse_frontmatter,
    save_config_file,
    write_frontmatter_md,
)

logger = logging.getLogger(__name__)

SHARED_AGENT_ROOT = Path.home() / ".Aries" / "agent"
_NAME_UNSAFE_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_config_lock = threading.Lock()
_ICON_CANDIDATES = (
    "icon.png",
    "icon.jpg",
    "icon.jpeg",
    "icon.svg",
    "icon.webp",
    "avatar.png",
    "avatar.jpg",
)
_MD_CANDIDATES = ("AGENT.md", "agent.md", "README.md")
_MAX_AVATAR_INLINE = 120_000
_MAX_NAME_LEN = 64


def _safe_filename(name: str) -> str:
    """允许中文等 Unicode 名称；禁止路径分隔符与 Windows 非法字符。"""
    name = (name or "").strip()
    if not name:
        raise ValueError("名称不能为空")
    if len(name) > _MAX_NAME_LEN:
        raise ValueError(f"名称过长（上限 {_MAX_NAME_LEN} 字符）")
    if name in (".", "..") or name.startswith(".") or name.endswith("."):
        raise ValueError("名称不能以点开头或结尾")
    if _NAME_UNSAFE_PATTERN.search(name):
        raise ValueError('名称不能包含 \\ / : * ? " < > | 等特殊字符')
    return name


def _icon_data_uri(path: Path | None) -> str:
    if not path or not path.is_file():
        return ""
    try:
        data = path.read_bytes()
        if len(data) > _MAX_AVATAR_INLINE:
            return ""
        suffix = path.suffix.lower().lstrip(".") or "png"
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "svg": "image/svg+xml",
            "webp": "image/webp",
        }.get(suffix, "image/png")
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    except Exception:
        return ""

_SUBAGENT_USAGE_RULES = (
    "\n"
    "# Subagent 使用规范\n"
    "下方「Available Subagents」列出了系统中可委派的子 Agent。"
    "每个 Subagent 拥有独立上下文与能力组合，适合复杂、多步任务。\n"
    "\n"
    "# Subagent 调用约束\n"
    "- 通过 `delegate_to_subagent` 工具委派任务。委派时 task 必须详尽，子 Agent 看不到当前对话历史。\n"
    "- 子 Agent 一次性返回最终结果（result 或 error），不能交互式追问；"
    "它会通过自己的 `report_to_main` 工具提交结论。\n"
    "- 何时委派：复杂多步任务、需要保护主上下文不被淹没、独立可并行的子查询。\n"
    "- 何时不要委派：简单任务、答案已知、必须串行依赖前序结果、能用一两个工具直接搞定。\n"
    "- 同一轮 tool_calls 中可以并发委派多个不同 Subagent，它们会被真正并行执行；"
    "返回后用一段简洁文字向用户汇报整合结论。\n"
)


@dataclass
class SubagentEntry:
    name: str
    description: str
    enabled: bool = True
    allowed_skills: list[str] = field(default_factory=list)
    allowed_mcps: list[str] = field(default_factory=list)
    system_prompt: str = ""
    config_path: Path | None = None
    folder_path: Path | None = None
    icon_path: Path | None = None
    available: bool = True
    unavailable_reason: str = ""
    scope: str = "shared"  # shared | private
    main_enabled: bool = True

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "allowed_skills": list(self.allowed_skills),
            "allowed_mcps": list(self.allowed_mcps),
            "system_prompt": self.system_prompt,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "scope": self.scope,
            "main_enabled": self.main_enabled,
            "config_path": str(self.config_path) if self.config_path else "",
            "folder_path": str(self.folder_path) if self.folder_path else "",
            "has_avatar": bool(self.icon_path and self.icon_path.exists()),
            "avatar_url": f"/api/subagents/{self.name}/icon" if self.icon_path else "",
            "avatar_data": _icon_data_uri(self.icon_path),
        }

    def to_router_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "allowed_skills": list(self.allowed_skills),
            "allowed_mcps": list(self.allowed_mcps),
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "scope": self.scope,
            "main_enabled": self.main_enabled,
        }


def user_agent_root(email: str | None = None) -> Path:
    email = (email or "").strip()
    if email:
        return Path.home() / ".Aries" / email / "agent"
    return SHARED_AGENT_ROOT


def user_agents_config_path(email: str) -> Path:
    base = Path.home() / ".Aries" / email
    yaml_path = base / "agents_config.yaml"
    if yaml_path.exists():
        return yaml_path
    json_path = base / "agents_config.json"
    if json_path.exists():
        return json_path
    return yaml_path


def ensure_agent_dir(email: str | None = None) -> Path:
    root = user_agent_root(email)
    root.mkdir(parents=True, exist_ok=True)
    migrate_legacy_agent_files(root)
    return root


def _str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(s).strip() for s in value if str(s).strip()]
    if isinstance(value, str):
        return [s.strip() for s in value.replace("[", "").replace("]", "").split(",") if s.strip()]
    return []


def _find_icon(folder: Path) -> Path | None:
    for name in _ICON_CANDIDATES:
        p = folder / name
        if p.is_file():
            return p
    for p in sorted(folder.glob("icon.*")):
        if p.is_file():
            return p
    return None


def _find_agent_md(folder: Path) -> Path | None:
    for name in _MD_CANDIDATES:
        p = folder / name
        if p.is_file():
            return p
    mds = sorted(folder.glob("*.md"))
    return mds[0] if mds else None


def migrate_legacy_agent_files(root: Path) -> None:
    """把旧版根目录 *.md 迁到 <name>/AGENT.md。"""
    if not root.is_dir():
        return
    for md in sorted(root.glob("*.md")):
        if md.name.lower() in ("readme.md",):
            continue
        name = md.stem
        try:
            _safe_filename(name)
        except ValueError:
            continue
        folder = root / name
        if folder.exists():
            continue
        try:
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / "AGENT.md"
            shutil.move(str(md), str(target))
            logger.info("已迁移 agent: %s -> %s", md, target)
        except Exception as e:
            logger.warning("迁移 agent 失败 %s: %s", md, e)


def _from_frontmatter(
    fm: dict[str, Any],
    name: str,
    md_path: Path,
    body: str,
    *,
    scope: str,
    folder: Path,
) -> SubagentEntry:
    entry = SubagentEntry(
        name=name,
        description=str(fm.get("description") or "").strip(),
        enabled=bool(fm.get("enabled", True)),
        allowed_skills=_str_list(fm.get("allowed_skills")),
        allowed_mcps=_str_list(fm.get("allowed_mcps")),
        system_prompt=body,
        config_path=md_path,
        folder_path=folder,
        icon_path=_find_icon(folder),
        scope=scope,
    )
    entry.available = entry.enabled
    entry.unavailable_reason = "" if entry.enabled else "已被禁用"
    return entry


def _read_agent_folder(folder: Path, *, scope: str) -> SubagentEntry | None:
    name = folder.name
    md_path = _find_agent_md(folder)
    if not md_path:
        return None
    try:
        content = md_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(content)
        name = str(fm.get("name") or name).strip() or folder.name
        return _from_frontmatter(fm, name, md_path, body, scope=scope, folder=folder)
    except Exception as exc:
        logger.warning("解析 subagent 失败 %s: %s", folder, exc)
        return None


def _save_avatar(folder: Path, avatar_b64: str) -> Path | None:
    raw = (avatar_b64 or "").strip()
    if not raw:
        return None
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        data = base64.b64decode(raw)
    except Exception as e:
        raise ValueError(f"头像 base64 无效：{e}") from e
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("头像过大（上限 2MB）")
    # 清理旧 icon
    for p in folder.glob("icon.*"):
        try:
            p.unlink()
        except Exception:
            pass
    path = folder / "icon.png"
    path.write_bytes(data)
    return path


# ---- 用户级启用配置 ----

def load_agents_config(email: str) -> dict[str, Any]:
    """main_enabled=None 表示未配置（默认全开）。"""
    email = (email or "").strip()
    if not email:
        return {"main_enabled": None}
    path = user_agents_config_path(email)
    if not path.exists():
        return {"main_enabled": None}
    data = load_config_file(path)
    enabled = data.get("main_enabled", None)
    if enabled is not None:
        if not isinstance(enabled, list):
            enabled = []
        enabled = [str(x).strip() for x in enabled if str(x).strip()]
    return {"main_enabled": enabled}


def save_agents_config(email: str, *, main_enabled: list[str] | None) -> dict[str, Any]:
    email = (email or "").strip()
    if not email:
        raise ValueError("缺少用户邮箱")
    path = Path.home() / ".Aries" / email / "agents_config.yaml"
    payload = {
        "main_enabled": list(main_enabled) if main_enabled is not None else None,
    }
    with _config_lock:
        save_config_file(path, payload)
        # 清理旧 json
        old = path.with_suffix(".json")
        if old.exists():
            try:
                old.unlink()
            except Exception:
                pass
    return payload


def ensure_agents_config(email: str) -> dict[str, Any]:
    email = (email or "").strip()
    if not email:
        return {"main_enabled": None}
    path = user_agents_config_path(email)
    if path.exists():
        return load_agents_config(email)
    names = [e.name for e in discover_subagents(email, apply_main_filter=False) if e.available]
    return save_agents_config(email, main_enabled=names)


def discover_subagents(
    email: str | None = None,
    *,
    apply_main_filter: bool = False,
) -> list[SubagentEntry]:
    ensure_agent_dir(None)
    if email:
        ensure_agent_dir(email)

    entries: list[SubagentEntry] = []
    seen: set[str] = set()

    def _load_dir(root: Path, scope: str) -> None:
        if not root.is_dir():
            return
        migrate_legacy_agent_files(root)
        for folder in sorted(root.iterdir()):
            if not folder.is_dir():
                continue
            if folder.name.startswith("."):
                continue
            if folder.name in seen:
                continue
            entry = _read_agent_folder(folder, scope=scope)
            if entry is None:
                continue
            entries.append(entry)
            seen.add(entry.name)

    if email:
        _load_dir(user_agent_root(email), "private")
    _load_dir(SHARED_AGENT_ROOT, "shared")

    main_enabled = None
    if email:
        cfg = load_agents_config(email)
        main_enabled = cfg.get("main_enabled")

    for entry in entries:
        if main_enabled is None:
            entry.main_enabled = True
        else:
            entry.main_enabled = entry.name in main_enabled

    if apply_main_filter:
        return [e for e in entries if e.main_enabled]
    return entries


def get_subagent_by_name(name: str, email: str | None = None) -> SubagentEntry | None:
    for entry in discover_subagents(email, apply_main_filter=False):
        if entry.name == name:
            return entry
    return None


def list_available_subagents(email: str | None = None) -> list[SubagentEntry]:
    return [e for e in discover_subagents(email, apply_main_filter=True) if e.available]


def build_subagent_router_section(email: str | None = None) -> str:
    entries = list_available_subagents(email)
    if not entries:
        return ""
    lines = [
        "# Available Subagents（可委派的子 Agent）",
        "下列子 Agent 可由你委派任务。每个 Subagent 拥有独立上下文与能力组合。",
        "",
    ]
    for entry in entries:
        skills = ", ".join(entry.allowed_skills) if entry.allowed_skills else "-"
        scope = "私有" if entry.scope == "private" else "公共"
        lines.append(
            f"- {entry.name} | {entry.description or '(无描述)'} | 技能: [{skills}] | {scope}"
        )
    return _SUBAGENT_USAGE_RULES + "\n" + "\n".join(lines)


def build_subagent_runtime(name: str, email: str | None = None) -> dict[str, Any]:
    entry = get_subagent_by_name(name, email)
    if entry is None:
        raise ValueError(f"Subagent 不存在：{name}")
    skills_context = ""
    skill_entries: list[Any] = []
    try:
        from app.engine.skills_manager import build_skills_prompt_section, resolve_skills_for_agent

        skill_entries = resolve_skills_for_agent(email, entry.allowed_skills)
        skills_context = build_skills_prompt_section(
            email,
            for_main=False,
            allowed_names=entry.allowed_skills,
        )
    except Exception:
        pass
    return {
        "entry": entry,
        "system_prompt": entry.system_prompt,
        "skills_context": skills_context,
        "skill_entries": skill_entries,
        "mcp_servers": list(entry.allowed_mcps),
        "effective_model": "",
    }


def save_subagent(email: str, payload: dict[str, Any]) -> SubagentEntry:
    """新建或覆盖用户私有 subagent。"""
    email = (email or "").strip()
    if not email:
        raise ValueError("缺少用户邮箱")
    name = _safe_filename(str(payload.get("name") or "").strip())
    if not name:
        raise ValueError("name 不能为空")

    root = ensure_agent_dir(email)
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    md_path = folder / "AGENT.md"

    frontmatter: dict[str, Any] = {
        "name": name,
        "description": str(payload.get("description") or "").strip(),
        "enabled": bool(payload.get("enabled", True)),
    }
    skills = [str(s).strip() for s in (payload.get("allowed_skills") or []) if str(s).strip()]
    if skills:
        frontmatter["allowed_skills"] = skills
    mcps = [str(m).strip() for m in (payload.get("allowed_mcps") or []) if str(m).strip()]
    if mcps:
        frontmatter["allowed_mcps"] = mcps

    body = str(payload.get("system_prompt") or "").strip()
    write_frontmatter_md(md_path, frontmatter, body)

    avatar = payload.get("avatar") or payload.get("avatar_base64") or ""
    if avatar:
        _save_avatar(folder, str(avatar))

    cfg = ensure_agents_config(email)
    enabled = cfg.get("main_enabled")
    if isinstance(enabled, list) and name not in enabled:
        enabled = list(enabled) + [name]
        save_agents_config(email, main_enabled=enabled)

    entry = _from_frontmatter(frontmatter, name, md_path, body, scope="private", folder=folder)
    entry.main_enabled = True
    return entry


def delete_subagent(email: str, name: str) -> bool:
    email = (email or "").strip()
    name = _safe_filename(str(name or "").strip())
    folder = user_agent_root(email) / name
    if not folder.is_dir():
        # 兼容未迁移的旧文件
        legacy = user_agent_root(email) / f"{name}.md"
        if legacy.exists():
            legacy.unlink()
        else:
            return False
    else:
        shutil.rmtree(folder, ignore_errors=True)
    cfg = load_agents_config(email)
    enabled = cfg.get("main_enabled")
    if isinstance(enabled, list) and name in enabled:
        save_agents_config(email, main_enabled=[x for x in enabled if x != name])
    return True


def set_main_enabled(email: str, name: str, enabled: bool) -> SubagentEntry:
    entry = get_subagent_by_name(name, email)
    if entry is None:
        raise ValueError(f"Subagent 不存在：{name}")

    cfg = ensure_agents_config(email)
    current = cfg.get("main_enabled")
    if current is None:
        current = [e.name for e in discover_subagents(email, apply_main_filter=False) if e.available]

    names = set(current)
    if enabled:
        names.add(entry.name)
    else:
        names.discard(entry.name)
    save_agents_config(email, main_enabled=sorted(names))
    entry.main_enabled = enabled
    return entry
