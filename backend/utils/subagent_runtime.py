"""Subagent Runtime - 子 Agent 执行引擎

设计要点（与 Trae Task tool 对齐 + 我们的增强）：
- 同步阻塞 + 流式状态推送：delegate_to_subagent 一次调用等到子 Agent 完成才返回
- 主 Agent 看到的返回值极简：{result, log_path} 或 {error, status, log_path}
- 子 Agent 拥有独立上下文窗口、独立 JSONL 日志，主 Agent 上下文绝不污染
- 子 Agent 通过 `report_to_main` 工具显式提交结果；未提交视为失败
- 三道防线：单轮 LLM 读超时 / 单工具超时 / 子 Agent 总超时
- stalled 指示器：长时间无新事件时仅提示，不杀任务（杀由总超时负责）
"""
from __future__ import annotations

import asyncio
import json
import logging
import platform
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable

import httpx

from utils.session_logger import SessionLogger, get_subagent_jsonl_path
from utils.token_counter import extract_usage_from_stream_chunk
from utils.url_utils import normalize_base_url

logger = logging.getLogger(__name__)

# ---- 三道防线超时 ----
SUBAGENT_MAX_ROUNDS = 15
SUBAGENT_TOTAL_TIMEOUT = 1800.0          # 30 分钟硬上限
SUBAGENT_LLM_READ_TIMEOUT = 900.0
SUBAGENT_LLM_CONNECT_TIMEOUT = 30.0
SUBAGENT_LLM_WRITE_TIMEOUT = 120.0
SUBAGENT_TOOL_TIMEOUT = 600.0
SUBAGENT_IDLE_WARN_THRESHOLD = 60.0      # 60 秒无活动 → 标记 stalled（仅提示）

REPORT_TOOL_NAME = "report_to_main"

EventEmitter = Callable[[dict[str, Any]], Awaitable[None]]


# 全局取消注册表：task_id -> cancel_event
# 用于外部（前端 / API）按 task_id 取消正在运行的子 Agent
_CANCEL_REGISTRY: dict[str, asyncio.Event] = {}


def register_cancel_event(task_id: str, event: asyncio.Event) -> None:
    _CANCEL_REGISTRY[task_id] = event


def unregister_cancel_event(task_id: str) -> None:
    _CANCEL_REGISTRY.pop(task_id, None)


def cancel_subagent(task_id: str) -> bool:
    """从外部请求取消某个正在运行的子 Agent。

    返回 True 表示找到了对应任务并已发出取消信号；False 表示未找到（可能已结束）。
    """
    event = _CANCEL_REGISTRY.get(task_id)
    if event is None:
        return False
    event.set()
    return True


def list_running_subagents() -> list[str]:
    """返回所有当前注册的（运行中的）子 Agent task_id 列表。"""
    return list(_CANCEL_REGISTRY.keys())


@dataclass
class SubagentExecution:
    """子 Agent 一次执行的全部状态。"""
    task_id: str
    subagent_name: str
    task: str
    status: str = "pending"   # pending / running / stalled / success / failed / timeout / cancelled
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    rounds: int = 0
    last_event: str = ""
    last_event_at: float = field(default_factory=time.time)
    final_output: str = ""
    error: str = ""
    log_path: str = ""

    def elapsed_ms(self) -> int:
        end = self.finished_at if self.finished_at is not None else time.time()
        return int((end - self.started_at) * 1000)

    def to_event_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "subagent": self.subagent_name,
            "task": self.task,
            "status": self.status,
            "round": self.rounds,
            "last_event": self.last_event,
            "last_event_at": self.last_event_at,
            "elapsed_ms": self.elapsed_ms(),
            "log_path": self.log_path,
        }


def get_report_to_main_tool_definition() -> dict[str, Any]:
    """子 Agent 用来回传最终结果的专用工具。"""
    return {
        "type": "function",
        "function": {
            "name": REPORT_TOOL_NAME,
            "description": (
                "向主 Agent 提交最终结果并结束本次子 Agent 任务。"
                "调用此工具后任务立即终止，message 内容会作为返回值传给主 Agent。"
                "请只保留对主 Agent 决策有价值的结论，不要重复中间过程。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "给主 Agent 的简要总结（建议不超过 500 字）。",
                    },
                    "success": {
                        "type": "boolean",
                        "description": "任务是否完成。失败时填 false 并在 message 中说明原因。",
                        "default": True,
                    },
                },
                "required": ["message"],
            },
        },
    }


def _filter_mcp_tools(all_tools: list[dict[str, Any]], allowed_mcps: list[str]) -> list[dict[str, Any]]:
    """按 server_id 过滤 MCP 工具定义。MCP 工具名约定为 `mcp_{server_id}_{tool}`。"""
    if not allowed_mcps:
        return []
    from utils.mcp_runtime import _slug  # type: ignore

    allowed_slugs = {_slug(m) for m in allowed_mcps}
    result: list[dict[str, Any]] = []
    for tool in all_tools:
        name = tool.get("function", {}).get("name", "")
        if not name.startswith("mcp_"):
            continue
        # 形如 mcp_<slug>_<tool>
        rest = name[len("mcp_"):]
        # 取最长前缀匹配 server slug
        for slug in allowed_slugs:
            if rest == slug or rest.startswith(slug + "_"):
                result.append(tool)
                break
    return result


def _build_skill_tool_definitions(
    skill_entries: list[Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """基于 skill_entries 加载工具定义（跨 available / unavailable 强制激活）。

    返回 (tool_definitions, tool_table)：
        tool_definitions: 给 LLM 的 schema 列表
        tool_table: {tool_name: skill_module} 供子 Agent 执行时直接调用，
                    避开 skills_manager.execute_tool 的 enabled-only 限制
    """
    from utils.skills_manager import CORE_TOOL_NAMES, skill_import_path

    tools: list[dict[str, Any]] = []
    table: dict[str, Any] = {}
    for entry in skill_entries:
        try:
            mod = __import__(
                skill_import_path(entry.folder_name, enabled=entry.enabled, skill_path=entry.skill_path),
                fromlist=["get_tool_definition", "get_tool_definitions", "execute"],
            )
            collected_names: list[str] = []
            if hasattr(mod, "get_tool_definitions"):
                defs = mod.get_tool_definitions()
                items = defs if isinstance(defs, list) else [defs]
                for item in items:
                    name = item.get("function", {}).get("name") if item else None
                    if name and name not in CORE_TOOL_NAMES:
                        tools.append(item)
                        collected_names.append(name)
            elif hasattr(mod, "get_tool_definition"):
                item = mod.get_tool_definition()
                name = item.get("function", {}).get("name") if item else None
                if name and name not in CORE_TOOL_NAMES:
                    tools.append(item)
                    collected_names.append(name)
            # 登记到路由表：所有由该 skill 提供的工具名都映射到 mod
            if hasattr(mod, "execute"):
                for name in collected_names:
                    table[name] = mod
        except Exception as exc:
            logger.warning("加载 skill %s 工具失败: %s", entry.folder_name, exc)
    return tools, table


def _execute_skill_tool(module: Any, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """直接调 skill 模块的 execute，绕开 skills_manager 的 enabled 检查。

    多工具 skill（有 get_tool_definitions）需要把 tool 名传进去；
    单工具 skill 直接 **args。
    """
    try:
        if hasattr(module, "get_tool_definitions"):
            call_args = dict(args)
            call_args["tool"] = tool_name
            return module.execute(**call_args)
        return module.execute(**args)
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "output": f"skill 工具 {tool_name} 执行失败: {exc}",
        }


def _build_core_tool_definitions() -> list[dict[str, Any]]:
    """加载 file_io / cli 等核心公共工具。"""
    try:
        from utils.agent_tools import get_tool_definitions

        return list(get_tool_definitions() or [])
    except Exception as exc:
        logger.warning("加载核心工具定义失败: %s", exc)
        return []


def _build_subagent_system_prompt(
    *,
    subagent_name: str,
    user_system_prompt: str,
    skills_context: str,
    task: str,
    context: str,
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    parts: list[str] = []
    parts.append(
        f"# 你的身份\n"
        f"你是被主 Agent 委派的子 Agent：`{subagent_name}`。"
        f"今天的日期是 {today}，当前操作系统：{platform.system()}。\n"
    )
    if user_system_prompt.strip():
        parts.append(f"# 详细职责\n{user_system_prompt.strip()}\n")
    parts.append(
        "# 任务通信规则\n"
        "- 你看不到主 Agent 与用户的对话历史，下方 task 已包含完成任务所需的全部信息\n"
        f"- 任务完成（或确定无法完成）时，必须调用 `{REPORT_TOOL_NAME}` 工具提交简要总结\n"
        f"- 在调用 `{REPORT_TOOL_NAME}` 之前，所有思考和工具调用都不会被主 Agent 看到\n"
        f"- 不要在 message 中重复中间过程，只保留对主 Agent 决策有价值的结论（建议 ≤500 字）\n"
        f"- 如果任务无法完成，也要调用 `{REPORT_TOOL_NAME}` 并在 message 中说明原因，success=false\n"
    )
    if skills_context:
        parts.append("# 可用本地 Skills\n" + skills_context)
    if context.strip():
        parts.append(f"# 主 Agent 提供的额外上下文\n{context.strip()}\n")
    parts.append(f"# 本次任务\n{task.strip()}")
    return "\n\n".join(parts)


def _resolve_model_credentials(model_name: str) -> tuple[str, str, str]:
    """根据 model 名解析 (base_url, api_key, real_model_id)。

    优先级：
    1. 在 ModelManager 中查找 m.model == model_name 的条目
    2. 若 model_name 为空或未匹配 → 用 active model
    """
    try:
        from models.model_manager import model_manager

        if model_name and model_name.strip():
            for m in model_manager.list_models():
                if m.model == model_name:
                    return m.baseUrl or "", m.apiKey or "", m.model
        active = model_manager.get_active_model()
        if active:
            return active.baseUrl or "", active.apiKey or "", active.model
    except Exception as exc:
        logger.warning("解析模型凭证失败: %s", exc)
    return "", "", model_name


async def _emit(emitter: EventEmitter | None, execution: SubagentExecution) -> None:
    if emitter is None:
        return
    try:
        await emitter({"subagent_event": execution.to_event_dict()})
    except Exception as exc:
        logger.debug("emitter 推送失败: %s", exc)


def _update_event(execution: SubagentExecution, label: str) -> None:
    execution.last_event = label
    execution.last_event_at = time.time()


async def _stalled_watchdog(execution: SubagentExecution, emitter: EventEmitter | None) -> None:
    """每隔 5 秒检查一次 last_event_at；超过阈值则把 status 改成 stalled 并推送一次。"""
    last_pushed_state = execution.status
    while execution.status in ("pending", "running", "stalled"):
        await asyncio.sleep(5)
        if execution.status not in ("pending", "running", "stalled"):
            return
        idle = time.time() - execution.last_event_at
        if idle >= SUBAGENT_IDLE_WARN_THRESHOLD:
            if execution.status != "stalled":
                execution.status = "stalled"
                await _emit(emitter, execution)
        else:
            if execution.status == "stalled":
                execution.status = "running"
                await _emit(emitter, execution)
        if execution.status != last_pushed_state:
            last_pushed_state = execution.status


async def run_subagent(
    *,
    subagent_name: str,
    task: str,
    context: str = "",
    work_dir: str | None = None,
    cancel_event: asyncio.Event | None = None,
    on_event: EventEmitter | None = None,
) -> dict[str, Any]:
    """执行一次子 Agent 任务。

    返回给主 Agent 的极简结构：
        成功: {"result": "<final_output>", "log_path": "..."}
        失败: {"error": "...", "status": "failed|timeout|cancelled", "log_path": "..."}
    """
    task_id = f"sa-{uuid.uuid4().hex[:8]}"
    execution = SubagentExecution(
        task_id=task_id,
        subagent_name=subagent_name,
        task=task,
        status="pending",
    )

    # 注册到全局取消表，支持外部按 task_id 取消
    if cancel_event is None:
        cancel_event = asyncio.Event()
    register_cancel_event(task_id, cancel_event)

    # 1. 加载 subagent 运行时配置
    try:
        from utils.subagent_manager import build_subagent_runtime

        runtime = build_subagent_runtime(subagent_name)
    except ValueError as exc:
        execution.status = "failed"
        execution.error = str(exc)
        execution.finished_at = time.time()
        await _emit(on_event, execution)
        unregister_cancel_event(task_id)
        return {
            "error": str(exc),
            "status": "failed",
            "log_path": "",
        }

    entry = runtime["entry"]
    skills_context = runtime["skills_context"]
    skill_entries = runtime["skill_entries"]
    mcp_servers = runtime["mcp_servers"]
    model_name = runtime["effective_model"]

    # 2. 解析模型凭证
    base_url, api_key, real_model = _resolve_model_credentials(model_name)
    if not base_url or not api_key or not real_model:
        execution.status = "failed"
        execution.error = "无法解析子 Agent 的模型凭证（base_url / api_key / model 缺失）"
        execution.finished_at = time.time()
        await _emit(on_event, execution)
        unregister_cancel_event(task_id)
        return {
            "error": execution.error,
            "status": "failed",
            "log_path": "",
        }

    # 3. 准备独立 SessionLogger（子 Agent 专属 JSONL）
    log_path = get_subagent_jsonl_path(task_id)
    sub_logger = SessionLogger(session_id=f"sub_agent_{task_id}", message_id="run")
    sub_logger.path = log_path  # 直接覆盖路径到 sub_agent 目录
    sub_logger.set_model(real_model)
    execution.log_path = str(log_path)

    # 4. 构造工具集：核心 + skills + 过滤后的 MCP + report_to_main
    #    显式不暴露 capability_search 和 delegate_to_subagent，防止递归
    core_tools = _build_core_tool_definitions()
    skill_tools, skill_tool_table = _build_skill_tool_definitions(skill_entries)
    try:
        from utils.mcp_runtime import get_mcp_tool_definitions

        all_mcp_tools = get_mcp_tool_definitions()
    except Exception:
        all_mcp_tools = []
    mcp_tools = _filter_mcp_tools(all_mcp_tools, mcp_servers)
    tool_definitions: list[dict[str, Any]] = []
    tool_definitions.extend(core_tools)
    tool_definitions.extend(skill_tools)
    tool_definitions.extend(mcp_tools)
    tool_definitions.append(get_report_to_main_tool_definition())

    # 5. 构造 system prompt
    system_prompt = _build_subagent_system_prompt(
        subagent_name=subagent_name,
        user_system_prompt=entry.system_prompt,
        skills_context=skills_context,
        task=task,
        context=context,
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    execution.status = "running"
    _update_event(execution, "子 Agent 已启动")
    await _emit(on_event, execution)

    watchdog_task = asyncio.create_task(_stalled_watchdog(execution, on_event))

    try:
        result = await asyncio.wait_for(
            _run_subagent_loop(
                execution=execution,
                messages=messages,
                tool_definitions=tool_definitions,
                skill_tool_table=skill_tool_table,
                base_url=base_url,
                api_key=api_key,
                real_model=real_model,
                work_dir=work_dir,
                cancel_event=cancel_event,
                on_event=on_event,
                sub_logger=sub_logger,
            ),
            timeout=SUBAGENT_TOTAL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        execution.status = "timeout"
        execution.error = f"子 Agent 执行超时（>{int(SUBAGENT_TOTAL_TIMEOUT)}s）"
        sub_logger.write_error_event("timeout", execution.error)
        result = {
            "error": execution.error,
            "status": "timeout",
            "log_path": execution.log_path,
        }
    except asyncio.CancelledError:
        execution.status = "cancelled"
        execution.error = "用户取消了子 Agent 任务"
        sub_logger.write_error_event("cancelled", execution.error)
        # 不再 raise：返回带 log_path 的正常结果，让调用方拿到日志路径
        result = {
            "error": execution.error,
            "status": "cancelled",
            "log_path": execution.log_path,
        }
    except Exception as exc:
        execution.status = "failed"
        execution.error = f"子 Agent 内部异常：{exc}"
        sub_logger.write_error_event("exception", str(exc))
        result = {
            "error": execution.error,
            "status": "failed",
            "log_path": execution.log_path,
        }
    finally:
        execution.finished_at = time.time()
        watchdog_task.cancel()
        try:
            await watchdog_task
        except (asyncio.CancelledError, Exception):
            pass
        sub_logger.finalize()
        await _emit(on_event, execution)
        # 注销取消事件（任务已结束）
        unregister_cancel_event(task_id)

    return result


async def _run_subagent_loop(
    *,
    execution: SubagentExecution,
    messages: list[dict[str, Any]],
    tool_definitions: list[dict[str, Any]],
    skill_tool_table: dict[str, Any],
    base_url: str,
    api_key: str,
    real_model: str,
    work_dir: str | None,
    cancel_event: asyncio.Event | None,
    on_event: EventEmitter | None,
    sub_logger: SessionLogger,
) -> dict[str, Any]:
    """子 Agent 的多轮工具循环（精简版）。"""
    from utils.skills_manager import execute_tool as execute_global_tool

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    timeout = httpx.Timeout(
        connect=SUBAGENT_LLM_CONNECT_TIMEOUT,
        read=SUBAGENT_LLM_READ_TIMEOUT,
        write=SUBAGENT_LLM_WRITE_TIMEOUT,
        pool=30.0,
    )
    normalized_base = normalize_base_url(base_url)

    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        for round_no in range(1, SUBAGENT_MAX_ROUNDS + 1):
            if cancel_event and cancel_event.is_set():
                execution.status = "cancelled"
                execution.error = "用户取消了子 Agent 任务"
                return {
                    "error": execution.error,
                    "status": "cancelled",
                    "log_path": execution.log_path,
                }

            execution.rounds = round_no
            _update_event(execution, f"第 {round_no} 轮思考")
            await _emit(on_event, execution)

            payload: dict[str, Any] = {
                "model": real_model,
                "messages": messages,
                "stream": True,
                "tools": tool_definitions,
                "tool_choice": "auto",
            }

            full_content = ""
            tool_calls_buffer: list[dict[str, Any]] = []

            try:
                async with client.stream(
                    "POST",
                    f"{normalized_base}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        text = await response.aread()
                        msg = text.decode(errors="ignore")
                        execution.status = "failed"
                        execution.error = f"模型 API 错误：{response.status_code} {msg[:200]}"
                        sub_logger.write_error_event("api_error", execution.error)
                        return {
                            "error": execution.error,
                            "status": "failed",
                            "log_path": execution.log_path,
                        }

                    async for line in response.aiter_lines():
                        if cancel_event and cancel_event.is_set():
                            execution.status = "cancelled"
                            execution.error = "用户取消了子 Agent 任务"
                            return {
                                "error": execution.error,
                                "status": "cancelled",
                                "log_path": execution.log_path,
                            }
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        usage = extract_usage_from_stream_chunk(chunk)
                        if usage:
                            sub_logger.add_token_usage(usage)

                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {}) or {}
                        finish_reason = choices[0].get("finish_reason")

                        if delta.get("tool_calls"):
                            for tc_delta in delta["tool_calls"]:
                                idx = tc_delta.get("index", 0)
                                while len(tool_calls_buffer) <= idx:
                                    tool_calls_buffer.append({
                                        "id": "",
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    })
                                tc = tool_calls_buffer[idx]
                                if tc_delta.get("id"):
                                    tc["id"] = tc_delta["id"]
                                fn = tc_delta.get("function") or {}
                                if fn.get("name"):
                                    tc["function"]["name"] = fn["name"]
                                if fn.get("arguments"):
                                    tc["function"]["arguments"] += fn["arguments"]
                            continue

                        if delta.get("reasoning_content"):
                            sub_logger.append_reasoning_delta(delta["reasoning_content"])
                            if on_event is not None:
                                try:
                                    await on_event({
                                        "subagent_reasoning": {
                                            "task_id": execution.task_id,
                                            "subagent": execution.subagent_name,
                                            "delta": delta["reasoning_content"],
                                        }
                                    })
                                except Exception:
                                    pass
                            continue

                        if delta.get("content"):
                            content = delta["content"]
                            full_content += content
                            sub_logger.record_assistant_content(content)
                            if on_event is not None:
                                try:
                                    await on_event({
                                        "subagent_content": {
                                            "task_id": execution.task_id,
                                            "subagent": execution.subagent_name,
                                            "delta": content,
                                        }
                                    })
                                except Exception:
                                    pass

                        if finish_reason in ("tool_calls", "stop"):
                            break
            except httpx.TimeoutException:
                execution.status = "failed"
                execution.error = f"模型 API 读取超时（>{int(SUBAGENT_LLM_READ_TIMEOUT)}s）"
                sub_logger.write_error_event("timeout", execution.error)
                return {
                    "error": execution.error,
                    "status": "failed",
                    "log_path": execution.log_path,
                }
            except httpx.HTTPError as exc:
                execution.status = "failed"
                execution.error = f"模型 API 请求失败：{exc}"
                sub_logger.write_error_event("http_error", str(exc))
                return {
                    "error": execution.error,
                    "status": "failed",
                    "log_path": execution.log_path,
                }

            # 没有工具调用 → 但子 Agent 必须用 report_to_main 终止，否则视为失败
            if not tool_calls_buffer:
                sub_logger.flush_assistant_round()
                execution.status = "failed"
                execution.error = (
                    f"子 Agent 未通过 {REPORT_TOOL_NAME} 提交结果（直接输出了纯文本）"
                )
                sub_logger.write_error_event("no_report", execution.error)
                return {
                    "error": execution.error,
                    "status": "failed",
                    "log_path": execution.log_path,
                    "partial_output": full_content[:1000],
                }

            sub_logger.flush_assistant_round()

            # 执行所有工具调用
            messages.append({
                "role": "assistant",
                "content": full_content if full_content else None,
                "tool_calls": tool_calls_buffer,
            })

            for tc in tool_calls_buffer:
                tool_name = tc.get("function", {}).get("name", "")
                tool_id = tc.get("id") or f"sub_{round_no}_{uuid.uuid4().hex[:6]}"
                args_str = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    args = {}

                # 拦截 report_to_main：立即终止
                if tool_name == REPORT_TOOL_NAME:
                    sub_logger.write_tool_call(tool_id, tool_name, args)
                    if on_event is not None:
                        try:
                            await on_event({
                                "subagent_tool_call": {
                                    "task_id": execution.task_id,
                                    "subagent": execution.subagent_name,
                                    "tool_call_id": tool_id,
                                    "tool_name": tool_name,
                                    "args": args,
                                    "status": "running",
                                    "round": round_no,
                                }
                            })
                        except Exception:
                            pass
                    message = str(args.get("message") or "").strip()
                    success_flag = bool(args.get("success", True))
                    execution.final_output = message
                    sub_logger.write_tool_result(
                        tool_id, tool_name,
                        "completed",
                        result=json.dumps({"received": True}, ensure_ascii=False),
                    )
                    if on_event is not None:
                        try:
                            await on_event({
                                "subagent_tool_result": {
                                    "task_id": execution.task_id,
                                    "subagent": execution.subagent_name,
                                    "tool_call_id": tool_id,
                                    "tool_name": tool_name,
                                    "status": "completed",
                                    "output": message,
                                    "round": round_no,
                                }
                            })
                        except Exception:
                            pass
                    _update_event(execution, "子 Agent 已提交结果")
                    if success_flag and message:
                        execution.status = "success"
                        return {
                            "result": message,
                            "log_path": execution.log_path,
                        }
                    else:
                        execution.status = "failed"
                        execution.error = message or "子 Agent 报告任务失败"
                        return {
                            "error": execution.error,
                            "status": "failed",
                            "log_path": execution.log_path,
                        }

                # 安全防递归：禁止 delegate_to_subagent / capability_search
                if tool_name in ("delegate_to_subagent", "capability_search"):
                    sub_logger.write_tool_call(tool_id, tool_name, args)
                    if on_event is not None:
                        try:
                            await on_event({
                                "subagent_tool_call": {
                                    "task_id": execution.task_id,
                                    "subagent": execution.subagent_name,
                                    "tool_call_id": tool_id,
                                    "tool_name": tool_name,
                                    "args": args,
                                    "status": "running",
                                    "round": round_no,
                                }
                            })
                        except Exception:
                            pass
                    blocked = {
                        "success": False,
                        "error": f"子 Agent 不允许调用 {tool_name}",
                        "output": f"子 Agent 不允许调用 {tool_name}（防递归）",
                    }
                    sub_logger.write_tool_result(
                        tool_id, tool_name, "error",
                        result=json.dumps(blocked, ensure_ascii=False),
                        error=blocked["error"],
                    )
                    if on_event is not None:
                        try:
                            await on_event({
                                "subagent_tool_result": {
                                    "task_id": execution.task_id,
                                    "subagent": execution.subagent_name,
                                    "tool_call_id": tool_id,
                                    "tool_name": tool_name,
                                    "status": "error",
                                    "output": blocked["output"],
                                    "error": blocked["error"],
                                    "round": round_no,
                                }
                            })
                        except Exception:
                            pass
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": json.dumps(blocked, ensure_ascii=False),
                    })
                    continue

                _update_event(execution, f"正在调用工具 {tool_name}")
                await _emit(on_event, execution)
                sub_logger.write_tool_call(tool_id, tool_name, args)
                if on_event is not None:
                    try:
                        await on_event({
                            "subagent_tool_call": {
                                "task_id": execution.task_id,
                                "subagent": execution.subagent_name,
                                "tool_call_id": tool_id,
                                "tool_name": tool_name,
                                "args": args,
                                "status": "running",
                                "round": round_no,
                            }
                        })
                    except Exception:
                        pass

                # 执行优先级：
                # 1. skill_tool_table：子 Agent 强制激活的 skill 工具（跨 available/unavailable）
                # 2. execute_global_tool：核心工具 + MCP 工具（走全局 enabled 路径）
                loop = asyncio.get_running_loop()
                invocation_id = f"sub_agent:{execution.task_id}:{tool_id}"
                skill_mod = skill_tool_table.get(tool_name)
                try:
                    if skill_mod is not None:
                        # 子 Agent 专属路径，不走 skills_manager.execute_tool
                        tool_result = await asyncio.wait_for(
                            loop.run_in_executor(
                                None,
                                lambda m=skill_mod, tn=tool_name, a=args: _execute_skill_tool(m, tn, a),
                            ),
                            timeout=SUBAGENT_TOOL_TIMEOUT,
                        )
                    else:
                        tool_result = await asyncio.wait_for(
                            loop.run_in_executor(
                                None,
                                lambda tn=tool_name, a=args, wd=work_dir, iid=invocation_id: execute_global_tool(
                                    tn, a, work_dir=wd, session_id=execution.task_id, invocation_id=iid
                                ),
                            ),
                            timeout=SUBAGENT_TOOL_TIMEOUT,
                        )
                except asyncio.TimeoutError:
                    tool_result = {
                        "success": False,
                        "error": "tool_timeout",
                        "output": f"工具 {tool_name} 执行超时（>{int(SUBAGENT_TOOL_TIMEOUT)}s）",
                    }
                except Exception as exc:
                    tool_result = {
                        "success": False,
                        "error": str(exc),
                        "output": f"工具 {tool_name} 异常：{exc}",
                    }

                status = "completed"
                err_msg = ""
                if isinstance(tool_result, dict) and tool_result.get("error"):
                    status = "error"
                    err_msg = str(tool_result.get("error"))

                sub_logger.write_tool_result(
                    tool_id, tool_name, status,
                    result=json.dumps(tool_result, ensure_ascii=False)
                        if isinstance(tool_result, dict) else str(tool_result),
                    error=err_msg,
                )
                _update_event(execution, f"工具 {tool_name} 已完成")
                await _emit(on_event, execution)
                if on_event is not None:
                    try:
                        await on_event({
                            "subagent_tool_result": {
                                "task_id": execution.task_id,
                                "subagent": execution.subagent_name,
                                "tool_call_id": tool_id,
                                "tool_name": tool_name,
                                "status": status,
                                "output": (tool_result.get("output") if isinstance(tool_result, dict) else str(tool_result)) or "",
                                "error": err_msg,
                                "round": round_no,
                            }
                        })
                    except Exception:
                        pass

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": json.dumps(tool_result, ensure_ascii=False)
                        if isinstance(tool_result, dict) else str(tool_result),
                })

        # 跑完 MAX_ROUNDS 仍未 report_to_main → 失败
        execution.status = "failed"
        execution.error = f"子 Agent 达到最大轮数 {SUBAGENT_MAX_ROUNDS} 仍未调用 {REPORT_TOOL_NAME}"
        sub_logger.write_error_event("max_rounds", execution.error)
        return {
            "error": execution.error,
            "status": "failed",
            "log_path": execution.log_path,
        }
