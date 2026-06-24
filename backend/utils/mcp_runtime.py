from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from datetime import timedelta

from utils.plugins_manager import (
    build_mcp_http_headers,
    discover_plugins,
    get_all_servers,
    get_mcp_cache_dir,
    resolve_mcp_transport,
)

DEFAULT_TIMEOUT_MS = 120_000


@dataclass(frozen=True)
class McpToolRoute:
    server_id: str
    tool_name: str
    exposed_name: str


@dataclass
class McpServerDiagnostic:
    id: str
    transport: str
    status: str  # connected | error
    tool_count: int = 0
    last_error: str | None = None
    last_connected_at: str | None = None
    catalog_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
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


def _is_proxy_port_reachable(proxy_url: str, timeout: float = 2.0) -> bool:
    """检测代理端口是否可达。"""
    import socket
    from urllib.parse import urlparse

    try:
        parsed = urlparse(proxy_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 8080
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def _build_stdio_env(server: dict[str, Any]) -> dict[str, str] | None:
    """构建 stdio 子进程环境变量。

    优先使用 network.json 中配置的代理（设置面板），而非系统环境变量。
    代理端口不可达时不注入，避免子进程卡在连接代理端口。
    """
    import os

    # 基础环境：继承父进程（已被 main.py 清理过死代理）
    env_dict = dict(os.environ)

    # 注入 network.json 中配置的代理（需验证端口可达）
    try:
        from utils.network_manager import load_network_config

        net_config = load_network_config()
        if net_config.get("enabled") and net_config.get("proxy_url"):
            proxy_url = str(net_config["proxy_url"]).strip()
            if _is_proxy_port_reachable(proxy_url):
                for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                            "http_proxy", "https_proxy", "all_proxy"):
                    env_dict[key] = proxy_url
                # npm/npx 专用代理变量（Node.js MCP 子进程会用）
                env_dict["npm_config_proxy"] = proxy_url
                env_dict["npm_config_https_proxy"] = proxy_url
                env_dict.pop("NO_PROXY", None)
            else:
                # 代理不可达：清除所有代理变量（含 npm），避免子进程卡在连接代理端口
                # npm 的代理配置存在 .npmrc 文件中，pop 环境变量后 npm 会回退读 .npmrc，
                # 必须显式设空字符串覆盖，让 npm 不使用代理
                for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                            "http_proxy", "https_proxy", "all_proxy"):
                    env_dict.pop(key, None)
                env_dict["npm_config_proxy"] = ""
                env_dict["npm_config_https_proxy"] = ""
                env_dict["NO_PROXY"] = "*"
                print(f"[mcp] 代理端口不可达（{proxy_url}），MCP 子进程不走代理")
        else:
            # 代理未启用：清除所有代理变量（含 npm 全局配置）
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                        "http_proxy", "https_proxy", "all_proxy"):
                env_dict.pop(key, None)
            env_dict["npm_config_proxy"] = ""
            env_dict["npm_config_https_proxy"] = ""
            env_dict["NO_PROXY"] = "*"
    except Exception:
        pass

    # 合并用户在 mcp.json 中为该 server 单独配置的 env（最高优先级）
    user_env = server.get("env")
    if isinstance(user_env, dict):
        env_dict.update({str(k): str(v) for k, v in user_env.items()})

    return env_dict


def _prepare_npx_args(arg_list: list[str], env_dict: dict[str, str]) -> list[str]:
    """对 npx 命令准备参数：使用临时 .npmrc 忽略用户 .npmrc 中的代理配置。

    当子进程不需要代理时（代理未启用或端口不可达），npx 仍会读取用户 ~/.npmrc
    中的 proxy/https-proxy 并尝试连接死端口，导致启动卡住。通过 --userconfig
    指定一个干净的 .npmrc 可避免此问题。
    """
    if not arg_list or arg_list[0] not in ("-y", "--yes"):
        return arg_list

    # 仅在明确清除代理时（NO_PROXY=* 且 npm_config_proxy 为空）注入干净 npmrc
    if env_dict.get("NO_PROXY") != "*":
        return arg_list
    if env_dict.get("npm_config_proxy") not in ("", None):
        return arg_list

    cache_dir = Path(tempfile.gettempdir()) / "aries_mcp_npmrc"
    cache_dir.mkdir(parents=True, exist_ok=True)
    npmrc_path = cache_dir / "clean.npmrc"
    if not npmrc_path.exists():
        npmrc_path.write_text("registry=https://registry.npmmirror.com\n", encoding="utf-8")

    return ["--userconfig", str(npmrc_path), *arg_list]


def _stdio_server_params(server: dict[str, Any]):
    from mcp import StdioServerParameters

    command = server.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("缺少 command")

    args = server.get("args")
    arg_list = [str(item) for item in args] if isinstance(args, list) else []
    command_str = command.strip().lower()

    env_dict = _build_stdio_env(server)

    # npx 命令需要特殊处理 .npmrc 代理配置
    if command_str in ("npx",):
        arg_list = _prepare_npx_args(arg_list, env_dict)

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
        self._started = False

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            # Windows: MCP stdio 传输需要 ProactorEventLoop 来支持子进程；
            # 主循环已切换为 SelectorEventLoop，这里显式创建 ProactorEventLoop。
            if sys.platform == "win32":
                from asyncio.windows_events import ProactorEventLoop
                self._loop = ProactorEventLoop()
            else:
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
        # 用 anyio.fail_after 而非 asyncio.wait_for，避免与 anyio cancel scope 跨 task 冲突
        from anyio import fail_after
        with fail_after(timeout):
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

        all_servers = get_all_servers()

        for server_id, server in all_servers.items():
            try:
                conn = await self._connect_server(server_id, server)
                self._connections[server_id] = conn
                self._diagnostics.append(
                    McpServerDiagnostic(
                        id=server_id,
                        transport=_server_transport(server),
                        status="connected",
                        tool_count=len(conn.tools),
                        last_connected_at=conn.last_connected_at,
                        catalog_fingerprint=conn.catalog_fingerprint,
                    )
                )
                print(f"[mcp] 已连接 {server_id}，{len(conn.tools)} 个工具")
            except Exception as exc:
                exc_type = type(exc).__name__
                message = str(exc) or exc_type
                # 超时类错误补充提示
                if exc_type in ("TimeoutError", "TimeoutCancellationError"):
                    message = f"连接超时（可能需要网络代理或服务未启动）"
                cached = _load_cached_tool_schemas(server_id)
                self._diagnostics.append(
                    McpServerDiagnostic(
                        id=server_id,
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
            server = get_all_servers().get(route.server_id)
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

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._definitions and not self._connections:
                self.rebuild()
            return list(self._definitions)

    def get_diagnostics(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._diagnostics and not self._routes:
                self.rebuild()
            return [item.to_dict() for item in self._diagnostics]

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

            server = get_all_servers().get(route.server_id)
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


def get_mcp_tool_definitions(
    *,
    force_refresh: bool = False,
    allowed_mcp_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """获取 MCP 工具定义。

    Args:
        force_refresh: 是否强制刷新连接池。
        allowed_mcp_ids: 主 Agent 允许的 MCP ID 列表。None = 不过滤（子 Agent 用）；空列表 = 不加载任何。
    """
    pool = get_mcp_pool()
    if force_refresh:
        pool.rebuild(force=True)
    all_defs = pool.get_tool_definitions()

    # 按 allowed_mcp_ids 过滤
    # None = 不过滤（子 Agent 用 _filter_mcp_tools 自行过滤）；空列表 = 不加载任何 MCP
    if allowed_mcp_ids is None:
        return all_defs
    if not allowed_mcp_ids:
        return []

    allowed_set = set(allowed_mcp_ids)
    result: list[dict[str, Any]] = []
    for tool_def in all_defs:
        # MCP 工具名的格式通常是 "mcp__{server_id}__{tool_name}"
        tool_name = tool_def.get("function", {}).get("name", "")
        # 检查工具名中是否包含允许的 server_id
        for mcp_id in allowed_set:
            if mcp_id in tool_name:
                result.append(tool_def)
                break
    return result


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

    if not plugins:
        return ""

    lines = [
        "【MCP 插件】",
        "以下 MCP 服务已启用。调用时请使用带 mcp_ 前缀的工具名（格式：mcp_{服务名}_{工具名}）：",
    ]

    routes_by_server: dict[str, list[str]] = {}
    for exposed_name, route in pool._routes.items():
        routes_by_server.setdefault(route.server_id, []).append(exposed_name)

    for plugin in plugins:
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
