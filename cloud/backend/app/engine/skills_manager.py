"""Skills Manager - 技能包发现与用户启用配置。

目录结构：
- 官方：~/.Aries/skills/<name>/SKILL.md + icon + scripts/samples/resources
- 私有：~/.Aries/{email}/skills/<name>/...
- 启用清单（仅约束主 Agent）：~/.Aries/{email}/skills_config.yaml
    main_enabled: [theme-factory, ...]
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

SHARED_SKILLS_ROOT = Path.home() / ".Aries" / "skills"
_NAME_UNSAFE_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_config_lock = threading.Lock()
_ICON_CANDIDATES = (
    "icon.png",
    "icon.jpg",
    "icon.jpeg",
    "icon.svg",
    "icon.webp",
    "avatar.png",
)
_MD_CANDIDATES = ("SKILL.md", "skill.md", "README.md")
_OPTIONAL_DIRS = ("scripts", "samples", "resources", "icons")
_MAX_AVATAR_INLINE = 120_000
_MAX_NAME_LEN = 64


def _safe_name(name: str) -> str:
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


@dataclass
class SkillEntry:
    name: str
    description: str
    folder_name: str
    skill_path: Path
    skill_md_path: Path
    content: str = ""
    body: str = ""
    frontmatter: dict[str, Any] = field(default_factory=dict)
    icon_path: Path | None = None
    scope: str = "shared"  # shared | private
    main_enabled: bool = True
    enabled: bool = True
    tree: list[str] = field(default_factory=list)

    def to_api_dict(self, *, include_content: bool = False) -> dict[str, Any]:
        data = {
            "name": self.name,
            "description": self.description,
            "folder_name": self.folder_name,
            "path": str(self.skill_path),
            "skill_md_path": str(self.skill_md_path),
            "scope": self.scope,
            "main_enabled": self.main_enabled,
            "enabled": self.enabled,
            "has_avatar": bool(self.icon_path and self.icon_path.exists()),
            "avatar_url": f"/api/skills/{self.folder_name}/icon" if self.icon_path else "",
            "avatar_data": _icon_data_uri(self.icon_path),
            "tree": list(self.tree),
        }
        if include_content:
            data["content"] = self.content
            data["body"] = self.body
            data["frontmatter"] = dict(self.frontmatter)
        return data


def user_skills_root(email: str | None = None) -> Path:
    email = (email or "").strip()
    if email:
        return Path.home() / ".Aries" / email / "skills"
    return SHARED_SKILLS_ROOT


def user_skills_config_path(email: str) -> Path:
    base = Path.home() / ".Aries" / email
    yaml_path = base / "skills_config.yaml"
    if yaml_path.exists():
        return yaml_path
    json_path = base / "skills_config.json"
    if json_path.exists():
        return json_path
    return yaml_path


def ensure_skills_dir(email: str | None = None) -> Path:
    root = user_skills_root(email)
    root.mkdir(parents=True, exist_ok=True)
    return root


def skill_roots_for_user(email: str | None = None) -> list[Path]:
    roots = []
    email = (email or "").strip()
    if email:
        roots.append(user_skills_root(email))
    roots.append(SHARED_SKILLS_ROOT)
    return roots


def _find_icon(folder: Path) -> Path | None:
    for name in _ICON_CANDIDATES:
        p = folder / name
        if p.is_file():
            return p
    icons_dir = folder / "icons"
    if icons_dir.is_dir():
        for p in sorted(icons_dir.iterdir()):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".svg", ".webp") and p.is_file():
                return p
    for p in sorted(folder.glob("icon.*")):
        if p.is_file():
            return p
    return None


def _find_skill_md(folder: Path) -> Path | None:
    for name in _MD_CANDIDATES:
        p = folder / name
        if p.is_file():
            return p
    mds = sorted(folder.glob("*.md"))
    return mds[0] if mds else None


def _list_tree(folder: Path, max_entries: int = 80) -> list[str]:
    items: list[str] = []
    try:
        for p in sorted(folder.rglob("*")):
            if p.is_dir():
                continue
            if any(part.startswith(".") for part in p.parts):
                continue
            rel = p.relative_to(folder).as_posix()
            items.append(rel)
            if len(items) >= max_entries:
                items.append("...")
                break
    except Exception:
        pass
    return items


def _read_skill_folder(folder: Path, *, scope: str) -> SkillEntry | None:
    md_path = _find_skill_md(folder)
    if not md_path:
        return None
    try:
        content = md_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(content)
        name = str(fm.get("name") or folder.name).strip() or folder.name
        description = str(fm.get("description") or "").strip()
        if not description:
            for line in body.splitlines():
                if line.startswith("# "):
                    description = line[2:].strip()
                    break
        return SkillEntry(
            name=name,
            description=description,
            folder_name=folder.name,
            skill_path=folder,
            skill_md_path=md_path,
            content=content,
            body=body,
            frontmatter=fm if isinstance(fm, dict) else {},
            icon_path=_find_icon(folder),
            scope=scope,
            enabled=bool(fm.get("enabled", True)) if isinstance(fm, dict) else True,
            tree=_list_tree(folder),
        )
    except Exception as e:
        logger.warning("解析 skill 失败 %s: %s", folder, e)
        return None


def load_skills_config(email: str) -> dict[str, Any]:
    email = (email or "").strip()
    if not email:
        return {"main_enabled": None}
    path = user_skills_config_path(email)
    if not path.exists():
        return {"main_enabled": None}
    data = load_config_file(path)
    enabled = data.get("main_enabled", None)
    if enabled is not None:
        if not isinstance(enabled, list):
            enabled = []
        enabled = [str(x).strip() for x in enabled if str(x).strip()]
    return {"main_enabled": enabled}


def save_skills_config(email: str, *, main_enabled: list[str] | None) -> dict[str, Any]:
    email = (email or "").strip()
    if not email:
        raise ValueError("缺少用户邮箱")
    path = Path.home() / ".Aries" / email / "skills_config.yaml"
    payload = {"main_enabled": list(main_enabled) if main_enabled is not None else None}
    with _config_lock:
        save_config_file(path, payload)
        old = path.with_suffix(".json")
        if old.exists():
            try:
                old.unlink()
            except Exception:
                pass
    return payload


def ensure_skills_config(email: str) -> dict[str, Any]:
    email = (email or "").strip()
    if not email:
        return {"main_enabled": None}
    path = user_skills_config_path(email)
    if path.exists():
        return load_skills_config(email)
    names = [e.folder_name for e in discover_skills(email, apply_main_filter=False) if e.enabled]
    return save_skills_config(email, main_enabled=names)


def discover_skills(
    email: str | None = None,
    *,
    apply_main_filter: bool = False,
) -> list[SkillEntry]:
    ensure_skills_dir(None)
    if email:
        ensure_skills_dir(email)

    entries: list[SkillEntry] = []
    seen: set[str] = set()

    def _load(root: Path, scope: str) -> None:
        if not root.is_dir():
            return
        for folder in sorted(root.iterdir()):
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            key = folder.name
            if key in seen:
                continue
            entry = _read_skill_folder(folder, scope=scope)
            if entry is None:
                continue
            entries.append(entry)
            seen.add(key)

    if email:
        _load(user_skills_root(email), "private")
    _load(SHARED_SKILLS_ROOT, "shared")

    main_enabled = None
    if email:
        cfg = load_skills_config(email)
        main_enabled = cfg.get("main_enabled")

    for entry in entries:
        if main_enabled is None:
            entry.main_enabled = True
        else:
            entry.main_enabled = entry.folder_name in main_enabled or entry.name in main_enabled

    if apply_main_filter:
        return [e for e in entries if e.main_enabled and e.enabled]
    return entries


def get_skill_by_name(name: str, email: str | None = None) -> SkillEntry | None:
    name = (name or "").strip()
    for entry in discover_skills(email, apply_main_filter=False):
        if entry.folder_name == name or entry.name == name:
            return entry
    return None


def list_main_skills(email: str | None = None) -> list[SkillEntry]:
    """主 Agent 可用技能（受 skills_config 约束）。"""
    return discover_skills(email, apply_main_filter=True)


def resolve_skills_for_agent(email: str | None, allowed_names: list[str] | None) -> list[SkillEntry]:
    """子 Agent：按 allowed_skills 解析，忽略主 Agent 启用名单。"""
    if not allowed_names:
        return []
    wanted = {str(n).strip() for n in allowed_names if str(n).strip()}
    result = []
    for entry in discover_skills(email, apply_main_filter=False):
        if entry.folder_name in wanted or entry.name in wanted:
            result.append(entry)
    return result


def build_skills_prompt_section(
    email: str | None = None,
    *,
    for_main: bool = True,
    allowed_names: list[str] | None = None,
    filter_names: list[str] | None = None,
) -> str:
    if for_main:
        entries = list_main_skills(email)
    else:
        entries = resolve_skills_for_agent(email, allowed_names)

    if filter_names is not None:
        wanted = {str(n).strip() for n in filter_names if str(n).strip()}
        entries = [e for e in entries if e.folder_name in wanted or e.name in wanted]

    if not entries:
        return ""

    lines = [
        "# Available Skills（可用技能包）",
        "下列技能包位于本机文件系统。你可以用 read_file / list_files / run_shell 读取文档并运行其中的脚本。",
        "路径可使用绝对路径（已对 skills 目录开放只读/执行）。",
        "",
    ]
    for e in entries:
        scope = "私有" if e.scope == "private" else "官方"
        lines.append(f"- {e.name} ({e.folder_name}) [{scope}]")
        lines.append(f"  描述: {e.description or '(无描述)'}")
        lines.append(f"  目录: {e.skill_path}")
        lines.append(f"  说明文档: {e.skill_md_path}")
        for sub in ("scripts", "samples", "resources"):
            p = e.skill_path / sub
            if p.is_dir():
                lines.append(f"  {sub}/: {p}")
        lines.append("")
    return "\n".join(lines).rstrip()


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
    for p in folder.glob("icon.*"):
        try:
            p.unlink()
        except Exception:
            pass
    path = folder / "icon.png"
    path.write_bytes(data)
    return path


def save_skill(email: str, payload: dict[str, Any]) -> SkillEntry:
    email = (email or "").strip()
    if not email:
        raise ValueError("缺少用户邮箱")
    name = _safe_name(str(payload.get("name") or payload.get("folder_name") or "").strip())
    if not name:
        raise ValueError("name 不能为空")

    root = ensure_skills_dir(email)
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    for d in _OPTIONAL_DIRS:
        (folder / d).mkdir(exist_ok=True)

    md_path = folder / "SKILL.md"
    frontmatter: dict[str, Any] = {
        "name": name,
        "description": str(payload.get("description") or "").strip(),
        "enabled": bool(payload.get("enabled", True)),
    }
    body = str(payload.get("body") or payload.get("content") or payload.get("system_prompt") or "").strip()
    write_frontmatter_md(md_path, frontmatter, body)

    avatar = payload.get("avatar") or payload.get("avatar_base64") or ""
    if avatar:
        _save_avatar(folder, str(avatar))

    cfg = ensure_skills_config(email)
    enabled = cfg.get("main_enabled")
    if isinstance(enabled, list) and name not in enabled:
        save_skills_config(email, main_enabled=list(enabled) + [name])

    entry = _read_skill_folder(folder, scope="private")
    if entry is None:
        raise ValueError("保存后无法读取技能")
    entry.main_enabled = True
    return entry


def extract_skill_zip(zip_bytes: bytes, email: str) -> tuple[Path, str]:
    """解压 zip 到临时目录，返回 (临时目录路径, 技能名)。

    zip 包结构要求：根目录或单层子目录下包含 SKILL.md。
    """
    import tempfile
    import zipfile
    import io

    tmpdir = Path(tempfile.mkdtemp(prefix="skill_upload_"))
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            # 安全检查：禁止路径穿越
            for member in zf.namelist():
                member_path = Path(member)
                if member_path.is_absolute() or ".." in member_path.parts:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                    raise ValueError(f"压缩包包含不安全路径: {member}")
            zf.extractall(tmpdir)
    except zipfile.BadZipFile:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise ValueError("无效的 zip 文件")

    # 查找 SKILL.md：先看根目录，再看单层子目录
    skill_dir = None
    for candidate in ("SKILL.md", "skill.md", "README.md"):
        if (tmpdir / candidate).is_file():
            skill_dir = tmpdir
            break
    if skill_dir is None:
        # 检查单层子目录
        for child in sorted(tmpdir.iterdir()):
            if child.is_dir():
                for candidate in ("SKILL.md", "skill.md", "README.md"):
                    if (child / candidate).is_file():
                        skill_dir = child
                        break
                if skill_dir:
                    break

    if skill_dir is None:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise ValueError("压缩包中未找到 SKILL.md 文件")

    # 从 frontmatter 提取技能名
    md_path = None
    for candidate in ("SKILL.md", "skill.md", "README.md"):
        p = skill_dir / candidate
        if p.is_file():
            md_path = p
            break
    name = ""
    if md_path:
        content = md_path.read_text(encoding="utf-8", errors="replace")
        fm, _ = parse_frontmatter(content)
        name = str(fm.get("name") or "").strip()
    if not name:
        name = skill_dir.name

    return skill_dir, name


def save_skill_from_dir(email: str, src_dir: Path, name: str) -> SkillEntry:
    """将已解压的技能目录保存到用户私有技能目录。"""
    email = (email or "").strip()
    if not email:
        raise ValueError("缺少用户邮箱")
    name = _safe_name(name)
    if not name:
        raise ValueError("name 不能为空")

    root = ensure_skills_dir(email)
    folder = root / name

    # 如果已存在则覆盖
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)

    # 复制所有文件（保留目录结构）
    for item in src_dir.rglob("*"):
        if item.is_file():
            rel = item.relative_to(src_dir)
            dest = folder / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)

    # 更新启用清单
    cfg = ensure_skills_config(email)
    enabled = cfg.get("main_enabled")
    if isinstance(enabled, list) and name not in enabled:
        save_skills_config(email, main_enabled=list(enabled) + [name])

    entry = _read_skill_folder(folder, scope="private")
    if entry is None:
        raise ValueError("保存后无法读取技能")
    entry.main_enabled = True
    return entry


def cleanup_temp_dir(tmp_dir: Path) -> None:
    """清理临时目录。"""
    shutil.rmtree(tmp_dir, ignore_errors=True)


def delete_skill(email: str, name: str) -> bool:

    email = (email or "").strip()
    name = _safe_name(str(name or "").strip())
    folder = user_skills_root(email) / name
    if not folder.is_dir():
        return False
    shutil.rmtree(folder, ignore_errors=True)
    cfg = load_skills_config(email)
    enabled = cfg.get("main_enabled")
    if isinstance(enabled, list) and name in enabled:
        save_skills_config(email, main_enabled=[x for x in enabled if x != name])
    return True


def set_main_enabled(email: str, name: str, enabled: bool) -> SkillEntry:
    entry = get_skill_by_name(name, email)
    if entry is None:
        raise ValueError(f"技能不存在：{name}")

    cfg = ensure_skills_config(email)
    current = cfg.get("main_enabled")
    if current is None:
        current = [e.folder_name for e in discover_skills(email, apply_main_filter=False) if e.enabled]

    names = set(current)
    key = entry.folder_name
    if enabled:
        names.add(key)
    else:
        names.discard(key)
        names.discard(entry.name)
    save_skills_config(email, main_enabled=sorted(names))
    entry.main_enabled = enabled
    return entry
