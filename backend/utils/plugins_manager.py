from __future__ import annotations

import json
import re
from dataclasses import dataclass
from json import JSONDecoder
from pathlib import Path
from typing import Any

MIMOCLAW_ROOT = Path.home() / ".MIMOClaw"
MCP_CONFIG_PATH = MIMOCLAW_ROOT / "mcp.json"
MCP_EXAMPLE_PATH = MIMOCLAW_ROOT / "mcp.example.json"
MCP_CACHE_ROOT = MIMOCLAW_ROOT / "mcps"

MCP_EXAMPLE_CONTENT = """{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    },
    "fetch": {
      "command": "uvx",
      "args": ["mcp-server-fetch"]
    },
    "remote-example": {
      "type": "streamable-http",
      "url": "https://example.com/mcp",
      "headers": {
        "Authorization": "Bearer your-token"
      }
    }
  }
}
"""


@dataclass
class PluginEntry:
    id: str
    name: str
    description: str
    enabled: bool
    transport: str = ""
    command: str = ""
    status: str = ""
    tool_count: int = 0

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "transport": self.transport,
            "command": self.command,
            "status": self.status,
            "tool_count": self.tool_count,
        }


def _ensure_config_dir() -> None:
    MIMOCLAW_ROOT.mkdir(parents=True, exist_ok=True)
    MCP_CACHE_ROOT.mkdir(parents=True, exist_ok=True)


def _empty_config() -> dict[str, Any]:
    return {"mcpServers": {}}


def ensure_mcp_files() -> None:
    _ensure_config_dir()
    if not MCP_EXAMPLE_PATH.is_file():
        MCP_EXAMPLE_PATH.write_text(MCP_EXAMPLE_CONTENT, encoding="utf-8")
    if not MCP_CONFIG_PATH.is_file():
        MCP_CONFIG_PATH.write_text(json.dumps(_empty_config(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_server_entry(server_id: str, raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    entry = dict(raw)
    if "transport" not in entry and not entry.get("type"):
        if entry.get("command"):
            entry["transport"] = "stdio"
        elif entry.get("url"):
            entry["transport"] = "streamable-http"
    return entry


def _normalize_transport_token(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def resolve_mcp_transport(server: dict[str, Any]) -> str:
    """解析 MCP 传输方式：stdio / sse / streamable-http。"""
    raw = server.get("transport") or server.get("type")
    if isinstance(raw, str) and raw.strip():
        token = _normalize_transport_token(raw)
        if token == "stdio":
            return "stdio"
        if token == "sse":
            return "sse"
        if token in {"http", "streamable-http", "streamablehttp"}:
            return "streamable-http"

    if server.get("url"):
        return "streamable-http"
    if server.get("command"):
        return "stdio"
    raise ValueError("缺少 command（stdio）或 url（http/sse）")


def build_mcp_http_headers(server: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    raw_headers = server.get("headers")
    if isinstance(raw_headers, dict):
        headers = {str(key): str(value) for key, value in raw_headers.items()}

    bearer = server.get("bearerToken") or server.get("bearer_token")
    if isinstance(bearer, str) and bearer.strip():
        headers.setdefault("Authorization", f"Bearer {bearer.strip()}")
    return headers


def _extract_servers_block(parsed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """兼容 mcpServers（Trae/Cursor）与 servers（MIMOClaw 旧写法）。"""
    merged: dict[str, dict[str, Any]] = {}
    for key in ("mcpServers", "servers"):
        block = parsed.get(key)
        if not isinstance(block, dict):
            continue
        for server_id, raw in block.items():
            if not isinstance(server_id, str) or not server_id.strip():
                continue
            normalized = _normalize_server_entry(server_id.strip(), raw)
            if normalized is not None:
                merged[server_id.strip()] = normalized
    return merged


def _normalize_mcp_config(parsed: dict[str, Any]) -> dict[str, Any]:
    servers = _extract_servers_block(parsed)
    return {"mcpServers": servers}


def load_mcp_config() -> dict[str, Any]:
    ensure_mcp_files()
    try:
        parsed = json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_config()
    if not isinstance(parsed, dict):
        return _empty_config()
    return _normalize_mcp_config(parsed)


def save_mcp_config(config: dict[str, Any]) -> None:
    _ensure_config_dir()
    servers = config.get("mcpServers") or config.get("servers") or {}
    if not isinstance(servers, dict):
        servers = {}
    payload = {"mcpServers": servers}
    MCP_CONFIG_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_json_fragments(text: str) -> list[dict[str, Any]]:
    """解析粘贴内容，支持多个 JSON 对象连续粘贴。"""
    raw = text.strip()
    if not raw:
        return []
    try:
        single = json.loads(raw)
        if isinstance(single, dict):
            return [single]
    except json.JSONDecodeError:
        pass

    decoder = JSONDecoder()
    results: list[dict[str, Any]] = []
    idx = 0
    while idx < len(raw):
        while idx < len(raw) and raw[idx].isspace():
            idx += 1
        if idx >= len(raw):
            break
        try:
            obj, end = decoder.raw_decode(raw, idx)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 解析失败: {exc}") from exc
        if isinstance(obj, dict):
            results.append(obj)
        idx = end
    return results


def import_mcp_json(raw_text: str) -> list[str]:
    """合并粘贴的 MCP 配置到 mcp.json，返回新增的 server id 列表。"""
    fragments = parse_json_fragments(raw_text)
    if not fragments:
        raise ValueError("请粘贴有效的 MCP JSON 配置")

    incoming: dict[str, dict[str, Any]] = {}
    for fragment in fragments:
        incoming.update(_extract_servers_block(fragment))
        if not incoming and fragment.get("command"):
            raise ValueError("缺少 mcpServers 键，请粘贴完整配置片段")

    if not incoming:
        raise ValueError("未找到 mcpServers 配置")

    config = load_mcp_config()
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
        config["mcpServers"] = servers

    added: list[str] = []
    for server_id, entry in incoming.items():
        if server_id not in servers:
            added.append(server_id)
        servers[server_id] = entry

    save_mcp_config(config)
    return added


def _server_transport(server: dict[str, Any]) -> str:
    try:
        return resolve_mcp_transport(server)
    except ValueError:
        return "unknown"


def _server_status(server: dict[str, Any], enabled: bool) -> str:
    if not enabled:
        return "disabled"
    last_error = server.get("lastError")
    if isinstance(last_error, str) and last_error.strip():
        return "error"
    return "configured"


def _server_description(server: dict[str, Any]) -> str:
    description = server.get("description")
    if isinstance(description, str) and description.strip():
        return description.strip()
    command = server.get("command")
    url = server.get("url")
    if isinstance(command, str) and command.strip():
        args = server.get("args")
        arg_text = ""
        if isinstance(args, list) and args:
            arg_text = " ".join(str(item) for item in args[:4])
        return f"{command} {arg_text}".strip()
    if isinstance(url, str) and url.strip():
        return url.strip()
    return "MCP 服务"


def _is_server_enabled(server: dict[str, Any]) -> bool:
    if server.get("disabled") is True:
        return False
    if server.get("enabled") is False:
        return False
    if server.get("isActive") is False:
        return False
    return True


def _cached_tool_count(server_id: str) -> int:
    tools_dir = MCP_CACHE_ROOT / _safe_dir_name(server_id) / "tools"
    if not tools_dir.is_dir():
        return 0
    return sum(1 for path in tools_dir.glob("*.json") if path.is_file())


def _safe_dir_name(server_id: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", server_id.strip()) or "unknown"


def get_mcp_cache_dir(server_id: str) -> Path:
    return MCP_CACHE_ROOT / _safe_dir_name(server_id)


def get_enabled_servers() -> dict[str, dict[str, Any]]:
    config = load_mcp_config()
    servers = config.get("mcpServers", {})
    if not isinstance(servers, dict):
        return {}
    enabled: dict[str, dict[str, Any]] = {}
    for server_id, raw in servers.items():
        if not server_id.strip() or not isinstance(raw, dict):
            continue
        if _is_server_enabled(raw):
            enabled[server_id] = raw
    return enabled


def discover_plugins() -> list[PluginEntry]:
    config = load_mcp_config()
    servers = config.get("mcpServers", {})
    if not isinstance(servers, dict):
        return []

    entries: list[PluginEntry] = []
    for plugin_id, raw_server in sorted(servers.items()):
        if not plugin_id.strip() or not isinstance(raw_server, dict):
            continue
        enabled = _is_server_enabled(raw_server)
        command = raw_server.get("command")
        entries.append(
            PluginEntry(
                id=plugin_id,
                name=plugin_id,
                description=_server_description(raw_server),
                enabled=enabled,
                transport=_server_transport(raw_server),
                command=command if isinstance(command, str) else "",
                status=_server_status(raw_server, enabled),
                tool_count=_cached_tool_count(plugin_id),
            )
        )
    return entries


def set_plugin_enabled(plugin_id: str, enabled: bool) -> None:
    config = load_mcp_config()
    servers = config.get("mcpServers", {})
    if not isinstance(servers, dict) or plugin_id not in servers:
        raise FileNotFoundError(f"插件 {plugin_id} 不存在，请先在 mcp.json 中配置")
    server = servers[plugin_id]
    if not isinstance(server, dict):
        raise FileNotFoundError(f"插件 {plugin_id} 配置无效")
    server["disabled"] = not enabled
    server["enabled"] = enabled
    save_mcp_config(config)


def get_mcp_server_config(plugin_id: str) -> dict[str, Any] | None:
    config = load_mcp_config()
    servers = config.get("mcpServers", {})
    if not isinstance(servers, dict):
        return None
    server = servers.get(plugin_id)
    return dict(server) if isinstance(server, dict) else None


def get_mcp_config_path() -> str:
    ensure_mcp_files()
    return str(MCP_CONFIG_PATH)
