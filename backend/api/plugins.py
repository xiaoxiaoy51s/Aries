from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import json

from utils.plugins_manager import (
    MCP_CACHE_ROOT,
    discover_plugins,
    get_mcp_config_path,
    get_mcp_server_config,
    import_mcp_json,
    set_plugin_enabled,
)

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


class PluginStatusUpdate(BaseModel):
    enabled: bool


class PluginImport(BaseModel):
    config_json: str = Field(min_length=1)


def _reload_mcp_pool() -> None:
    from utils.mcp_runtime import get_mcp_pool

    get_mcp_pool().rebuild(force=True)


@router.get("")
async def list_plugins():
    """返回用户在 ~/.MIMOClaw/mcp.json 中配置的 MCP 插件。"""
    from utils.mcp_runtime import get_mcp_diagnostics

    entries = discover_plugins()
    diagnostics = {item["id"]: item for item in get_mcp_diagnostics()}
    plugins = []
    for entry in entries:
        data = entry.to_api_dict()
        diag = diagnostics.get(entry.id)
        if diag:
            data["status"] = diag.get("status", data.get("status"))
            data["tool_count"] = diag.get("tool_count", data.get("tool_count", 0))
            if diag.get("last_error"):
                data["last_error"] = diag["last_error"]
        plugins.append(data)

    return {
        "plugins": plugins,
        "config_path": get_mcp_config_path(),
        "cache_root": str(MCP_CACHE_ROOT),
        "diagnostics": list(diagnostics.values()),
    }


@router.get("/{plugin_id}")
async def get_plugin_detail(plugin_id: str):
    """返回单个 MCP 插件的配置 JSON。"""
    from utils.mcp_runtime import get_mcp_diagnostics

    server = get_mcp_server_config(plugin_id)
    if server is None:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_id} 不存在")

    wrapped = {"mcpServers": {plugin_id: server}}
    diagnostics = {item["id"]: item for item in get_mcp_diagnostics()}
    diag = diagnostics.get(plugin_id, {})

    return {
        "id": plugin_id,
        "name": plugin_id,
        "description": server.get("description") if isinstance(server.get("description"), str) else "",
        "enabled": not (server.get("disabled") is True or server.get("enabled") is False),
        "config_path": get_mcp_config_path(),
        "server_config": server,
        "config_json": json.dumps(wrapped, ensure_ascii=False, indent=2) + "\n",
        "status": diag.get("status"),
        "tool_count": diag.get("tool_count", 0),
        "last_error": diag.get("last_error"),
    }


@router.put("/{plugin_id}/status")
async def update_plugin_status(plugin_id: str, body: PluginStatusUpdate):
    """启用或禁用 MCP 插件。"""
    found = any(entry.id == plugin_id for entry in discover_plugins())
    if not found:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_id} 不存在")
    try:
        set_plugin_enabled(plugin_id, body.enabled)
        _reload_mcp_pool()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": plugin_id, "enabled": body.enabled}


@router.post("/import")
async def import_plugins(body: PluginImport):
    """粘贴 Trae/Cursor 风格的 MCP JSON 并合并到 mcp.json。"""
    try:
        added = import_mcp_json(body.config_json)
        if added:
            _reload_mcp_pool()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"added": added, "count": len(added)}


@router.post("/refresh")
async def refresh_plugins():
    """手动刷新 MCP 连接池（类似 Kun 重启 runtime）。"""
    _reload_mcp_pool()
    from utils.mcp_runtime import get_mcp_diagnostics, get_mcp_tool_definitions

    return {
        "tool_count": len(get_mcp_tool_definitions()),
        "diagnostics": get_mcp_diagnostics(),
    }
