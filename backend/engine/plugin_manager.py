"""内置插件管理器

职责：
1. 启动时把 backend/plugins/ 下的内容同步到 ~/.Aries/plugins/
2. 读写 ~/.Aries/plugins/config.json 开关配置
3. 提供发现、加载、开关 API

目录结构：
    ~/.Aries/plugins/
      config.json          # 开关配置
      skills/              # 从 backend/plugins/skills/ 同步
      tools/               # 从 backend/plugins/tools/ 同步
      agents/               # 从 backend/plugins/agents/ 同步
      mcps/                # 从 backend/plugins/mcps/ 同步
"""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 源目录：随程序打包
_PLUGINS_SOURCE = Path(__file__).resolve().parent.parent / "plugins"

# 目标目录：用户数据
_PLUGINS_ROOT = Path.home() / ".Aries" / "plugins"
_CONFIG_PATH = _PLUGINS_ROOT / "config.json"

PLUGIN_KINDS = ("skills", "tools", "agents", "mcps")


class PluginKind(str, Enum):
    SKILL = "skills"
    TOOL = "tools"
    AGENT = "agents"
    MCP = "mcps"


@dataclass
class PluginEntry:
    """一个内置插件条目"""
    kind: str           # skills / tools / agents / mcps
    name: str           # 目录名或文件名（不带扩展名）
    display_name: str
    description: str
    enabled: bool
    source_path: str    # backend/plugins/ 下的源路径
    target_path: str    # ~/.Aries/plugins/ 下的目标路径

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "enabled": self.enabled,
            "source_path": self.source_path,
            "target_path": self.target_path,
        }


# ---------- 配置读写 ----------

def _default_config() -> dict[str, dict[str, bool]]:
    return {kind: {} for kind in PLUGIN_KINDS}


def load_config() -> dict[str, dict[str, bool]]:
    """读取插件开关配置。"""
    if not _CONFIG_PATH.exists():
        return _default_config()
    try:
        raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return _default_config()
        result = _default_config()
        for kind in PLUGIN_KINDS:
            section = raw.get(kind, {})
            if isinstance(section, dict):
                result[kind] = {
                    str(k): bool(v) for k, v in section.items()
                }
        return result
    except Exception as exc:
        logger.warning("读取 plugins/config.json 失败: %s", exc)
        return _default_config()


def save_config(config: dict[str, dict[str, bool]]) -> None:
    """保存插件开关配置。"""
    _PLUGINS_ROOT.mkdir(parents=True, exist_ok=True)
    data = {kind: dict(config.get(kind, {})) for kind in PLUGIN_KINDS}
    _CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def is_plugin_enabled(kind: str, name: str) -> bool:
    """检查某个插件是否开启。未在配置中记录的默认 True。"""
    config = load_config()
    section = config.get(kind, {})
    if name not in section:
        return True
    return section[name]


def set_plugin_enabled(kind: str, name: str, enabled: bool) -> None:
    """设置某个插件开关。"""
    config = load_config()
    config.setdefault(kind, {})[name] = enabled
    save_config(config)


# ---------- 同步逻辑 ----------

def _sync_file(src: Path, dst: Path) -> bool:
    """同步单个文件，返回是否有更新。"""
    if not src.exists():
        return False
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _sync_dir(src: Path, dst: Path) -> bool:
    """同步目录（递归），返回是否有更新。"""
    if not src.exists() or not src.is_dir():
        return False
    updated = False
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if _sync_file(item, target):
            updated = True
    return updated


def sync_plugins() -> dict[str, int]:
    """启动时调用：把 backend/plugins/ 同步到 ~/.Aries/plugins/。

    返回各类型同步的文件数。
    """
    _PLUGINS_ROOT.mkdir(parents=True, exist_ok=True)
    counts = {kind: 0 for kind in PLUGIN_KINDS}

    for kind in PLUGIN_KINDS:
        src_dir = _PLUGINS_SOURCE / kind
        dst_dir = _PLUGINS_ROOT / kind
        if not src_dir.exists():
            continue

        if kind == "tools":
            # tools/ 下是单个 JSON 文件
            for src_file in src_dir.glob("*.json"):
                dst_file = dst_dir / src_file.name
                if _sync_file(src_file, dst_file):
                    counts[kind] += 1
        else:
            # skills/agents/mcps/ 下是子目录
            for src_sub in src_dir.iterdir():
                if not src_sub.is_dir() or src_sub.name.startswith("__"):
                    continue
                dst_sub = dst_dir / src_sub.name
                if _sync_dir(src_sub, dst_sub):
                    counts[kind] += 1

    # 确保 config.json 存在
    if not _CONFIG_PATH.exists():
        save_config(_default_config())

    if any(counts.values()):
        logger.info("Plugins synced: %s", counts)
    return counts


# ---------- 发现 ----------

def _parse_skill_md(skill_md_path: Path, default_name: str) -> dict[str, str]:
    """解析 SKILL.md 的 frontmatter。"""
    content = skill_md_path.read_text(encoding="utf-8")
    name = default_name
    description = ""

    if content.startswith("---"):
        import re
        end = re.search(r"\n---\s*\n", content[3:])
        if end:
            yaml_block = content[3:end.start() + 3]
            for line in yaml_block.splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if key == "name":
                        name = val
                    elif key == "description":
                        description = val
    return {"name": name, "description": description}


def _parse_tool_json(json_path: Path) -> dict[str, str]:
    """解析工具 JSON 定义。"""
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        func = data.get("function", {})
        return {
            "name": func.get("name", json_path.stem),
            "description": func.get("description", "")[:200],
        }
    except Exception:
        return {"name": json_path.stem, "description": ""}


def _parse_agent_json(json_path: Path) -> dict[str, str]:
    """解析子 Agent 配置。"""
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return {
            "name": data.get("name", json_path.stem),
            "description": data.get("description", "")[:200],
        }
    except Exception:
        return {"name": json_path.stem, "description": ""}


def _parse_mcp_json(json_path: Path) -> dict[str, str]:
    """解析内置 MCP 配置。"""
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return {
            "name": data.get("name", json_path.stem),
            "description": data.get("description", "")[:200],
        }
    except Exception:
        return {"name": json_path.stem, "description": ""}


def discover_plugins() -> list[PluginEntry]:
    """发现所有内置插件。"""
    entries: list[PluginEntry] = []
    config = load_config()

    for kind in PLUGIN_KINDS:
        dst_dir = _PLUGINS_ROOT / kind
        if not dst_dir.exists():
            continue

        if kind == "tools":
            for json_file in sorted(dst_dir.glob("*.json")):
                parsed = _parse_tool_json(json_file)
                name = parsed["name"]
                entries.append(PluginEntry(
                    kind=kind,
                    name=name,
                    display_name=name,
                    description=parsed["description"],
                    enabled=is_plugin_enabled(kind, name),
                    source_path=str(_PLUGINS_SOURCE / kind / json_file.name),
                    target_path=str(json_file),
                ))
        else:
            for sub in sorted(dst_dir.iterdir()):
                if not sub.is_dir() or sub.name.startswith("__"):
                    continue
                name = sub.name
                display_name = name
                description = ""

                if kind == "skills":
                    skill_md = sub / "SKILL.md"
                    if not skill_md.is_file():
                        skill_md = sub / "skill.md"
                    if skill_md.is_file():
                        parsed = _parse_skill_md(skill_md, name)
                        display_name = parsed["name"]
                        description = parsed["description"]
                elif kind == "agents":
                    for json_file in sub.glob("*.json"):
                        parsed = _parse_agent_json(json_file)
                        display_name = parsed["name"]
                        description = parsed["description"]
                        break
                elif kind == "mcps":
                    for json_file in sub.glob("*.json"):
                        parsed = _parse_mcp_json(json_file)
                        display_name = parsed["name"]
                        description = parsed["description"]
                        break

                entries.append(PluginEntry(
                    kind=kind,
                    name=name,
                    display_name=display_name,
                    description=description,
                    enabled=is_plugin_enabled(kind, name),
                    source_path=str(_PLUGINS_SOURCE / kind / name),
                    target_path=str(sub),
                ))

    return entries


def get_enabled_plugins() -> list[PluginEntry]:
    """返回所有已开启的插件。"""
    return [e for e in discover_plugins() if e.enabled]


# ---------- 加载 ----------

def get_plugin_tool_definitions() -> list[dict[str, Any]]:
    """加载所有已开启的 tools 类型插件定义。"""
    tools: list[dict[str, Any]] = []
    for entry in get_enabled_plugins():
        if entry.kind != "tools":
            continue
        try:
            data = json.loads(Path(entry.target_path).read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("type") == "function":
                tools.append(data)
        except Exception as exc:
            logger.warning("加载插件工具 %s 失败: %s", entry.name, exc)
    return tools


def get_plugin_skill_dirs() -> list[Path]:
    """返回所有已开启的 skills 类型插件目录。"""
    return [
        Path(e.target_path)
        for e in get_enabled_plugins()
        if e.kind == "skills"
    ]


def get_plugin_agent_configs() -> list[dict[str, Any]]:
    """返回所有已开启的 agents 类型插件配置。"""
    configs: list[dict[str, Any]] = []
    for entry in get_enabled_plugins():
        if entry.kind != "agents":
            continue
        agent_dir = Path(entry.target_path)
        for json_file in agent_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data["_source"] = "plugin"
                    configs.append(data)
            except Exception as exc:
                logger.warning("加载插件 Agent %s 失败: %s", entry.name, exc)
    return configs


def get_plugin_mcp_configs() -> list[dict[str, Any]]:
    """返回所有已开启的 mcps 类型插件配置。"""
    configs: list[dict[str, Any]] = []
    for entry in get_enabled_plugins():
        if entry.kind != "mcps":
            continue
        mcp_dir = Path(entry.target_path)
        for json_file in mcp_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data["_source"] = "plugin"
                    configs.append(data)
            except Exception as exc:
                logger.warning("加载插件 MCP %s 失败: %s", entry.name, exc)
    return configs


# ---------- 上下文 ----------

def build_plugins_context() -> str:
    """构建给 system prompt 的简短插件列表（不展开详情，避免污染上下文）。"""
    entries = get_enabled_plugins()
    if not entries:
        return ""

    by_kind: dict[str, list[PluginEntry]] = {}
    for e in entries:
        by_kind.setdefault(e.kind, []).append(e)

    lines = ["【内置插件（始终可用）】"]

    kind_labels = {
        "skills": "技能",
        "tools": "工具",
        "agents": "子 Agent",
        "mcps": "MCP 服务",
    }

    for kind in PLUGIN_KINDS:
        items = by_kind.get(kind)
        if not items:
            continue
        label = kind_labels.get(kind, kind)
        names = [e.display_name for e in items]
        lines.append(f"- {label}: {', '.join(names)}")

    lines.append("如需了解某个插件的具体用法，可调用 read_file 读取其定义文件。")
    return "\n".join(lines)


# ---------- 插件技能加载与执行 ----------

def _load_plugin_skill_module(skill_dir: Path):
    """用 importlib 从目录路径加载插件技能模块。"""
    import importlib.util

    init_path = skill_dir / "__init__.py"
    if not init_path.is_file():
        return None

    module_name = f"_plugin_skill_{skill_dir.name}"
    spec = importlib.util.spec_from_file_location(module_name, init_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_plugin_skill_tool_definitions() -> list[dict[str, Any]]:
    """加载所有已开启的 skills 类型插件的工具定义。"""
    tools: list[dict[str, Any]] = []
    for skill_dir in get_plugin_skill_dirs():
        try:
            module = _load_plugin_skill_module(skill_dir)
            if module is None:
                continue
            if hasattr(module, "get_tool_definitions"):
                defs = module.get_tool_definitions()
                if isinstance(defs, list):
                    tools.extend(defs)
                elif isinstance(defs, dict):
                    tools.append(defs)
            elif hasattr(module, "get_tool_definition"):
                defn = module.get_tool_definition()
                if defn:
                    tools.append(defn)
        except Exception as exc:
            logger.warning("加载插件技能 %s 工具定义失败: %s", skill_dir.name, exc)
    return tools


def execute_plugin_skill_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """在插件技能中查找并执行指定工具。未找到返回 None。"""
    for skill_dir in get_plugin_skill_dirs():
        try:
            module = _load_plugin_skill_module(skill_dir)
            if module is None:
                continue

            has_tool = False
            if hasattr(module, "get_tool_definitions"):
                defs = module.get_tool_definitions()
                if isinstance(defs, list):
                    for d in defs:
                        if d.get("function", {}).get("name") == tool_name:
                            has_tool = True
                            break
                elif isinstance(defs, dict) and defs.get("function", {}).get("name") == tool_name:
                    has_tool = True
            if not has_tool and hasattr(module, "get_tool_definition"):
                defn = module.get_tool_definition()
                if defn and defn.get("function", {}).get("name") == tool_name:
                    has_tool = True

            if has_tool and hasattr(module, "execute"):
                if hasattr(module, "get_tool_definitions"):
                    arguments["tool"] = tool_name
                return module.execute(**arguments)
        except Exception as exc:
            logger.warning("执行插件技能工具 %s 失败: %s", tool_name, exc)
            continue
    return None


def execute_plugin_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """执行纯 JSON 工具（tools 类型插件）。未找到返回 None。"""
    for entry in get_enabled_plugins():
        if entry.kind != "tools":
            continue
        try:
            data = json.loads(Path(entry.target_path).read_text(encoding="utf-8"))
            func = data.get("function", {})
            if func.get("name") != tool_name:
                continue
            executor_name = func.get("name", "")
            # 查找对应的执行器：同目录下 {name}_executor.py
            executor_path = Path(entry.target_path).parent / f"{executor_name}_executor.py"
            if executor_path.is_file():
                import importlib.util
                spec = importlib.util.spec_from_file_location(f"_plugin_tool_{executor_name}", executor_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    if hasattr(module, "execute"):
                        return module.execute(**arguments)
            return {"success": False, "error": f"插件工具 {tool_name} 缺少执行器", "output": ""}
        except Exception as exc:
            logger.warning("执行插件工具 %s 失败: %s", tool_name, exc)
            continue
    return None
