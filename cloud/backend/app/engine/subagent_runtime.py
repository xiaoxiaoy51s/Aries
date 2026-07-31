"""Subagent Runtime - 子 Agent 执行引擎（cloud 多租户）。

- 同步等待 + 流式状态推送
- 子 Agent 通过 report_to_main 回传结果；未提交视为失败
- 日志按用户邮箱隔离：~/.Aries/{email}/session/sub_agent/...
- 禁止子 Agent 再调用 delegate_to_subagent（防递归）
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

from app.utils.session_logger import SessionLogger, get_subagent_jsonl_path
from app.utils.token_counter import normalize_api_usage

logger = logging.getLogger(__name__)

SUBAGENT_MAX_ROUNDS = 50
SUBAGENT_TOTAL_TIMEOUT = 1800.0
SUBAGENT_LLM_READ_TIMEOUT = 900.0
SUBAGENT_LLM_CONNECT_TIMEOUT = 30.0
SUBAGENT_LLM_WRITE_TIMEOUT = 120.0
SUBAGENT_TOOL_TIMEOUT = 600.0
SUBAGENT_IDLE_WARN_THRESHOLD = 60.0

REPORT_TOOL_NAME = "report_to_main"
DELEGATE_TOOL_NAME = "delegate_to_subagent"

EventEmitter = Callable[[dict[str, Any]], Awaitable[None]]

_CANCEL_REGISTRY: dict[str, asyncio.Event] = {}


def register_cancel_event(task_id: str, event: asyncio.Event) -> None:
    _CANCEL_REGISTRY[task_id] = event


def unregister_cancel_event(task_id: str) -> None:
    _CANCEL_REGISTRY.pop(task_id, None)


def cancel_subagent(task_id: str) -> bool:
    event = _CANCEL_REGISTRY.get(task_id)
    if event is None:
        return False
    event.set()
    return True


def list_running_subagents() -> list[str]:
    return list(_CANCEL_REGISTRY.keys())


@dataclass
class SubagentExecution:
    task_id: str
    subagent_name: str
    task: str
    user_email: str = ""
    status: str = "pending"
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
        payload: dict[str, Any] = {
            "task_id": self.task_id,
            "subagent": self.subagent_name,
            "task": self.task,
            "status": self.status,
            "round": self.rounds,
            "last_event": self.last_event,
            "last_event_at": self.last_event_at,
            "elapsed_ms": self.elapsed_ms(),
            "log_path": self.log_path,
            "user_email": self.user_email,
        }
        if self.error:
            payload["error"] = self.error
        if self.final_output:
            payload["final_message"] = self.final_output
        return payload


def get_report_to_main_tool_definition() -> dict[str, Any]:
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
                        "description": "给主 Agent 的简要总结（建议不超过 1200 字）。",
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


def format_subagent_result_for_main(sub_result: dict[str, Any]) -> str:
    if sub_result.get("result"):
        return str(sub_result["result"])
    status = str(sub_result.get("status") or "failed")
    error = str(sub_result.get("error") or "").strip()
    partial = str(sub_result.get("partial_output") or "").strip()
    log_path = str(sub_result.get("log_path") or "").strip()
    lines: list[str] = []
    if status == "cancelled":
        lines.append("【子 Agent 已取消】任务被用户或系统中止。")
    elif status == "timeout":
        lines.append("【子 Agent 超时】任务未在时限内完成。")
    else:
        lines.append("【子 Agent 失败】任务未能成功完成。")
    if error:
        lines.append(f"原因：{error}")
    if partial:
        lines.append(f"部分输出：{partial[:800]}")
    if log_path:
        lines.append(f"详细日志：{log_path}")
    lines.append("请根据以上信息向用户说明情况，并决定是否需要调整任务后重试或换用其他方案。")
    return "\n".join(lines)


def _build_subagent_system_prompt(
    *,
    subagent_name: str,
    user_system_prompt: str,
    task: str,
    context: str,
    skills_context: str = "",
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    parts = [
        f"# 你的身份\n"
        f"你是被主 Agent 委派的子 Agent：`{subagent_name}`。"
        f"今天的日期是 {today}，当前操作系统：{platform.system()}。\n"
    ]
    if user_system_prompt.strip():
        parts.append(f"# 详细职责\n{user_system_prompt.strip()}\n")
    if skills_context.strip():
        parts.append(skills_context.strip())
    parts.append(
        "# 任务通信规则\n"
        "- 你看不到主 Agent 与用户的对话历史，下方 task 已包含完成任务所需的全部信息\n"
        f"- 任务完成（或确定无法完成）时，必须调用 `{REPORT_TOOL_NAME}` 工具提交简要总结\n"
        f"- 在调用 `{REPORT_TOOL_NAME}` 之前，所有思考和工具调用都不会被主 Agent 看到\n"
        f"- 不要在 message 中重复中间过程，只保留对主 Agent 决策有价值的结论（建议 ≤500 字）\n"
        f"- 如果任务无法完成，也要调用 `{REPORT_TOOL_NAME}` 并在 message 中说明原因，success=false\n"
    )
    if context.strip():
        parts.append(f"# 主 Agent 提供的额外上下文\n{context.strip()}\n")
    parts.append(f"# 本次任务\n{task.strip()}")
    return "\n\n".join(parts)


def _build_core_tool_definitions() -> list[dict[str, Any]]:
    """主工具集，排除 delegate_to_subagent 防递归。"""
    from app.tools.registry import get_tool_schemas

    return [
        s for s in get_tool_schemas()
        if s.get("function", {}).get("name") != DELEGATE_TOOL_NAME
    ]


async def _resolve_model(user_email: str, model_name: str = ""):
    from app.service.model_config_service import ModelConfigService

    active = await ModelConfigService.get_active_model(user_email)
    if model_name and model_name.strip():
        # 优先匹配配置的 model 字段；找不到则回退 active
        try:
            models = await ModelConfigService.list_models(user_email)
            for m in models or []:
                if getattr(m, "model", None) == model_name:
                    return m
        except Exception:
            pass
    return active


def _update_event(execution: SubagentExecution, label: str) -> None:
    execution.last_event = label
    execution.last_event_at = time.time()


async def _emit(emitter: EventEmitter | None, execution: SubagentExecution) -> None:
    if emitter is None:
        return
    try:
        await emitter({"type": "subagent_event", "data": execution.to_event_dict()})
    except Exception as exc:
        logger.debug("emitter 推送失败: %s", exc)


async def _fail_subagent_loop(
    execution: SubagentExecution,
    *,
    error: str,
    status: str = "failed",
    sub_logger: SessionLogger | None = None,
    on_event: EventEmitter | None = None,
    error_type: str = "subagent_failed",
    partial_output: str = "",
) -> dict[str, Any]:
    execution.status = status
    execution.error = error
    if partial_output:
        execution.final_output = partial_output[:1000]
    if sub_logger is not None:
        sub_logger.write_error_event(error_type, error)
    _update_event(execution, error)
    await _emit(on_event, execution)
    result: dict[str, Any] = {
        "error": error,
        "status": status,
        "log_path": execution.log_path,
    }
    if partial_output:
        result["partial_output"] = partial_output[:1000]
    return result


async def _stalled_watchdog(execution: SubagentExecution, emitter: EventEmitter | None) -> None:
    while execution.status in ("pending", "running", "stalled"):
        await asyncio.sleep(5)
        if execution.status not in ("pending", "running", "stalled"):
            return
        idle = time.time() - execution.last_event_at
        if idle >= SUBAGENT_IDLE_WARN_THRESHOLD:
            if execution.status != "stalled":
                execution.status = "stalled"
                await _emit(emitter, execution)
        elif execution.status == "stalled":
            execution.status = "running"
            await _emit(emitter, execution)


async def run_subagent(
    *,
    subagent_name: str,
    task: str,
    user_email: str,
    context: str = "",
    cancel_event: asyncio.Event | None = None,
    on_event: EventEmitter | None = None,
    session_id: str | None = None,
    parent_tool_call_id: str | None = None,
    user_id: int | None = None,
    workspace_dir: str = "default",
) -> dict[str, Any]:
    """执行一次子 Agent 任务。日志写入 ~/.Aries/{user_email}/session/sub_agent/..."""
    task_id = f"sa-{uuid.uuid4().hex[:8]}"
    execution = SubagentExecution(
        task_id=task_id,
        subagent_name=subagent_name,
        task=task,
        user_email=user_email,
        status="pending",
    )

    if cancel_event is None:
        cancel_event = asyncio.Event()
    register_cancel_event(task_id, cancel_event)

    try:
        from app.engine.subagent_manager import build_subagent_runtime

        runtime = build_subagent_runtime(subagent_name, email=user_email)
    except ValueError as exc:
        execution.status = "failed"
        execution.error = str(exc)
        execution.finished_at = time.time()
        await _emit(on_event, execution)
        unregister_cancel_event(task_id)
        return {"error": str(exc), "status": "failed", "log_path": ""}

    entry = runtime["entry"]
    model_name = runtime["effective_model"]

    model = await _resolve_model(user_email, model_name)
    if not model or not getattr(model, "baseUrl", None) or not getattr(model, "apiKey", None):
        execution.status = "failed"
        execution.error = "无法解析子 Agent 的模型凭证（请先在设置中配置并激活模型）"
        execution.finished_at = time.time()
        await _emit(on_event, execution)
        unregister_cancel_event(task_id)
        return {"error": execution.error, "status": "failed", "log_path": ""}

    log_path = get_subagent_jsonl_path(user_email, task_id)
    execution.log_path = str(log_path)

    def _on_logger_event(event: dict[str, Any]) -> None:
        if on_event is None:
            return
        # 同步回调里不能 await；把关键事件塞进主 SSE 由 chat_service 的 on_event 处理
        # 这里 on_event 可能是 async；用 create_task 若有 loop
        try:
            loop = asyncio.get_running_loop()
            payload = {
                "type": "subagent_log_event",
                "data": {
                    "task_id": task_id,
                    "jsonl_path": str(log_path),
                    "tool_call_id": parent_tool_call_id or "",
                    "subagent": subagent_name,
                    "event": event,
                },
            }
            loop.create_task(on_event(payload))
        except Exception:
            pass

    sub_logger = SessionLogger(
        user_email,
        f"sub_agent_{task_id}",
        "run",
        on_event=_on_logger_event,
    )
    # 覆盖为邮箱隔离的 sub_agent 路径
    try:
        sub_logger._file.close()
    except Exception:
        pass
    sub_logger.path = log_path
    sub_logger._file = open(log_path, "a", encoding="utf-8")
    sub_logger.set_model(model.model)

    if on_event is not None:
        try:
            await on_event({
                "type": "subagent_log_started",
                "data": {
                    "task_id": task_id,
                    "jsonl_path": str(log_path),
                    "tool_call_id": parent_tool_call_id or "",
                    "subagent": subagent_name,
                },
            })
        except Exception:
            pass

    tool_definitions = _build_core_tool_definitions()
    tool_definitions.append(get_report_to_main_tool_definition())

    system_prompt = _build_subagent_system_prompt(
        subagent_name=subagent_name,
        user_system_prompt=entry.system_prompt,
        task=task,
        context=context,
        skills_context=runtime.get("skills_context") or "",
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    execution.status = "running"
    _update_event(execution, "子 Agent 已启动")
    await _emit(on_event, execution)

    watchdog_task = asyncio.create_task(_stalled_watchdog(execution, on_event))
    tool_context = {
        "user_email": user_email,
        "session_id": session_id or f"sub_agent_{task_id}",
        "user_id": user_id,
        "workspace_dir": (workspace_dir or "default").strip() or "default",
    }

    try:
        result = await asyncio.wait_for(
            _run_subagent_loop(
                execution=execution,
                messages=messages,
                tool_definitions=tool_definitions,
                base_url=model.baseUrl.rstrip("/"),
                api_key=model.apiKey,
                real_model=model.model,
                cancel_event=cancel_event,
                on_event=on_event,
                sub_logger=sub_logger,
                tool_context=tool_context,
            ),
            timeout=SUBAGENT_TOTAL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        execution.status = "timeout"
        execution.error = f"子 Agent 执行超时（>{int(SUBAGENT_TOTAL_TIMEOUT)}s）"
        sub_logger.write_error_event("timeout", execution.error)
        result = {"error": execution.error, "status": "timeout", "log_path": execution.log_path}
    except asyncio.CancelledError:
        execution.status = "cancelled"
        execution.error = "用户取消了子 Agent 任务"
        sub_logger.write_error_event("cancelled", execution.error)
        result = {"error": execution.error, "status": "cancelled", "log_path": execution.log_path}
    except Exception as exc:
        execution.status = "failed"
        execution.error = f"子 Agent 内部异常：{exc}"
        sub_logger.write_error_event("exception", str(exc))
        result = {"error": execution.error, "status": "failed", "log_path": execution.log_path}
    finally:
        execution.finished_at = time.time()
        watchdog_task.cancel()
        try:
            await watchdog_task
        except (asyncio.CancelledError, Exception):
            pass
        duration_ms = execution.elapsed_ms()
        sub_logger.finalize(duration_ms=duration_ms)
        await _emit(on_event, execution)
        unregister_cancel_event(task_id)

    return result


async def _run_subagent_loop(
    *,
    execution: SubagentExecution,
    messages: list[dict[str, Any]],
    tool_definitions: list[dict[str, Any]],
    base_url: str,
    api_key: str,
    real_model: str,
    cancel_event: asyncio.Event | None,
    on_event: EventEmitter | None,
    sub_logger: SessionLogger,
    tool_context: dict[str, Any],
) -> dict[str, Any]:
    from app.tools.registry import execute_tool, parse_tool_arguments

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

    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        for round_no in range(1, SUBAGENT_MAX_ROUNDS + 1):
            if cancel_event and cancel_event.is_set():
                return await _fail_subagent_loop(
                    execution,
                    error="用户取消了子 Agent 任务",
                    status="cancelled",
                    sub_logger=sub_logger,
                    on_event=on_event,
                    error_type="cancelled",
                )

            execution.rounds = round_no
            _update_event(execution, f"第 {round_no} 轮思考")
            await _emit(on_event, execution)

            if round_no == SUBAGENT_MAX_ROUNDS - 1:
                messages.append({
                    "role": "system",
                    "content": (
                        f"【系统提醒】你已接近子 Agent 工具调用轮数上限（{SUBAGENT_MAX_ROUNDS} 轮）。"
                        f"本轮必须调用 `{REPORT_TOOL_NAME}` 向主 Agent 汇报；"
                        "如无法完成也需说明原因（success=false）。"
                    ),
                })

            payload: dict[str, Any] = {
                "model": real_model,
                "messages": messages,
                "stream": True,
                "stream_options": {"include_usage": True},
                "tools": tool_definitions,
                "tool_choice": "auto",
            }

            full_content = ""
            tool_calls_acc: dict[int, dict] = {}

            try:
                async with client.stream(
                    "POST",
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        text = await response.aread()
                        msg = text.decode(errors="ignore")
                        return await _fail_subagent_loop(
                            execution,
                            error=f"模型 API 错误：{response.status_code} {msg[:200]}",
                            status="failed",
                            sub_logger=sub_logger,
                            on_event=on_event,
                            error_type="api_error",
                        )

                    async for line in response.aiter_lines():
                        if cancel_event and cancel_event.is_set():
                            return await _fail_subagent_loop(
                                execution,
                                error="用户取消了子 Agent 任务",
                                status="cancelled",
                                sub_logger=sub_logger,
                                on_event=on_event,
                                error_type="cancelled",
                            )
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        usage = chunk.get("usage")
                        if usage:
                            sub_logger.add_token_usage(normalize_api_usage(usage))

                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {}) or {}

                        if delta.get("tool_calls"):
                            for tc_delta in delta["tool_calls"]:
                                idx = tc_delta.get("index", 0)
                                if idx not in tool_calls_acc:
                                    tool_calls_acc[idx] = {
                                        "id": "",
                                        "name": "",
                                        "arguments": "",
                                    }
                                tc = tool_calls_acc[idx]
                                if tc_delta.get("id"):
                                    tc["id"] = tc_delta["id"]
                                fn = tc_delta.get("function") or {}
                                if fn.get("name"):
                                    tc["name"] = fn["name"]
                                if fn.get("arguments"):
                                    tc["arguments"] += fn["arguments"]
                            continue

                        if delta.get("reasoning_content"):
                            sub_logger.append_reasoning_delta(delta["reasoning_content"])
                            continue

                        if delta.get("content"):
                            content = delta["content"]
                            full_content += content
                            sub_logger.record_assistant_content(content)

            except httpx.TimeoutException:
                return await _fail_subagent_loop(
                    execution,
                    error=f"模型 API 读取超时（>{int(SUBAGENT_LLM_READ_TIMEOUT)}s）",
                    status="failed",
                    sub_logger=sub_logger,
                    on_event=on_event,
                    error_type="timeout",
                )
            except httpx.HTTPError as exc:
                return await _fail_subagent_loop(
                    execution,
                    error=f"模型 API 请求失败：{exc}",
                    status="failed",
                    sub_logger=sub_logger,
                    on_event=on_event,
                    error_type="http_error",
                )

            tool_calls_buffer = [
                {
                    "id": tool_calls_acc[k]["id"] or f"sub_{round_no}_{uuid.uuid4().hex[:6]}",
                    "type": "function",
                    "function": {
                        "name": tool_calls_acc[k]["name"],
                        "arguments": tool_calls_acc[k]["arguments"],
                    },
                }
                for k in sorted(tool_calls_acc.keys())
            ]

            if not tool_calls_buffer:
                sub_logger.flush_assistant_round()
                return await _fail_subagent_loop(
                    execution,
                    error=f"子 Agent 未通过 {REPORT_TOOL_NAME} 提交结果（直接输出了纯文本）",
                    status="failed",
                    sub_logger=sub_logger,
                    on_event=on_event,
                    error_type="no_report",
                    partial_output=full_content[:1000],
                )

            sub_logger.flush_assistant_round()
            messages.append({
                "role": "assistant",
                "content": full_content if full_content else None,
                "tool_calls": tool_calls_buffer,
            })

            for tc in tool_calls_buffer:
                tool_name = tc.get("function", {}).get("name", "")
                tool_id = tc.get("id")
                args = parse_tool_arguments(tc.get("function", {}).get("arguments", "{}"))

                if tool_name == REPORT_TOOL_NAME:
                    sub_logger.write_tool_call(tool_id, tool_name, args)
                    message = str(args.get("message") or "").strip()
                    success_flag = bool(args.get("success", True))
                    execution.final_output = message
                    sub_logger.write_tool_result(
                        tool_id, tool_name,
                        json.dumps({"received": True}, ensure_ascii=False),
                    )
                    _update_event(execution, "子 Agent 已提交结果")
                    if success_flag and message:
                        execution.status = "success"
                        return {"result": message, "log_path": execution.log_path}
                    execution.status = "failed"
                    execution.error = message or "子 Agent 报告任务失败"
                    return {
                        "error": execution.error,
                        "status": "failed",
                        "log_path": execution.log_path,
                    }

                if tool_name == DELEGATE_TOOL_NAME:
                    blocked = f"子 Agent 不允许调用 {tool_name}（防递归）"
                    sub_logger.write_tool_call(tool_id, tool_name, args)
                    sub_logger.write_tool_result(tool_id, tool_name, blocked, error=blocked)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": blocked,
                    })
                    continue

                _update_event(execution, f"正在调用工具 {tool_name}")
                await _emit(on_event, execution)
                sub_logger.write_tool_call(tool_id, tool_name, args)

                try:
                    tool_result = await asyncio.wait_for(
                        execute_tool(tool_name, args, context=tool_context),
                        timeout=SUBAGENT_TOOL_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    tool_result = f"工具 {tool_name} 执行超时（>{int(SUBAGENT_TOOL_TIMEOUT)}s）"
                except Exception as exc:
                    tool_result = f"工具 {tool_name} 异常：{exc}"

                sub_logger.write_tool_result(tool_id, tool_name, str(tool_result))
                _update_event(execution, f"工具 {tool_name} 已完成")
                await _emit(on_event, execution)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": str(tool_result),
                })

        return await _fail_subagent_loop(
            execution,
            error=f"子 Agent 达到最大轮数上限（{SUBAGENT_MAX_ROUNDS}）且未调用 {REPORT_TOOL_NAME}",
            status="failed",
            sub_logger=sub_logger,
            on_event=on_event,
            error_type="max_rounds",
        )
