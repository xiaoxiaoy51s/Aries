"""Network Manager - 代理配置与域名规则匹配

配置文件：~/.Aries/network.json（用户在前端设置页面维护）
{
  "enabled": true,
  "proxy_url": "http://127.0.0.1:7890",
  "proxy_domains": ["google.com", "github.com", ...],
  "proxy_commands": ["npm install", "git clone", "pip install", ...],
  "command_proxy": true
}

工作模式：按域名规则匹配
- 访问 proxy_domains 中的域名时走代理
- 执行 proxy_commands 中的命令前缀时注入代理环境变量
- 其他直连
"""
from __future__ import annotations

import json
import logging
import os
import platform
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

NETWORK_CONFIG_PATH = Path.home() / ".Aries" / "network.json"

# 用户未配置时使用的默认命令前缀（仅作为初始模板，用户可自行修改）
_DEFAULT_PROXY_COMMANDS = [
    "npm install",
    "npm i ",
    "npm ci",
    "yarn install",
    "yarn add",
    "pnpm install",
    "pnpm add",
    "git clone",
    "git pull",
    "git push",
    "git fetch",
    "pip install",
    "pip3 install",
    "poetry install",
    "go install",
    "go get",
    "go mod download",
    "docker pull",
    "cargo install",
]


def _default_config() -> dict[str, Any]:
    return {
        "enabled": False,
        "proxy_url": "http://127.0.0.1:7890",
        "proxy_domains": [],
        "proxy_commands": list(_DEFAULT_PROXY_COMMANDS),
        "command_proxy": True,
    }


def load_network_config() -> dict[str, Any]:
    """读取 network.json，不存在则返回默认配置。"""
    if not NETWORK_CONFIG_PATH.exists():
        return _default_config()
    try:
        raw = json.loads(NETWORK_CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return _default_config()
        # 合并默认值，确保字段完整
        config = _default_config()
        config.update(raw)
        # proxy_domains 如果用户配置了，就直接用用户的（不合并默认）
        if "proxy_domains" in raw and isinstance(raw["proxy_domains"], list):
            config["proxy_domains"] = [str(d).strip() for d in raw["proxy_domains"] if str(d).strip()]
        # proxy_commands 同理
        if "proxy_commands" in raw and isinstance(raw["proxy_commands"], list):
            config["proxy_commands"] = [str(c).strip() for c in raw["proxy_commands"] if str(c).strip()]
        return config
    except Exception as exc:
        logger.warning("读取 network.json 失败: %s", exc)
        return _default_config()


def save_network_config(config: dict[str, Any]) -> None:
    """保存配置到 network.json。"""
    NETWORK_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    NETWORK_CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def ensure_network_config_exists() -> None:
    """如果 network.json 不存在，创建默认配置。"""
    if not NETWORK_CONFIG_PATH.exists():
        save_network_config(_default_config())


def is_proxy_enabled() -> bool:
    """代理是否启用。"""
    return bool(load_network_config().get("enabled", False))


def get_proxy_url() -> str:
    """获取代理 URL。"""
    return str(load_network_config().get("proxy_url", "http://127.0.0.1:7890"))


def _domain_matches(target_domain: str, proxy_domains: list[str]) -> bool:
    """检查目标域名是否匹配代理域名列表。

    匹配规则：子域名也算匹配。例如 proxy_domains 含 "google.com"，
    则 "www.google.com"、"maps.google.com" 都匹配。
    """
    target = target_domain.lower().strip()
    if target.startswith("www."):
        target = target[4:]
    for domain in proxy_domains:
        d = domain.lower().strip()
        if d.startswith("www."):
            d = d[4:]
        if target == d or target.endswith("." + d):
            return True
    return False


def should_use_proxy_for_url(url: str) -> bool:
    """检查指定 URL 是否应该走代理。

    条件：代理启用 + 域名匹配规则。
    """
    config = load_network_config()
    if not config.get("enabled", False):
        return False
    try:
        domain = urlparse(url).netloc.lower()
        if not domain:
            return False
        return _domain_matches(domain, config.get("proxy_domains", []))
    except Exception:
        return False


def get_proxy_for_url(url: str) -> dict[str, str] | None:
    """获取指定 URL 的代理配置。

    返回 {"http": "...", "https": "..."} 或 None（不走代理）。
    """
    if not should_use_proxy_for_url(url):
        return None
    proxy_url = get_proxy_url()
    return {"http": proxy_url, "https": proxy_url}


def should_inject_proxy_for_command(command: str) -> bool:
    """检查指定命令是否需要注入代理环境变量。

    条件：代理启用 + command_proxy=true + 命令匹配用户配置的 proxy_commands。
    """
    config = load_network_config()
    if not config.get("enabled", False):
        return False
    if not config.get("command_proxy", True):
        return False
    cmd = command.strip().lower()
    for prefix in config.get("proxy_commands", []):
        if cmd.startswith(prefix.strip().lower()):
            return True
    return False


def get_proxy_env_for_command(command: str) -> dict[str, str]:
    """获取命令执行时需要注入的代理环境变量。

    返回环境变量 dict（可能为空）。
    包含 HTTP_PROXY, HTTPS_PROXY, ALL_PROXY。
    同时设置 npm/git/pip 专用变量。
    """
    if not should_inject_proxy_for_command(command):
        return {}
    proxy_url = get_proxy_url()
    env: dict[str, str] = {
        "HTTP_PROXY": proxy_url,
        "HTTPS_PROXY": proxy_url,
        "http_proxy": proxy_url,
        "https_proxy": proxy_url,
        "ALL_PROXY": proxy_url,
        "all_proxy": proxy_url,
    }
    # npm 专用
    if "npm" in command.lower():
        env["npm_config_proxy"] = proxy_url
        env["npm_config_https-proxy"] = proxy_url
    return env


def wrap_command_with_proxy(command: str) -> str:
    """如果命令需要代理，在命令前注入跨平台的环境变量设置。

    Windows (cmd.exe)：用 set X=Y && 前缀
    Linux/Mac (bash/sh)：用 X=Y 前缀
    """
    if not should_inject_proxy_for_command(command):
        return command
    proxy_url = get_proxy_url()
    env_vars = [
        f"HTTP_PROXY={proxy_url}",
        f"HTTPS_PROXY={proxy_url}",
        f"http_proxy={proxy_url}",
        f"https_proxy={proxy_url}",
        f"ALL_PROXY={proxy_url}",
        f"all_proxy={proxy_url}",
    ]
    if platform.system() == "Windows":
        # PowerShell: $env:X="Y"; $env:Z="W"; command
        prefix = "; ".join(f'$env:{k}="{v}"' for k, v in env_vars.items()) + "; "
    else:
        # bash/sh: X=Y Z=W command
        prefix = " ".join(env_vars) + " "
    return prefix + command.strip()
