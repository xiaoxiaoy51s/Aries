"""主流式 Agent 逻辑：多轮工具调用、子 Agent 并行委派、实时上下文压缩。"""
import json
import asyncio
import httpx
from typing import AsyncGenerator, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from services.platform_segment import PlatformStreamSink

from utils.url_utils import normalize_base_url
from utils.network_manager import get_httpx_proxy_for_url
from utils.message_snapshot import (
    create_assistant_snapshot,
    set_summary_block,
    finalize_snapshot,
)
from utils.session_logger import SessionLogger
from utils.token_counter import extract_usage_from_stream_chunk
from utils.prompt_cache import (
    build_layered_messages,
    compute_config_fingerprint,
    is_prompt_cache_enabled,
    prepare_llm_payload,
    summarize_cache_usage,
)
from db.chat import save_message, update_message

from .stream_constants import (
    REPEAT_TOOL_LIMIT,
    LLM_CONNECT_TIMEOUT_SECONDS,
    LLM_READ_TIMEOUT_SECONDS,
    LLM_WRITE_TIMEOUT_SECONDS,
    _HINT_PREFIXES,
)
from .todo_handler import get_todos, format_todos_for_context, purge_todo_messages
from .system_prompt import build_agent_system_prompt_parts, get_agent_skills_and_tools
from .tool_runner import run_single_tool, run_delegate_items, build_tool_result_event, is_parallel_safe
from utils.terminal_output import format_tool_result_for_model
from utils.tool_result_image import split_tool_result_image, tool_result_for_logging
from prompt.agent_prompts import filter_tools_for_agent as _filter_tools_for_agent_mode
from api.chat.agent_modes import build_agent_mode_context as _build_agent_mode_context


async def _should_stop_stream(
    cancel_event: Optional[asyncio.Event],
    disconnect_check: Optional[Any],
) -> bool:
    if cancel_event and cancel_event.is_set():
        return True
    if disconnect_check:
        try:
            if await disconnect_check():
                return True
        except Exception:
            pass
    return False


def _pop_limit_hint_message(messages: list[dict[str, Any]]) -> None:
    """移除临时追加的系统提示（工具上限/重复检测），避免污染会话历史。"""
    if messages and messages[-1].get("role") == "system":
        content = messages[-1].get("content", "")
        if isinstance(content, str) and any(content.startswith(p) for p in _HINT_PREFIXES):
            messages.pop()


def _strip_image_base64(tr: dict) -> tuple[dict, str]:
    """构建 tool 角色消息，并剥离 image_base64。

    返回 (tool_message, image_base64)。
    image_base64 为空字符串表示无图片。
    tool 消息的 content 始终为纯文本字符串（兼容所有 API）。
    """
    content = tr.get("content", "")
    slim, image_b64 = split_tool_result_image(content if isinstance(content, str) else "")
    return {"role": "tool", "tool_call_id": tr["tool_call_id"], "content": slim}, image_b64


def _format_llm_api_error(raw: str) -> str:
    """从模型网关原始错误体中提取可读说明。"""
    text = (raw or "").strip()
    if not text:
        return "模型 API 返回未知错误"

    try:
        outer = json.loads(text)
    except json.JSONDecodeError:
        return text[:2000]

    if not isinstance(outer, dict):
        return text[:2000]

    err = outer.get("error")
    if isinstance(err, str):
        return err[:2000]
    if isinstance(err, dict):
        message = str(err.get("message") or err.get("detail") or "").strip()
        if message:
            try:
                inner = json.loads(message)
                if isinstance(inner, dict):
                    inner_err = inner.get("error")
                    if isinstance(inner_err, str) and inner_err.strip():
                        return inner_err.strip()[:2000]
            except json.JSONDecodeError:
                pass
            return message[:2000]
        code = err.get("code")
        err_type = err.get("type")
        if code or err_type:
            return f"{err_type or 'API error'} ({code})"

    detail = outer.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()[:2000]
    return text[:2000]


def _sanitize_tool_calls_for_messages(tool_calls_buffer: list) -> list:
    """确保写入下一轮 messages 的 tool_calls.arguments 均为合法 JSON 字符串。"""
    sanitized: list = []
    for tc in tool_calls_buffer or []:
        tc_copy = json.loads(json.dumps(tc, ensure_ascii=False))
        func = tc_copy.get("function") or {}
        args_str = func.get("arguments") or "{}"
        if not isinstance(args_str, str):
            args_str = json.dumps(args_str, ensure_ascii=False)
        try:
            parsed = json.loads(args_str) if args_str.strip() else {}
            if not isinstance(parsed, dict):
                parsed = {}
        except json.JSONDecodeError:
            parsed = {}
        func["arguments"] = json.dumps(parsed, ensure_ascii=False)
        tc_copy["function"] = func
        sanitized.append(tc_copy)
    return sanitized


class _LLMStreamResult:
    """LLM 流式请求的解析结果容器。"""
    def __init__(self):
        self.full_content = ""
        self.tool_calls_buffer: list = []
        self.error_msg: str | None = None
        self.cancelled = False


async def _handle_llm_stream(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict,
    payload: dict,
    logger,
    segment_sink,
    cancel_event,
    disconnect_check,
    result: _LLMStreamResult,
) -> AsyncGenerator[bool, None]:
    """向 LLM 发起流式请求，每个 chunk 后 yield True 让调用方 drain SSE 队列。"""

    try:
        async with client.stream("POST", f"{base_url}/chat/completions", headers=headers, json=payload) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                raw_error = error_text.decode(errors="replace")
                result.error_msg = _format_llm_api_error(raw_error)
                if logger:
                    logger.write_error_event("api_error", result.error_msg, details=raw_error[:4000])
                return

            async for line in response.aiter_lines():
                if await _should_stop_stream(cancel_event, disconnect_check):
                    result.cancelled = True
                    break
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        usage = extract_usage_from_stream_chunk(chunk)
                        if usage:
                            logger.add_token_usage(usage)
                        choices = chunk.get("choices") or []
                        if not choices:
                            # 部分网关最后一包仅含 usage、无 choices
                            continue

                        delta = choices[0].get("delta", {})
                        finish_reason = choices[0].get("finish_reason")

                        if "tool_calls" in delta and delta["tool_calls"]:
                            for tc_delta in delta["tool_calls"]:
                                index = tc_delta.get("index", 0)
                                while len(result.tool_calls_buffer) <= index:
                                    result.tool_calls_buffer.append({
                                        "id": "", "type": "function",
                                        "function": {"name": "", "arguments": ""}
                                    })
                                tc = result.tool_calls_buffer[index]
                                if "id" in tc_delta and tc_delta["id"]:
                                    tc["id"] = tc_delta["id"]
                                if "function" in tc_delta:
                                    func_delta = tc_delta["function"]
                                    if "name" in func_delta and func_delta["name"]:
                                        tc["function"]["name"] = func_delta["name"]
                                    if "arguments" in func_delta and func_delta["arguments"]:
                                        tc["function"]["arguments"] += func_delta["arguments"]
                            yield True
                            continue

                        if "reasoning_content" in delta and delta["reasoning_content"]:
                            logger.append_reasoning_delta(delta["reasoning_content"])
                            yield True
                            continue

                        if "content" in delta and delta["content"]:
                            content = delta["content"]
                            result.full_content += content
                            logger.record_assistant_content(content)
                            yield True

                        # 不在 finish_reason 时 break：部分 OpenAI 兼容 API 的 usage
                        # 在 finish_reason 之后的独立 chunk 返回（无 choices），需要继续读取

                    except json.JSONDecodeError:
                        continue
    except httpx.TimeoutException:
        result.error_msg = (
            f"模型 API 读取超时（{int(LLM_READ_TIMEOUT_SECONDS)} 秒内无新数据）。"
            "常见于 Playwright 等多轮工具任务后模型响应较慢，请稍后重试或拆分任务。"
        )
        if logger:
            logger.write_error_event("timeout", result.error_msg)
    except httpx.HTTPError as exc:
        result.error_msg = f"模型 API 请求失败：{exc}"
        if logger:
            logger.write_error_event("http_error", result.error_msg)


async def stream_agent_mode(
    request,
    messages: list,
    headers: dict,
    base_payload: dict,
    session_id: str,
    work_dir: str | None = None,
    cancel_event: Optional[asyncio.Event] = None,
    disconnect_check: Optional[Any] = None,
    segment_sink: Optional["PlatformStreamSink"] = None,
    agent_mode: str | None = None,
    override_model: str | None = None,
    override_system_prompt: str | None = None,
    override_tools: list[dict[str, Any]] | None = None,
    override_agent_mode_label: str | None = None,
) -> AsyncGenerator[str, None]:
    """Agent 模式 - 支持多轮工具调用。

    当传入 override_* 参数时，进入"子 Agent 直接模式"：
    - override_model: 使用子 Agent 的专属模型
    - override_system_prompt: 使用子 Agent 的 system_prompt
    - override_tools: 使用子 Agent 的专属工具集
    """
    final_content = ""
    cancelled = False
    assistant_message_id = None
    logger = None
    snapshot = ""
    _esc_listener_started = False  # ESC 监听（Agent 流式期间全局紧急停止）
    is_subagent_mode = bool(override_system_prompt)

    # SSE 事件队列：替代 WebSocket，收集 SessionLogger 的事件并通过 SSE 推送
    _sse_queue: asyncio.Queue[dict] = asyncio.Queue()

    def _on_logger_event(event: dict) -> None:
        """SessionLogger 同步回调，将事件推入异步队列供 SSE 消费。"""
        try:
            _sse_queue.put_nowait(event)
        except Exception:
            pass

    async def _drain_sse_queue():
        """取出队列中所有事件，yield 为 SSE 格式（log_event / subagent_log_*）。"""
        while not _sse_queue.empty():
            try:
                ev = _sse_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            kind = ev.pop("__sse_kind", "log_event")
            if kind == "log_event":
                if ev.get("type") == "log_complete":
                    continue
                yield f"event: log_event\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            elif kind in ("subagent_log_started", "subagent_log_event", "subagent_log_complete"):
                yield f"event: {kind}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"

    try:
        assistant_message_id = save_message(session_id, "assistant", "", message_snapshot_json="", mode="agent")
        logger = SessionLogger(
            session_id=session_id,
            message_id=assistant_message_id,
            on_event=_on_logger_event,
        )
        effective_model = override_model or getattr(request, "model", "") or ""
        logger.set_model(effective_model)
        jsonl_path = logger.jsonl_path_str()
        # 立即将 JSONL 路径写入 DB，确保用户切回页面时能找到日志
        update_message(assistant_message_id, message_snapshot_json=jsonl_path)
        # SSE 通知前端：assistant 回复已开始
        yield f"event: log_started\ndata: {json.dumps({'session_id': session_id, 'message_id': assistant_message_id, 'jsonl_path': jsonl_path}, ensure_ascii=False)}\n\n"
        breakdown_inputs = base_payload.pop("context_breakdown_inputs", None) or {}
        base_payload.pop("context_token_info", None)
        snapshot = create_assistant_snapshot(session_id, logger)

        skills_context, tool_definitions, mcp_context, subagents_context = get_agent_skills_and_tools()
        prompt_parts = build_agent_system_prompt_parts(
            skills_context, work_dir=work_dir,
            mcp_context=mcp_context, subagents_context=subagents_context,
        )
        agent_ctx = ""
        system_prompt = prompt_parts["full"]

        if is_subagent_mode:
            # 子 Agent 直接模式：完全替换 system prompt 和工具集
            system_prompt = override_system_prompt
            prompt_parts = {
                "base": override_system_prompt,
                "full": override_system_prompt,
                "mcp": "",
                "subagents": "",
                "rules": "",
                "skills": "",
            }
            tool_definitions = override_tools or []
        else:
            # 固定 Agent 模式：过滤工具 + 追加专用 prompt（与 @code_review 逻辑一致）
            if agent_mode:
                tool_definitions = _filter_tools_for_agent_mode(tool_definitions, agent_mode)
                agent_ctx = _build_agent_mode_context(agent_mode)
                if agent_ctx:
                    system_prompt = system_prompt + agent_ctx

        prompt_fingerprint = compute_config_fingerprint(
            tool_definitions,
            prompt_parts=prompt_parts,
            model=effective_model,
        )

        # context usage breakdown
        from utils.token_counter import build_context_usage_breakdown
        model_name = effective_model
        # system_prompt_base 只含 base + mcp + subagents + plugins，
        # rules 和 skills 单独计入，避免与 full system_prompt 重复计算
        sp_base = (
            prompt_parts.get("base", "")
            + (prompt_parts.get("mcp") or "")
            + (prompt_parts.get("subagents") or "")
            + (prompt_parts.get("plugins") or "")
        )
        if agent_ctx:
            sp_base += agent_ctx
        context_breakdown = build_context_usage_breakdown(
            system_prompt_base=sp_base,
            tool_definitions=tool_definitions,
            rules_text=prompt_parts["rules"],
            skills_text=prompt_parts["skills"],
            summarized_messages=breakdown_inputs.get("summarized_messages") or [],
            conversation_messages=breakdown_inputs.get("conversation_messages") or [],
            model=model_name,
        )
        for k in ("recent_message_count", "memory_count", "reasoning_count"):
            if breakdown_inputs.get(k) is not None:
                context_breakdown[k] = breakdown_inputs[k]
        logger.set_token_usage({
            "context": context_breakdown,
            "prompt_cache": {
                "enabled": is_prompt_cache_enabled(),
                "fingerprint": prompt_fingerprint,
            },
        })
        yield f"event: stream_event\ndata: {json.dumps({'meta': logger.get_run_metadata()}, ensure_ascii=False)}\n\n"
        async for ev in _drain_sse_queue():
            yield ev

        extra_system_suffix = agent_ctx if not is_subagent_mode else ""
        intent_label = override_agent_mode_label or (f"agent:{agent_mode}" if agent_mode else "subagent")

        # ===== 意图识别 =====（固定 Agent / 子 Agent 模式下跳过）
        if not agent_mode and not is_subagent_mode:
            try:
                from prompt.edit_code_prompts import classify_intent, filter_tools_for_intent, get_prompt_for_intent, INTENT_AGENT
                user_text = ""
                for msg in reversed(messages):
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            user_text = content
                        elif isinstance(content, list):
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    user_text += part.get("text", "")
                        break
                intent = classify_intent(user_text)
                intent_label = intent
                if intent != INTENT_AGENT:
                    tool_definitions = filter_tools_for_intent(intent, tool_definitions)
                    prompt_fingerprint = compute_config_fingerprint(
                        tool_definitions,
                        prompt_parts=prompt_parts,
                        model=effective_model,
                    )
                intent_prompt = get_prompt_for_intent(intent)
                if intent_prompt:
                    extra_system_suffix += "\n\n" + intent_prompt
                yield f"event: stream_event\ndata: {json.dumps({'intent': intent}, ensure_ascii=False)}\n\n"
                async for ev in _drain_sse_queue():
                    yield ev
            except Exception:
                pass
        else:
            yield f"event: stream_event\ndata: {json.dumps({'intent': intent_label}, ensure_ascii=False)}\n\n"
            async for ev in _drain_sse_queue():
                yield ev

        if is_subagent_mode:
            messages = [m for m in messages if m.get("role") != "system"]
            if tool_definitions:
                tool_definitions = [
                    t for t in tool_definitions
                    if t.get("function", {}).get("name") != "delegate_to_subagent"
                ]
                prompt_fingerprint = compute_config_fingerprint(
                    tool_definitions,
                    prompt_parts=prompt_parts,
                    model=effective_model,
                )

        if is_prompt_cache_enabled():
            current_messages = build_layered_messages(
                prompt_parts,
                messages,
                extra_system_suffix=extra_system_suffix,
            )
        else:
            content = system_prompt
            if extra_system_suffix and extra_system_suffix not in content:
                content += extra_system_suffix
            current_messages = [{"role": "system", "content": content}]
            current_messages.extend(m for m in messages if m.get("role") != "system")

        base_url = normalize_base_url(request.baseUrl)
        llm_timeout = httpx.Timeout(connect=LLM_CONNECT_TIMEOUT_SECONDS, read=LLM_READ_TIMEOUT_SECONDS, write=LLM_WRITE_TIMEOUT_SECONDS, pool=30.0)
        # 按域名规则决定是否走代理：境外模型 API (openai/anthropic/google/x.ai) 走代理，
        # 国产模型默认直连；代理 URL 与域名列表由用户在前端「网络代理」设置页维护。
        llm_proxy = get_httpx_proxy_for_url(request.baseUrl)

        # ESC 全局紧急停止（Windows 后台监听；等同前端停止 + 终端 Ctrl+C）
        if cancel_event and not _esc_listener_started and not is_subagent_mode:
            from utils.computer_use_lifecycle import start_computer_use_esc_listener
            from services.emergency_stop import emergency_stop_session_sync
            _sid, _wd, _ce = session_id, work_dir, cancel_event

            def _on_esc() -> None:
                if not _ce.is_set():
                    emergency_stop_session_sync(_sid, _wd)
                    _ce.set()

            if start_computer_use_esc_listener(_on_esc):
                _esc_listener_started = True

        # 从模型配置解析上下文窗口和工具轮次上限
        effective_context_window = request.context_window or 200_000
        effective_max_rounds = request.max_tool_rounds or 100

        async with httpx.AsyncClient(timeout=llm_timeout, trust_env=False, proxy=llm_proxy) as client:
            last_tool_name: str = ""
            repeat_count: int = 0
            _pending_images: list[str] = []

            for round_no in range(1, effective_max_rounds + 1):
                if await _should_stop_stream(cancel_event, disconnect_check):
                    cancelled = True
                    break

                payload = prepare_llm_payload(
                    model=effective_model,
                    messages=current_messages,
                    tool_definitions=tool_definitions,
                    stream=True,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )

                # LLM 流式请求：每个 chunk 后 drain SSE 队列，确保实时推送
                stream_result = _LLMStreamResult()
                async for _ in _handle_llm_stream(
                    client, base_url, headers, payload, logger, segment_sink,
                    cancel_event, disconnect_check, stream_result,
                ):
                    async for ev in _drain_sse_queue():
                        yield ev
                async for ev in _drain_sse_queue():
                    yield ev

                if logger:
                    api = (logger.get_run_metadata().get("token_usage") or {}).get("api_usage") or {}
                    if api.get("prompt_tokens") or api.get("completion_tokens"):
                        # 用 current_messages 重新计算 conversation breakdown，
                        # 包含工具调用循环中追加的 assistant tool_calls、tool 结果、截图等
                        from utils.token_counter import estimate_messages_tokens
                        conv_msgs = [m for m in current_messages if m.get("role") != "system"]
                        conv_tokens = estimate_messages_tokens(conv_msgs)
                        context_breakdown["breakdown"]["conversation"] = conv_tokens
                        real_pt = int(api.get("prompt_tokens") or 0)
                        if real_pt:
                            context_breakdown["estimated_tokens"] = real_pt
                            context_breakdown["from_api_prompt_tokens"] = real_pt
                            cw = effective_context_window
                            context_breakdown["context_window"] = cw
                            context_breakdown["usage_percent"] = round((real_pt / cw) * 100, 1) if cw > 0 else 0.0
                        else:
                            context_breakdown["estimated_tokens"] = sum(context_breakdown["breakdown"].values())
                        logger.set_token_usage({"context": context_breakdown})
                        logger.emit_run_metadata_snapshot()
                        yield f"event: stream_event\ndata: {json.dumps({'meta': logger.get_run_metadata()}, ensure_ascii=False)}\n\n"
                        async for ev in _drain_sse_queue():
                            yield ev

                full_content = stream_result.full_content
                tool_calls_buffer = stream_result.tool_calls_buffer

                if stream_result.error_msg:
                    friendly = stream_result.error_msg
                    if logger:
                        logger.write_assistant_segment(
                            "⚠️ 模型请求失败，任务已暂停。\n\n"
                            f"错误：{friendly}\n\n"
                            "这通常是模型网关无法处理当前请求（例如工具 schema 不兼容、上下文过大或截图过多）。"
                            "请稍后重试，或尝试更换模型、开启新对话后继续。"
                        )
                    yield f"event: stream_event\ndata: {json.dumps({'error': friendly}, ensure_ascii=False)}\n\n"
                    break

                if stream_result.cancelled:
                    cancelled = True

                if cancelled:
                    break

                if not tool_calls_buffer:
                    if segment_sink:
                        reasoning_text, assistant_text = logger.flush_assistant_round()
                        from services.platform_segment import emit_logger_segments
                        await emit_logger_segments(segment_sink, reasoning=reasoning_text, assistant=assistant_text)
                    try:
                        from memory.compaction import get_compactor
                        compactor = get_compactor()
                        compactor.maybe_trigger_compaction(session_id, current_messages, context_window=effective_context_window, is_warm=True)
                    except Exception:
                        pass
                    _pop_limit_hint_message(current_messages)
                    break

                # 落盘本轮分析文本
                reasoning_text, assistant_text = logger.flush_assistant_round()
                if segment_sink:
                    from services.platform_segment import emit_logger_segments
                    await emit_logger_segments(segment_sink, reasoning=reasoning_text, assistant=assistant_text)

                # ===== 执行工具调用 =====
                tool_results = []
                delegate_items: list[dict[str, Any]] = []
                # 分组：并行安全的只读工具 vs 需串行的工具
                parallel_tasks: list[dict[str, Any]] = []
                serial_items: list[dict[str, Any]] = []

                for tc in tool_calls_buffer:
                    tool_name = tc.get("function", {}).get("name", "")
                    args_str = tc.get("function", {}).get("arguments", "{}")
                    tool_id = tc.get("id") or f"call_{assistant_message_id}_{len(tool_results)}"
                    try:
                        args = json.loads(args_str) if args_str else {}
                    except json.JSONDecodeError:
                        args = {}

                    # delegate_to_subagent：收集后并行执行
                    if tool_name == "delegate_to_subagent":
                        delegate_items.append({
                            "tool_id": tool_id,
                            "tool_name": tool_name,
                            "args": args,
                            "sub_name": str(args.get("subagent_name") or args.get("agent_name") or "").strip(),
                            "sub_task": str(args.get("task") or "").strip(),
                            "sub_desc": str(args.get("description") or "").strip(),
                            "sub_context": str(args.get("context") or ""),
                            "sub_isolation": str(args.get("isolation") or "").strip(),
                            "round": round_no,
                        })
                        yield f"event: stream_event\ndata: {json.dumps({'tool_call': {'tool_call_id': tool_id, 'tool_name': tool_name, 'status': 'running', 'args': args, 'round': round_no}}, ensure_ascii=False)}\n\n"
                        logger.write_tool_call(tool_id, tool_name, args)
                        logger.write_subagent_block(
                            tool_call_id=tool_id,
                            subagent_name=str(args.get("subagent_name") or args.get("agent_name") or "").strip(),
                            task=str(args.get("task") or "").strip(),
                            status="running",
                        )
                        continue

                    item = {"tool_name": tool_name, "args": args, "tool_id": tool_id}
                    if is_parallel_safe(tool_name) and not cancel_event:
                        parallel_tasks.append(item)
                    else:
                        serial_items.append(item)

                # 1. 并行安全的只读工具：先发 running 事件，再 asyncio.gather 并发执行
                if parallel_tasks:
                    for item in parallel_tasks:
                        yield f"event: stream_event\ndata: {json.dumps({'tool_call': {'tool_call_id': item['tool_id'], 'tool_name': item['tool_name'], 'status': 'running', 'args': item['args'], 'round': round_no}}, ensure_ascii=False)}\n\n"
                        logger.write_tool_call(item['tool_id'], item['tool_name'], item['args'])

                    async def _run_one(item: dict) -> dict:
                        result, confirm_event, stream_stopped = await run_single_tool(
                            item['tool_name'], item['args'], item['tool_id'], session_id,
                            work_dir, round_no, logger, cancel_event, segment_sink, assistant_message_id,
                        )
                        return {"item": item, "result": result, "confirm_event": confirm_event, "stream_stopped": stream_stopped}

                    # 在后台 Task 中并发执行，同时持续 drain SSE 队列
                    gather_task = asyncio.ensure_future(
                        asyncio.gather(*[_run_one(it) for it in parallel_tasks], return_exceptions=True)
                    )
                    parallel_results = None
                    while not gather_task.done():
                        async for ev in _drain_sse_queue():
                            yield ev
                        try:
                            parallel_results = await asyncio.wait_for(asyncio.shield(gather_task), timeout=0.1)
                            break
                        except asyncio.TimeoutError:
                            continue
                    if parallel_results is None:
                        parallel_results = await gather_task
                    async for ev in _drain_sse_queue():
                        yield ev
                    for pr in parallel_results:
                        if isinstance(pr, Exception):
                            # gather 异常：构造错误结果
                            tool_results.append({"tool_call_id": "error", "role": "tool", "content": json.dumps({"error": str(pr)}, ensure_ascii=False)})
                            continue
                        item = pr["item"]
                        result = pr["result"]
                        confirm_event = pr["confirm_event"]
                        stream_stopped = pr["stream_stopped"]

                        if confirm_event:
                            # confirmation_required 已通过 SessionLogger.write_confirmation_required
                            # → JSONL log_event → SSE 推送，此处无需重复 yield
                            yield f"event: stream_event\ndata: {json.dumps({'tool_result': {'tool_name': item['tool_name'], 'status': 'pending_confirmation', 'output': '等待用户确认危险命令…', 'round': round_no}}, ensure_ascii=False)}\n\n"

                        tool_results.append({
                            "tool_call_id": item['tool_id'],
                            "role": "tool",
                            "content": format_tool_result_for_model(result) if isinstance(result, dict) else str(result),
                        })

                        status = "completed" if not isinstance(result, dict) or not result.get("error") else "error"
                        error_msg = result.get("error", "") if isinstance(result, dict) else ""
                        output = result.get("output", "") if isinstance(result, dict) else str(result)
                        _file_change = result.get("file_change") if isinstance(result, dict) else None
                        is_cached = bool(isinstance(result, dict) and result.get("_cached"))
                        log_payload = tool_result_for_logging(result) if isinstance(result, dict) else {"output": str(result)}
                        screenshot_preview = log_payload.pop("screenshot_preview", None)
                        logger.write_tool_result(
                            item['tool_id'], item['tool_name'], status,
                            result=json.dumps(log_payload, ensure_ascii=False),
                            error=error_msg, session_id=result.get("session_id", "") if isinstance(result, dict) else "",
                            file_change=_file_change,
                            cached=is_cached,
                        )
                        if segment_sink:
                            await segment_sink.on_tool_done(item['tool_name'], status, log_payload.get("output", output))

                        result_event = build_tool_result_event(
                            item['tool_name'], item['tool_id'], status, log_payload.get("output", output), round_no, result, cached=is_cached,
                            log_payload={**log_payload, **({"screenshot_preview": screenshot_preview} if screenshot_preview else {})},
                        )
                        yield f"event: stream_event\ndata: {json.dumps({'tool_result': result_event}, ensure_ascii=False)}\n\n"

                        yield f"event: stream_event\ndata: {json.dumps({'meta': logger.get_run_metadata()}, ensure_ascii=False)}\n\n"
                        async for ev in _drain_sse_queue():
                            yield ev

                        if stream_stopped:
                            cancelled = True
                            final_content = full_content

                # 2. 需串行的工具：逐个执行
                for item in serial_items:
                    if await _should_stop_stream(cancel_event, disconnect_check):
                        cancelled = True
                        final_content = full_content
                        break
                    tool_name = item['tool_name']
                    args = item['args']
                    tool_id = item['tool_id']

                    yield f"event: stream_event\ndata: {json.dumps({'tool_call': {'tool_call_id': tool_id, 'tool_name': tool_name, 'status': 'running', 'args': args, 'round': round_no}}, ensure_ascii=False)}\n\n"
                    # 在后台 Task 中执行工具（含确认等待），同时持续 drain SSE 队列，
                    # 确保 confirmation_required 等事件能被及时推送到前端
                    tool_task = asyncio.ensure_future(run_single_tool(
                        tool_name, args, tool_id, session_id, work_dir, round_no,
                        logger, cancel_event, segment_sink, assistant_message_id,
                    ))
                    result = None
                    confirm_event = False
                    stream_stopped = False
                    while not tool_task.done():
                        # 先 drain 队列中的事件
                        async for ev in _drain_sse_queue():
                            yield ev
                        # 等待一小段时间或工具完成
                        try:
                            result, confirm_event, stream_stopped = await asyncio.wait_for(
                                asyncio.shield(tool_task), timeout=0.1
                            )
                            break
                        except asyncio.TimeoutError:
                            continue
                    if result is None:
                        result, confirm_event, stream_stopped = await tool_task
                    # 工具已完成，再 drain 一次
                    async for ev in _drain_sse_queue():
                        yield ev

                    if confirm_event:
                        # confirmation_required 已通过 SessionLogger.write_confirmation_required
                        # → JSONL log_event → SSE 推送，此处无需重复 yield
                        yield f"event: stream_event\ndata: {json.dumps({'tool_result': {'tool_name': tool_name, 'status': 'pending_confirmation', 'output': '等待用户确认危险命令…', 'round': round_no}}, ensure_ascii=False)}\n\n"

                    tool_results.append({
                        "tool_call_id": tool_id,
                        "role": "tool",
                        "content": format_tool_result_for_model(result) if isinstance(result, dict) else str(result),
                    })

                    status = "completed" if not isinstance(result, dict) or not result.get("error") else "error"
                    error_msg = result.get("error", "") if isinstance(result, dict) else ""
                    output = result.get("output", "") if isinstance(result, dict) else str(result)
                    _file_change = result.get("file_change") if isinstance(result, dict) else None
                    is_cached = bool(isinstance(result, dict) and result.get("_cached"))
                    log_payload = tool_result_for_logging(result) if isinstance(result, dict) else {"output": str(result)}
                    screenshot_preview = log_payload.pop("screenshot_preview", None)
                    logger.write_tool_result(
                        tool_id, tool_name, status,
                        result=json.dumps(log_payload, ensure_ascii=False),
                        error=error_msg, session_id=result.get("session_id", "") if isinstance(result, dict) else "",
                        file_change=_file_change,
                        cached=is_cached,
                    )
                    if segment_sink:
                        await segment_sink.on_tool_done(tool_name, status, log_payload.get("output", output))

                    result_event = build_tool_result_event(
                        tool_name, tool_id, status, log_payload.get("output", output), round_no, result, cached=is_cached,
                        log_payload={**log_payload, **({"screenshot_preview": screenshot_preview} if screenshot_preview else {})},
                    )
                    yield f"event: stream_event\ndata: {json.dumps({'tool_result': result_event}, ensure_ascii=False)}\n\n"

                    yield f"event: stream_event\ndata: {json.dumps({'meta': logger.get_run_metadata()}, ensure_ascii=False)}\n\n"
                    async for ev in _drain_sse_queue():
                        yield ev

                    if stream_stopped:
                        cancelled = True
                        final_content = full_content
                        break

                if cancelled:
                    break

                # 并行执行 delegate_to_subagent
                sub_tool_results = []
                async for ev in run_delegate_items(
                    delegate_items, session_id, work_dir, logger, cancel_event, round_no,
                    sse_queue=_sse_queue,
                ):
                    async for drained in _drain_sse_queue():
                        yield drained
                    if ev.get("__sse_drain"):
                        continue
                    if "__final_results" in ev:
                        sub_tool_results = ev["__final_results"]
                    else:
                        # 子 Agent 状态事件（running/stalled/success）；内嵌细节走 subagent_log_event
                        yield f"event: stream_event\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                async for drained in _drain_sse_queue():
                    yield drained
                for sr in sub_tool_results:
                    yield f"event: stream_event\ndata: {json.dumps({'tool_result': {'tool_name': 'delegate_to_subagent', 'tool_call_id': sr['tool_call_id'], 'status': 'completed', 'output': '', 'round': round_no}}, ensure_ascii=False)}\n\n"
                tool_results.extend(sub_tool_results)

                # 连续相同工具检测
                round_tool_names = set()
                for tc in tool_calls_buffer:
                    fn = tc.get("function", {}).get("name", "")
                    if fn:
                        round_tool_names.add(fn)
                if len(round_tool_names) == 1:
                    single_tool = next(iter(round_tool_names))
                    if single_tool == last_tool_name:
                        repeat_count += 1
                    else:
                        last_tool_name = single_tool
                        repeat_count = 1
                else:
                    last_tool_name = ""
                    repeat_count = 0

                if repeat_count >= REPEAT_TOOL_LIMIT:
                    current_messages.append({
                        "role": "system",
                        "content": f"【系统提醒】检测到连续 {repeat_count} 轮调用相同工具「{last_tool_name}」，可能陷入了循环。请停止重复调用，总结当前进度和遇到的问题，告知用户需要什么信息或帮助来继续。"
                    })
                    yield f"data: {json.dumps({'hint': f'检测到重复调用 {last_tool_name}，正在整理进度…'}, ensure_ascii=False)}\n\n"
                    repeat_count = 0
                    last_tool_name = ""

                # 构建下一轮消息
                current_messages.append({
                    "role": "assistant",
                    "content": final_content if final_content else None,
                    "tool_calls": _sanitize_tool_calls_for_messages(tool_calls_buffer),
                })
                for tr in tool_results:
                    tool_msg, img_b64 = _strip_image_base64(tr)
                    current_messages.append(tool_msg)
                    if img_b64:
                        _pending_images.append(img_b64)

                # 截图图片作为单独的 user 消息注入（兼容所有 API，tool 消息不支持 content array）
                if _pending_images:
                    user_content: list[dict] = [{"type": "text", "text": "以下是刚才截取的屏幕截图，请根据画面内容决定下一步操作："}]
                    for b64 in _pending_images:
                        user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
                    current_messages.append({"role": "user", "content": user_content})
                    _pending_images = []

                # 注入任务清单
                _todos = get_todos(session_id)
                if _todos:
                    purge_todo_messages(current_messages)
                    current_messages.append({"role": "system", "content": format_todos_for_context(_todos)})

                # 实时上下文检查（接近窗口上限时记录日志，不压缩以避免破坏 cache prefix）
                try:
                    from memory.compaction import should_compact
                    from utils.token_counter import estimate_message_tokens
                    if should_compact(current_messages, max_history_tokens=int(effective_context_window * 0.7)):
                        total_tok = sum(estimate_message_tokens(m) for m in current_messages)
                        if logger:
                            logger.write_info_event("context_approaching_limit",
                                f"工具循环中上下文接近窗口上限：{len(current_messages)} 条消息，约 {total_tok} tokens",
                                details=json.dumps({"message_count": len(current_messages), "tokens": total_tok}, ensure_ascii=False))
                except Exception:
                    pass
            else:
                _pop_limit_hint_message(current_messages)
                if logger:
                    logger.write_error_event("step_limit_exceeded", f"工具调用达到上限（{effective_max_rounds} 轮）")
    finally:
        # 停止 ESC 热键监听，并关闭 codex-computer-use.exe（与 SSE 流生命周期对齐）
        if _esc_listener_started:
            from utils.computer_use_lifecycle import stop_computer_use_esc_listener
            stop_computer_use_esc_listener()
        from utils.computer_use_lifecycle import release_computer_use_client
        release_computer_use_client()

        if assistant_message_id is not None and logger is not None:
            # 先推送 run_metadata + log_complete，避免 DB 落盘阻塞前端结束态
            if not logger.is_finalized():
                cache_summary = summarize_cache_usage(
                    (logger.get_run_metadata().get("token_usage") or {}).get("api_usage") or {}
                )
                if cache_summary:
                    existing_pc = (logger.get_run_metadata().get("token_usage") or {}).get("prompt_cache") or {}
                    logger.set_token_usage({"prompt_cache": {**existing_pc, **cache_summary}})
                logger.apply_api_usage_estimate()
                logger.finalize()

            if cancelled:
                logger.write_info_event("stream_interrupted", "用户中断或连接断开，正在保存已有进度到数据库")
            reasoning_text, assistant_text = logger.flush_assistant_round()
            _pop_limit_hint_message(current_messages)
            purge_todo_messages(current_messages)
            if segment_sink:
                from services.platform_segment import emit_logger_segments
                await emit_logger_segments(segment_sink, reasoning=reasoning_text, assistant=assistant_text)

            db_content = logger.build_db_content() or final_content or ""
            if not db_content and cancelled:
                db_reasoning = logger.build_db_reasoning()
                if db_reasoning:
                    db_content = db_reasoning
            if db_content:
                set_summary_block(snapshot, db_content)
                finalize_snapshot(snapshot)
            elif cancelled:
                logger.flush_reasoning_segment()

            stop_note = ""
            if cancelled and not db_content:
                stop_note = "（用户中断，任务未完成。请发送「继续」以恢复执行。）"
            # AI 消息不再写 content/reasoning_content 到 DB，仅更新快照路径
            # 取消时写入 stop_note 作为兜底，确保前端有内容显示
            if stop_note:
                update_message(
                    assistant_message_id,
                    content=stop_note,
                    message_snapshot_json=logger.jsonl_path_str(),
                )
            else:
                update_message(
                    assistant_message_id,
                    message_snapshot_json=logger.jsonl_path_str(),
                )
            yield f"event: stream_event\ndata: {json.dumps({'meta': logger.get_run_metadata()}, ensure_ascii=False)}\n\n"
            async for ev in _drain_sse_queue():
                yield ev
            # SSE 通知前端：assistant 回复结束
            yield f"event: log_complete\ndata: {json.dumps({'session_id': session_id, 'message_id': assistant_message_id, 'jsonl_path': jsonl_path}, ensure_ascii=False)}\n\n"
