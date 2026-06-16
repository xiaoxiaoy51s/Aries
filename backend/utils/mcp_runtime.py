from __future__ import annotations

import asyncio
import json
import re
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from datetime import timedelta

from utils.plugins_manager import (
    build_mcp_http_headers,
    discover_plugins,
    get_enabled_servers,
    get_mcp_cache_dir,
    resolve_mcp_transport,
)

DEFAULT_TIMEOUT_MS = 30_000


@dataclass(frozen=True)
class McpToolRoute:
    server_id: str
    tool_name: str
    exposed_name: str


@dataclass
class McpServerDiagnostic:
    id: str
    enabled: bool
    transport: str
    status: str  # disabled | connected | error
    tool_count: int = 0
    last_error: str | None = None
    last_connected_at: str | None = None
    catalog_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "enabled": self.enabled,
            "transport": self.transport,
            "status": self.status,
            "tool_count": self.tool_count,
            "last_error": self.last_error,
            "last_connected_at": self.last_connected_at,
            "catalog_fingerprint": self.catalog_fingerprint,
        }


@dataclass
class _ServerConnection:
    server_id: str
    server: dict[str, Any]
    stack: AsyncExitStack
    session: Any
    tools: list[dict[str, Any]] = field(default_factory=list)
    status: str = "connected"
    last_error: str | None = None
    last_connected_at: str | None = None
    catalog_fingerprint: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return text.strip("_") or "tool"


def normalize_mcp_tool_name(server_id: str, tool_name: str) -> str:
    """与 Kun 一致：mcp_{server}_{tool}"""
    return f"mcp_{_slug(server_id)}_{_slug(tool_name)}"


def _catalog_fingerprint(tool_names: list[str]) -> str:
    payload = json.dumps(sorted(tool_names), ensure_ascii=True)
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


def _tool_schema_dict(tool: Any) -> dict[str, Any]:
    name = getattr(tool, "name", None) or ""
    description = getattr(tool, "description", None) or ""
    input_schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}
    if not isinstance(input_schema, dict):
        input_schema = {}
    return {
        "name": str(name),
        "description": str(description),
        "arguments": input_schema,
    }


def _cache_server_tools(server_id: str, tools: list[Any]) -> None:
    cache_dir = get_mcp_cache_dir(server_id)
    tools_dir = cache_dir / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = cache_dir / "SERVER_METADATA.json"
    metadata_path.write_text(
        json.dumps({"server_name": server_id}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for old_file in tools_dir.glob("*.json"):
        old_file.unlink(missing_ok=True)

    for tool in tools:
        schema = _tool_schema_dict(tool)
        tool_name = str(schema.get("name") or "").strip()
        if not tool_name:
            continue
        safe_name = tool_name.replace("/", "_").replace("\\", "_")
        tool_path = tools_dir / f"{safe_name}.json"
        tool_path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _load_cached_tool_schemas(server_id: str) -> list[dict[str, Any]]:
    tools_dir = get_mcp_cache_dir(server_id) / "tools"
    if not tools_dir.is_dir():
        return []
    schemas: list[dict[str, Any]] = []
    for path in sorted(tools_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("name"):
            schemas.append(data)
    return schemas


def _schema_to_openai(exposed_name: str, schema: dict[str, Any], server_id: str) -> dict[str, Any]:
    description = schema.get("description") or f"MCP 工具（{server_id}）"
    input_schema = schema.get("arguments") or {}
    if not isinstance(input_schema, dict):
        input_schema = {}
    properties = input_schema.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    required = input_schema.get("required")
    if not isinstance(required, list):
        required = []
    return {
        "type": "function",
        "function": {
            "name": exposed_name,
            "description": str(description),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def _extract_tool_result(result: Any) -> str:
    content = getattr(result, "content", None)
    if not content:
        return ""
    chunks: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            chunks.append(text)
            continue
        if isinstance(block, dict):
            block_text = block.get("text")
            if isinstance(block_text, str) and block_text.strip():
                chunks.append(block_text)
    if chunks:
        return "\n".join(chunks)
    if hasattr(result, "model_dump"):
        return json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
    return str(result)


def _server_transport(server: dict[str, Any]) -> str:
    try:
        return resolve_mcp_transport(server)
    except ValueError:
        return "unknown"


def _http_server_url(server: dict[str, Any]) -> str:
    url = server.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("缺少 url")
    return url.strip()


def _sse_read_timeout_seconds(server: dict[str, Any]) -> float:
    for key in ("sseReadTimeoutMs", "sse_read_timeout_ms"):
        value = server.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value) / 1000.0
    return 300.0


def _timeout_seconds(server: dict[str, Any]) -> float:
    timeout_ms = server.get("timeoutMs")
    if isinstance(timeout_ms, (int, float)) and timeout_ms > 0:
        return float(timeout_ms) / 1000.0
    return DEFAULT_TIMEOUT_MS / 1000.0


def _stdio_server_params(server: dict[str, Any]):
    from mcp import StdioServerParameters

    command = server.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("缺少 command")

    args = server.get("args")
    arg_list = [str(item) for item in args] if isinstance(args, list) else []

    env = server.get("env")
    env_dict = {str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else None

    return StdioServerParameters(
        command=command.strip(),
        args=arg_list,
        env=env_dict,
    )


async def _list_all_tools(session: Any, timeout: float) -> list[Any]:
    tools: list[Any] = []
    cursor: str | None = None
    while True:
        response = await session.list_tools(cursor=cursor) if cursor else await session.list_tools()
        tools.extend(list(getattr(response, "tools", []) or []))
        cursor = getattr(response, "nextCursor", None)
        if not cursor:
            break
    return tools


class McpConnectionPool:
    """参考 Kun buildMcpToolProviders：启动时建连、长连接复用、失败重连。"""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._connections: dict[str, _ServerConnection] = {}
        self._routes: dict[str, McpToolRoute] = {}
        self._definitions: list[dict[str, Any]] = []
        self._diagnostics: list[McpServerDiagnostic] = []
        self._disabled_servers: list[McpServerDiagnostic] = []
        self._started = False

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="mcp-connection-pool",
                daemon=True,
            )
            self._thread.start()
            self._started = True

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _ensure_started(self) -> None:
        if not self._started:
            self.start()

    def _run(self, coro, timeout: float = 180.0):
        self._ensure_started()
        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    async def _connect_server(self, server_id: str, server: dict[str, Any]) -> _ServerConnection:
        from mcp import ClientSession

        transport = resolve_mcp_transport(server)
        stack = AsyncExitStack()
        timeout = _timeout_seconds(server)
        sse_read_timeout = _sse_read_timeout_seconds(server)

        if transport == "stdio":
            from mcp.client.stdio import stdio_client

            server_params = _stdio_server_params(server)
            read, write = await stack.enter_async_context(stdio_client(server_params))
        elif transport == "sse":
            from mcp.client.sse import sse_client

            read, write = await stack.enter_async_context(
                sse_client(
                    _http_server_url(server),
                    headers=build_mcp_http_headers(server),
                    timeout=timeout,
                    sse_read_timeout=sse_read_timeout,
                )
            )
        else:
            from mcp.client.streamable_http import streamablehttp_client

            read, write, _ = await stack.enter_async_context(
                streamablehttp_client(
                    _http_server_url(server),
                    headers=build_mcp_http_headers(server),
                    timeout=timedelta(seconds=timeout),
                    sse_read_timeout=timedelta(seconds=sse_read_timeout),
                )
            )

        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        live_tools = await _list_all_tools(session, timeout)
        _cache_server_tools(server_id, live_tools)
        schemas = [_tool_schema_dict(tool) for tool in live_tools if getattr(tool, "name", None)]
        fingerprint = _catalog_fingerprint([s["name"] for s in schemas])

        return _ServerConnection(
            server_id=server_id,
            server=server,
            stack=stack,
            session=session,
            tools=schemas,
            status="connected",
            last_connected_at=_now_iso(),
            catalog_fingerprint=fingerprint,
        )

    async def _disconnect_server(self, conn: _ServerConnection | None) -> None:
        if conn is None:
            return
        try:
            await conn.stack.aclose()
        except Exception:
            pass

    async def _rebuild_async(self) -> None:
        for conn in list(self._connections.values()):
            await self._disconnect_server(conn)

        self._connections.clear()
        self._routes.clear()
        self._definitions.clear()
        self._diagnostics.clear()
        self._disabled_servers.clear()

        config_servers = discover_plugins()
        enabled_map = get_enabled_servers()

        for plugin in config_servers:
            if not plugin.enabled:
                self._disabled_servers.append(
                    McpServerDiagnostic(
                        id=plugin.id,
                        enabled=False,
                        transport=plugin.transport or "stdio",
                        status="disabled",
                    )
                )

        for server_id, server in enabled_map.items():
            try:
                conn = await self._connect_server(server_id, server)
                self._connections[server_id] = conn
                self._diagnostics.append(
                    McpServerDiagnostic(
                        id=server_id,
                        enabled=True,
                        transport=_server_transport(server),
                        status="connected",
                        tool_count=len(conn.tools),
                        last_connected_at=conn.last_connected_at,
                        catalog_fingerprint=conn.catalog_fingerprint,
                    )
                )
                print(f"[mcp] 已连接 {server_id}，{len(conn.tools)} 个工具")
            except Exception as exc:
                message = str(exc)
                cached = _load_cached_tool_schemas(server_id)
                self._diagnostics.append(
                    McpServerDiagnostic(
                        id=server_id,
                        enabled=True,
                        transport=_server_transport(server),
                        status="error",
                        tool_count=len(cached),
                        last_error=message,
                    )
                )
                if cached:
                    fallback = _ServerConnection(
                        server_id=server_id,
                        server=server,
                        stack=AsyncExitStack(),
                        session=None,
                        tools=cached,
                        status="error",
                        last_error=message,
                    )
                    self._connections[server_id] = fallback
                print(f"[mcp] 连接服务 {server_id} 失败: {message}")

        self._rebuild_registry()

    def _rebuild_registry(self) -> None:
        self._routes.clear()
        self._definitions.clear()
        reserved = set()

        for server_id, conn in self._connections.items():
            for schema in conn.tools:
                original_name = str(schema.get("name") or "").strip()
                if not original_name:
                    continue
                exposed_name = normalize_mcp_tool_name(server_id, original_name)
                if exposed_name in reserved:
                    continue
                reserved.add(exposed_name)
                self._routes[exposed_name] = McpToolRoute(
                    server_id=server_id,
                    tool_name=original_name,
                    exposed_name=exposed_name,
                )
                self._definitions.append(_schema_to_openai(exposed_name, schema, server_id))

    def rebuild(self, *, force: bool = False) -> None:
        del force  # 保留参数以兼容旧调用
        with self._lock:
            self._run(self._rebuild_async())

    async def _call_tool_async(
        self,
        route: McpToolRoute,
        arguments: dict[str, Any],
    ) -> str:
        conn = self._connections.get(route.server_id)
        if conn is None or conn.session is None:
            raise RuntimeError(f"MCP 服务 {route.server_id} 未连接")

        timeout = _timeout_seconds(conn.server)
        try:
            result = await conn.session.call_tool(route.tool_name, arguments)
            conn.last_error = None
            return _extract_tool_result(result)
        except Exception as exc:
            conn.last_error = str(exc)
            await self._disconnect_server(conn)
            server = get_enabled_servers().get(route.server_id)
            if server is None:
                raise
            new_conn = await self._connect_server(route.server_id, server)
            self._connections[route.server_id] = new_conn
            self._rebuild_registry()
            result = await new_conn.session.call_tool(route.tool_name, arguments)
            return _extract_tool_result(result)

    def shutdown(self) -> None:
        with self._lock:
            if not self._started or self._loop is None:
                return
            try:
                self._run(self._shutdown_async(), timeout=30)
            except Exception as exc:
                print(f"[mcp] 关闭连接池异常: {exc}")
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=5)
            self._loop = None
            self._thread = None
            self._started = False

    async def _shutdown_async(self) -> None:
        for conn in list(self._connections.values()):
            await self._disconnect_server(conn)
        self._connections.clear()
        self._routes.clear()
        self._definitions.clear()
        self._diagnostics.clear()
        self._disabled_servers.clear()

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._definitions and not self._connections:
                self.rebuild()
            return list(self._definitions)

    def get_diagnostics(self) -> list[dict[str, Any]]:
        with self._lock:
            return [item.to_dict() for item in self._diagnostics + self._disabled_servers]

    def get_load_errors(self) -> dict[str, str]:
        errors: dict[str, str] = {}
        for item in self._diagnostics:
            if item.status == "error" and item.last_error:
                errors[item.id] = item.last_error
        for conn in self._connections.values():
            if conn.last_error:
                errors[conn.server_id] = conn.last_error
        return errors

    def execute_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if arguments is None:
            arguments = {}

        with self._lock:
            route = self._routes.get(tool_name)
            if route is None:
                self.rebuild()
                route = self._routes.get(tool_name)
            if route is None:
                return None

            server = get_enabled_servers().get(route.server_id)
            if not server:
                return {
                    "success": False,
                    "error": f"MCP 服务 {route.server_id} 未启用或不存在",
                    "output": f"❌ MCP 服务 {route.server_id} 未启用，请在插件页开启后重试。",
                }

            try:
                output = self._run(self._call_tool_async(route, arguments), timeout=_timeout_seconds(server) + 60)
                return {
                    "success": True,
                    "output": output or "(MCP 工具执行完成，无文本输出)",
                }
            except Exception as exc:
                message = str(exc)
                return {
                    "success": False,
                    "error": message,
                    "output": f"❌ MCP 工具 {tool_name} 执行失败: {message}",
                }


_pool: McpConnectionPool | None = None


def get_mcp_pool() -> McpConnectionPool:
    global _pool
    if _pool is None:
        _pool = McpConnectionPool()
    return _pool


def refresh_mcp_tool_registry(*, force_refresh: bool = False) -> None:
    get_mcp_pool().rebuild(force=force_refresh)


def get_mcp_tool_definitions(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    pool = get_mcp_pool()
    if force_refresh:
        pool.rebuild(force=True)
    return pool.get_tool_definitions()


def get_mcp_load_errors() -> dict[str, str]:
    return get_mcp_pool().get_load_errors()


def get_mcp_diagnostics() -> list[dict[str, Any]]:
    return get_mcp_pool().get_diagnostics()


def is_mcp_tool(tool_name: str) -> bool:
    pool = get_mcp_pool()
    if not pool._routes:
        pool.get_tool_definitions()
    return tool_name in pool._routes


def execute_mcp_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any] | None:
    return get_mcp_pool().execute_tool(tool_name, arguments)


def build_mcp_prompt_context() -> str:
    pool = get_mcp_pool()
    plugins = discover_plugins()
    enabled = [p for p in plugins if p.enabled]

    if not enabled:
        disabled = [p for p in plugins if not p.enabled]
        if disabled:
            names = "、".join(p.id for p in disabled)
            return (
                "【MCP 插件】\n"
                f"以下 MCP 已配置但未启用：{names}。请在插件页开启后 Agent 才能调用。\n"
            )
        return ""

    lines = [
        "【MCP 插件】",
        "以下 MCP 服务已启用。调用时请使用带 mcp_ 前缀的工具名（格式：mcp_{服务名}_{工具名}）：",
    ]

    routes_by_server: dict[str, list[str]] = {}
    for exposed_name, route in pool._routes.items():
        routes_by_server.setdefault(route.server_id, []).append(exposed_name)

    for plugin in enabled:
        tool_names = routes_by_server.get(plugin.id, [])
        if tool_names:
            lines.append(f"- {plugin.id}: {', '.join(tool_names)}")
            continue
        err = pool.get_load_errors().get(plugin.id)
        if err:
            lines.append(f"- {plugin.id}: 连接失败（{err}）")
        else:
            lines.append(f"- {plugin.id}: 已启用，工具待加载")

    errors = pool.get_load_errors()
    if errors:
        lines.append("连接异常：")
        for server_id, message in errors.items():
            lines.append(f"- {server_id}: {message}")

    return "\n".join(lines)
