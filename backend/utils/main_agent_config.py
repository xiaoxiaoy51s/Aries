"""Main Agent 配置管理

配置文件：~/.Aries/agent/main_agent.json
{
  "allowed_skills": ["web_search", "playwright_cli"],
  "allowed_mcps": ["playwright"]
}

主 Agent 只加载 allowed_skills 中的技能工具和 allowed_mcps 中的 MCP 工具。
未列出的技能/MCP 在系统中始终可用（供子 Agent 使用），但主 Agent 不会加载。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AGENT_DIR = Path.home() / ".Aries" / "agent"
MAIN_AGENT_CONFIG_PATH = AGENT_DIR / "main_agent.json"


def _default_config() -> dict[str, Any]:
    return {
        "allowed_skills": [],
        "allowed_mcps": [],
    }


def load_main_agent_config() -> dict[str, Any]:
    """读取主 Agent 配置。"""
    if not MAIN_AGENT_CONFIG_PATH.exists():
        return _default_config()
    try:
        raw = json.loads(MAIN_AGENT_CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return _default_config()
        return {
            "allowed_skills": [str(s).strip() for s in raw.get("allowed_skills", []) if str(s).strip()],
            "allowed_mcps": [str(m).strip() for m in raw.get("allowed_mcps", []) if str(m).strip()],
        }
    except Exception as exc:
        logger.warning("读取 main_agent.json 失败: %s", exc)
        return _default_config()


def save_main_agent_config(config: dict[str, Any]) -> None:
    """保存主 Agent 配置。"""
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "allowed_skills": [str(s).strip() for s in config.get("allowed_skills", []) if str(s).strip()],
        "allowed_mcps": [str(m).strip() for m in config.get("allowed_mcps", []) if str(m).strip()],
    }
    MAIN_AGENT_CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def ensure_main_agent_config_exists() -> None:
    """如果 main_agent.json 不存在，创建默认配置。"""
    if not MAIN_AGENT_CONFIG_PATH.exists():
        save_main_agent_config(_default_config())


def get_main_agent_allowed_skills() -> list[str]:
    """获取主 Agent 允许使用的技能 folder_name 列表。"""
    return load_main_agent_config().get("allowed_skills", [])


def get_main_agent_allowed_mcps() -> list[str]:
    """获取主 Agent 允许使用的 MCP ID 列表。"""
    return load_main_agent_config().get("allowed_mcps", [])


def is_skill_allowed_for_main_agent(folder_name: str) -> bool:
    """检查技能是否在主 Agent 的允许列表中。空列表表示全部允许（向后兼容）。"""
    allowed = get_main_agent_allowed_skills()
    if not allowed:
        return True
    return folder_name in allowed


def is_mcp_allowed_for_main_agent(mcp_id: str) -> bool:
    """检查 MCP 是否在主 Agent 的允许列表中。空列表表示全部允许（向后兼容）。"""
    allowed = get_main_agent_allowed_mcps()
    if not allowed:
        return True
    return mcp_id in allowed
