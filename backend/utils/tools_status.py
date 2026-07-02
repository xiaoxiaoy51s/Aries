"""CLI 工具检测模块。

使用 shutil.which() 检测系统 PATH 中的 CLI 工具，
读取 ~/.Aries/config/tools.json 持久化用户连接状态。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

# 已知 CLI 工具的元数据
# 每个工具条目的格式：
#   id:        前端使用的唯一标识符（英文小写）
#   name:      中文名称
#   binary:    要检测的二进制名（list，任一命中即可）
#   description: 简短的用途描述
# AI 编码代理 CLI 候选列表
# binary:    要检测的可执行文件名（list，任一命中即可）
# vendor:    厂商 / 品牌标识，用于前端着色
# run_cmd:   非交互式单次执行的命令模板，{prompt} 会被替换
# version_flag: 获取版本号的参数
CLI_CANDIDATES: list[dict[str, Any]] = [
    {
        "id": "claude",
        "name": "Claude Code",
        "binary": ["claude"],
        "description": "Anthropic 终端编码代理",
        "vendor": "anthropic",
        "version_flag": "--version",
    },
    {
        "id": "codex",
        "name": "Codex CLI",
        "binary": ["codex"],
        "description": "OpenAI Codex 命令行编码代理",
        "vendor": "openai",
        "version_flag": "--version",
    },
    {
        "id": "opencode",
        "name": "OpenCode",
        "binary": ["opencode"],
        "description": "开源终端编码代理",
        "vendor": "opencode",
        "version_flag": "--version",
    },
    {
        "id": "mimocode",
        "name": "MiMo Code",
        "binary": ["mimocode", "mimo"],
        "description": "小米 MiMo 终端编码代理",
        "vendor": "xiaomi",
        "version_flag": "--version",
    },
    {
        "id": "trae",
        "name": "Trae CLI",
        "binary": ["traecli", "trae"],
        "description": "字节跳动 Trae 终端编码代理",
        "vendor": "bytedance",
        "version_flag": "--version",
    },
    {
        "id": "codebuddy",
        "name": "CodeBuddy",
        "binary": ["codebuddy", "cbc"],
        "description": "腾讯 CodeBuddy 终端编码代理",
        "vendor": "tencent",
        "version_flag": "--version",
    },
    {
        "id": "qoder",
        "name": "Qoder CLI",
        "binary": ["qodercli"],
        "description": "Qoder 终端编码代理",
        "vendor": "qoder",
        "version_flag": "--version",
    },
    {
        "id": "gemini",
        "name": "Gemini CLI",
        "binary": ["gemini"],
        "description": "Google Gemini 终端编码代理",
        "vendor": "google",
        "version_flag": "--version",
    },
    {
        "id": "kimi",
        "name": "Kimi Code",
        "binary": ["kimi"],
        "description": "月之暗面 Kimi 终端编码代理",
        "vendor": "moonshot",
        "version_flag": "--version",
    },
    {
        "id": "vscode",
        "name": "VS Code CLI",
        "binary": ["code"],
        "description": "VS Code 命令行启动器",
        "vendor": "microsoft",
        "version_flag": "--version",
    },
    {
        "id": "cursor",
        "name": "Cursor CLI",
        "binary": ["cursor-agent", "agent"],
        "description": "Cursor 编辑器终端编码代理",
        "vendor": "cursor",
        "version_flag": "--version",
    },
]

# 支持手动连接方式的 CLI（如 Docker Desktop / Python 官方安装器）
# 这类工具即使不在 PATH 中，用户也可以提供路径手动连接
# 所有 CLI 均支持手动连接（用户可提供本地安装路径）
CONNECTABLE_CLI_IDS: set[str] = {c["id"] for c in CLI_CANDIDATES}


# 路由配置：定义每个 CLI 如何被调用（单次执行模式）
# prompt_flag: prompt 参数前缀，空字符串表示 prompt 作为位置参数
# extra_args:  额外固定参数
# conversation_mode: separate=每次新会话 / history_only=追加历史 / none=单次执行
CLI_ROUTING_CONFIGS: dict[str, dict[str, Any]] = {
    "claude": {
        "prompt_flag": "-p",
        "extra_args": ["--dangerously-skip-permissions"],
        "conversation_mode": "separate",
    },
    "codex": {
        "prompt_flag": "",
        "extra_args": ["exec", "--skip-git-repo-check"],
        "conversation_mode": "history_only",
    },
    "opencode": {
        "prompt_flag": "",
        "extra_args": ["run"],
        "conversation_mode": "none",
    },
    "mimocode": {
        "prompt_flag": "",
        "extra_args": ["run"],
        "conversation_mode": "none",
    },
    "trae": {
        "prompt_flag": "",
        "extra_args": ["run"],
        "conversation_mode": "none",
    },
    "codebuddy": {
        "prompt_flag": "-p",
        "extra_args": [],
        "conversation_mode": "separate",
    },
    "qoder": {
        "prompt_flag": "",
        "extra_args": ["--yolo"],
        "conversation_mode": "none",
    },
    "gemini": {
        "prompt_flag": "",
        "extra_args": ["--code-only"],
        "conversation_mode": "separate",
    },
    "kimi": {
        "prompt_flag": "-p",
        "extra_args": [],
        "conversation_mode": "separate",
    },
    "vscode": {
        "prompt_flag": "",
        "extra_args": [],
        "conversation_mode": "none",
    },
    "cursor": {
        "prompt_flag": "",
        "extra_args": [],
        "conversation_mode": "separate",
    },
}


def detect_cli(cli_id: str, binary_names: list[str]) -> dict[str, Any]:
    """检测单个 CLI 是否在系统 PATH 中"""
    for name in binary_names:
        found = shutil.which(name)
        if found:
            return {
                "id": cli_id,
                "installed": True,
                "path": found,
                "binary": name,
            }
    return {
        "id": cli_id,
        "installed": False,
        "path": None,
        "binary": None,
    }


def detect_all_clis() -> list[dict[str, Any]]:
    """检测所有已知 CLI 工具"""
    results = []
    for candidate in CLI_CANDIDATES:
        result = detect_cli(candidate["id"], candidate["binary"])
        result["name"] = candidate["name"]
        result["description"] = candidate["description"]
        result["connectable"] = candidate["id"] in CONNECTABLE_CLI_IDS
        results.append(result)
    return results


def detect_cli_by_id(cli_id: str) -> dict[str, Any] | None:
    """按 id 检测单个 CLI"""
    for candidate in CLI_CANDIDATES:
        if candidate["id"] == cli_id:
            result = detect_cli(candidate["id"], candidate["binary"])
            result["name"] = candidate["name"]
            result["description"] = candidate["description"]
            result["connectable"] = candidate["id"] in CONNECTABLE_CLI_IDS
            return result
    return None
