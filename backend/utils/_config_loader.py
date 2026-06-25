"""共享配置加载工具：统一 skills / subagent 的目录发现与文件解析。"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def discover_json_configs(root: Path, suffix: str = ".json") -> list[Path]:
    """扫描目录下所有 JSON/YAML 配置文件。

    Args:
        root: 扫描根目录
        suffix: 文件后缀过滤（.json / .yaml）

    Returns:
        按文件名排序的配置文件路径列表
    """
    if not root.is_dir():
        return []
    return sorted(
        [p for p in root.iterdir() if p.is_file() and p.suffix == suffix],
        key=lambda p: p.name.lower(),
    )


def discover_subdir_configs(root: Path, config_filename: str = "SKILL.md") -> list[Path]:
    """扫描子目录下的配置文件。

    格式：每个子目录下有一个 config_filename 文件。
    Args:
        root: 扫描根目录（如 ~/.Aries/skills/available/）
        config_filename: 子目录内的配置文件名（如 SKILL.md）

    Returns:
        按目录名排序的配置路径列表
    """
    if not root.is_dir():
        return []
    paths: list[Path] = []
    for sub in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if sub.is_dir() and not sub.name.startswith("__"):
            config = sub / config_filename
            if config.is_file():
                paths.append(config)
    return paths


def read_json_config(path: Path) -> dict[str, Any] | None:
    """读取 JSON 配置文件，失败返回 None。"""
    try:
        import json
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def find_nested_configs(root: Path, suffixes: tuple[str, ...] = (".json", ".yaml", ".yml")) -> list[Path]:
    """递归扫描目录下所有配置文件，支持子目录嵌套。"""
    if not root.is_dir():
        return []
    result: list[Path] = []
    for item in root.rglob("*"):
        if item.is_file() and item.suffix in suffixes and not item.name.startswith("__"):
            result.append(item)
    return sorted(result, key=lambda p: p.name.lower())
