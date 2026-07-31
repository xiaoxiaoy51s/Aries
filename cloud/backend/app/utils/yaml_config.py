"""YAML 配置读写（兼容旧 JSON）。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _load_yaml(text: str) -> Any:
    import yaml

    return yaml.safe_load(text)


def _dump_yaml(data: Any) -> str:
    import yaml

    return yaml.safe_dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )


def load_config_file(path: Path) -> dict[str, Any]:
    """读取 yaml/json 配置，失败返回 {}。"""
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("读取配置失败 %s: %s", path, e)
        return {}
    try:
        if path.suffix.lower() in (".yaml", ".yml"):
            data = _load_yaml(text)
        else:
            data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("解析配置失败 %s: %s", path, e)
        return {}


def save_config_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_yaml(data), encoding="utf-8")


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """解析 Markdown YAML frontmatter。"""
    text = content.lstrip("\ufeff")
    if not text.startswith("---"):
        return {}, text.strip()
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text.strip()
    fm_raw = text[3:end].strip()
    body = text[end + 4:].strip()
    try:
        fm = _load_yaml(fm_raw) or {}
        if not isinstance(fm, dict):
            fm = {}
    except Exception:
        fm = {}
    return fm, body


def write_frontmatter_md(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_text = _dump_yaml(frontmatter).rstrip()
    parts = ["---", fm_text, "---"]
    if body:
        parts.append("")
        parts.append(body.rstrip())
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
