"""主流式 Agent 逻辑：多轮工具调用、子 Agent 并行委派、实时上下文压缩。"""
import json
import asyncio
import httpx
from typing import AsyncGenerator, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from services.platform_segment import PlatformStreamSink

from utils.url_utils import normalize_base_url
from utils.message_snapshot import (
    create_assistant_snapshot,
    set_summary_block,
    finalize_snapshot,
)
from utils.session_logger import SessionLogger
from utils.token_counter import extract_usage_from_stream_chunk
from db.chat import save_message, update_message

from .stream_constants import (
    MAX_TOOL_ROUNDS,
    REPEAT_TOOL_LIMIT,
    LLM_CONNECT_TIMEOUT_SECONDS,
    LLM_READ_TIMEOUT_SECONDS,
    LLM_WRITE_TIMEOUT_SECONDS,
    _HINT_PREFIXES,
)
from .todo_handler import get_todos, format_todos_for_context, purge_todo_messages
from .system_prompt import build_agent_system_prompt_parts, get_agent_skills_and_tools
from .tool_runner import run_single_tool, run_delegate_items, build_tool_result_event


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
) -> AsyncGenerator[str, None]:
    """向 LLM 发起流式请求，yield SSE 事件，结果写入 result 容器。"""
    reasoning_emitted_before_content = False

    try:
        async with client.stream("POST", f"{base_url}/chat/completions", headers=headers, json=payload) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                result.error_msg = error_text.decode()
                if logger:
                    logger.write_error_event("api_error", result.error_msg)
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
                        choices = chunk.get("choices", [])
                        if not choices:
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
                            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                            continue

                        if "reasoning_content" in delta and delta["reasoning_content"]:
                            logger.append_reasoning_delta(delta["reasoning_content"])
                            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                            continue

                        if "content" in delta and delta["content"]:
                            if segment_sink and not reasoning_emitted_before_content:
                                reasoning_text = logger.flush_reasoning_segment()
                                if reasoning_text:
                                    await segment_sink.on_reasoning(reasoning_text)
                                reasoning_emitted_before_content = True
                            content = delta["content"]
                            result.full_content += content
                            logger.record_assistant_content(content)
                            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                        if finish_reason in ("tool_calls", "stop"):
                            break

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
) -> AsyncGenerator[str, None]:
    """Agent 模式 - 支持多轮工具调用"""
    final_content = ""
    cancelled = False
    assistant_message_id = None
    logger = None
    snapshot = ""

    try:
        assistant_message_id = save_message(session_id, "assistant", "", message_snapshot_json="", mode="agent")
        logger = SessionLogger(session_id=session_id, message_id=assistant_message_id)
        logger.set_model(getattr(request, "model", "") or "")
        breakdown_inputs = base_payload.pop("context_breakdown_inputs", None) or {}
        base_payload.pop("context_token_info", None)
        snapshot = create_assistant_snapshot(session_id, logger)

        skills_context, tool_definitions, mcp_context, subagents_context = get_agent_skills_and_tools()
        prompt_parts = build_agent_system_prompt_parts(
            skills_context, work_dir=work_dir, session_id=session_id,
            mcp_context=mcp_context, subagents_context=subagents_context,
        )
        system_prompt = prompt_parts["full"]

        # context usage breakdown
        from utils.token_counter import build_context_usage_breakdown
        model_name = getattr(request, "model", "") or ""
        context_breakdown = build_context_usage_breakdown(
            system_prompt_base=prompt_parts["base"] + (prompt_parts.get("mcp") or "") + (prompt_parts.get("subagents") or ""),
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
        logger.set_token_usage({"context": context_breakdown})
        yield f"data: {json.dumps({'meta': logger.get_run_metadata()}, ensure_ascii=False)}\n\n"

        # ===== 意图识别 =====
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
            if intent != INTENT_AGENT:
                tool_definitions = filter_tools_for_intent(intent, tool_definitions)
            intent_prompt = get_prompt_for_intent(intent)
            if intent_prompt:
                system_prompt = system_prompt + "\n\n" + intent_prompt
            yield f"data: {json.dumps({'intent': intent}, ensure_ascii=False)}\n\n"
        except Exception:
            pass

        current_messages = [{"role": "system", "content": system_prompt}]
        current_messages.extend(messages)

        base_url = normalize_base_url(request.baseUrl)
        llm_timeout = httpx.Timeout(connect=LLM_CONNECT_TIMEOUT_SECONDS, read=LLM_READ_TIMEOUT_SECONDS, write=LLM_WRITE_TIMEOUT_SECONDS, pool=30.0)

        async with httpx.AsyncClient(timeout=llm_timeout, trust_env=False) as client:
            last_tool_name: str = ""
            repeat_count: int = 0

            for round_no in range(1, MAX_TOOL_ROUNDS + 1):
                if await _should_stop_stream(cancel_event, disconnect_check):
                    cancelled = True
                    break

                # 第 24 轮提醒
                if round_no == MAX_TOOL_ROUNDS - 1:
                    current_messages.append({
                        "role": "system",
                        "content": (
                            "【系统提醒】你当前已接近本地工具调用上限（25 轮）。"
                            "本轮请不要再发起新的工具调用，而是总结截至目前已完成的任务内容、"
                            "已修改的文件、已验证的结果，以及剩余未完成的工作。"
                            "用精炼的语言向用户汇报进度，并告知用户如需要继续可发送「继续」。"
                        )
                    })
                    yield f"data: {json.dumps({'hint': '工具调用即将达到上限，正在整理执行进度…'}, ensure_ascii=False)}\n\n"

                payload = {
                    "model": request.model, "messages": current_messages, "stream": True,
                }
                if tool_definitions:
                    payload["tools"] = tool_definitions
                    payload["tool_choice"] = "auto"
                if request.temperature is not None:
                    payload["temperature"] = request.temperature
                if request.max_tokens is not None:
                    payload["max_tokens"] = request.max_tokens

                # LLM 流式请求
                stream_result = _LLMStreamResult()
                async for event in _handle_llm_stream(
                    client, base_url, headers, payload, logger, segment_sink,
                    cancel_event, disconnect_check, stream_result,
                ):
                    yield event

                full_content = stream_result.full_content
                tool_calls_buffer = stream_result.tool_calls_buffer

                if stream_result.error_msg:
                    yield f"data: {json.dumps({'error': stream_result.error_msg}, ensure_ascii=False)}\n\n"
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
                        compactor.maybe_trigger_compaction(session_id, current_messages, context_window=200_000, is_warm=True)
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

                for tc in tool_calls_buffer:
                    if await _should_stop_stream(cancel_event, disconnect_check):
                        cancelled = True
                        final_content = full_content
                        break
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
                        yield f"data: {json.dumps({'tool_call': {'tool_call_id': tool_id, 'tool_name': tool_name, 'status': 'running', 'args': args, 'round': round_no}}, ensure_ascii=False)}\n\n"
                        logger.write_tool_call(tool_id, tool_name, args)
                        logger.write_subagent_block(
                            tool_call_id=tool_id,
                            subagent_name=str(args.get("subagent_name") or args.get("agent_name") or "").strip(),
                            task=str(args.get("task") or "").strip(),
                            status="running",
                        )
                        continue

                    # 普通工具执行
                    result, confirm_event, stream_stopped = await run_single_tool(
                        tool_name, args, tool_id, session_id, work_dir, round_no,
                        logger, cancel_event, segment_sink, assistant_message_id,
                    )

                    if confirm_event:
                        yield f"data: {json.dumps(confirm_event, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'tool_result': {'tool_name': tool_name, 'status': 'pending_confirmation', 'output': '等待用户确认危险命令…', 'round': round_no}}, ensure_ascii=False)}\n\n"

                    tool_results.append({
                        "tool_call_id": tool_id,
                        "role": "tool",
                        "content": json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                    })

                    status = "completed" if not isinstance(result, dict) or not result.get("error") else "error"
                    error_msg = result.get("error", "") if isinstance(result, dict) else ""
                    output = result.get("output", "") if isinstance(result, dict) else str(result)
                    _file_change = result.get("file_change") if isinstance(result, dict) else None
                    logger.write_tool_result(
                        tool_id, tool_name, status,
                        result=json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                        error=error_msg, session_id=result.get("session_id", "") if isinstance(result, dict) else "",
                        file_change=_file_change,
                    )
                    if segment_sink:
                        await segment_sink.on_tool_done(tool_name, status, output)

                    result_event = build_tool_result_event(tool_name, tool_id, status, output, round_no, result)
                    yield f"data: {json.dumps({'tool_result': result_event}, ensure_ascii=False)}\n\n"

                    try:
                        from services.chat_ws import broadcast_stream_event
                        await broadcast_stream_event(session_id, {"meta": logger.get_run_metadata()})
                    except Exception:
                        pass

                    if stream_stopped:
                        cancelled = True
                        final_content = full_content
                        break

                if cancelled:
                    break

                # 并行执行 delegate_to_subagent
                sub_tool_results = await run_delegate_items(
                    delegate_items, session_id, work_dir, logger, cancel_event, round_no,
                )
                for sr in sub_tool_results:
                    yield f"data: {json.dumps({'tool_result': {'tool_name': 'delegate_to_subagent', 'tool_call_id': sr['tool_call_id'], 'status': 'completed', 'output': '', 'round': round_no}}, ensure_ascii=False)}\n\n"
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
                    "tool_calls": tool_calls_buffer
                })
                for tr in tool_results:
                    current_messages.append({"role": "tool", "tool_call_id": tr["tool_call_id"], "content": tr["content"]})

                # 注入任务清单
                _todos = get_todos(session_id)
                if _todos:
                    purge_todo_messages(current_messages)
                    current_messages.append({"role": "system", "content": format_todos_for_context(_todos)})

                # 实时上下文压缩
                try:
                    from memory.compaction import should_compact, split_messages_for_compaction, build_session_summary
                    from utils.token_counter import estimate_message_tokens
                    if should_compact(current_messages):
                        to_compact, to_keep = split_messages_for_compaction(current_messages)
                        if to_compact and len(to_compact) > 4:
                            summary = build_session_summary(to_compact)
                            system_msgs = [m for m in current_messages if m.get("role") == "system"]
                            compacted = system_msgs + [{"role": "system", "content": f"## 之前的对话摘要\n\n{summary}\n\n---\n以上是之前对话的摘要，以下是最近的对话内容："}] + to_keep
                            old_count = len(current_messages)
                            old_tokens = sum(estimate_message_tokens(m) for m in current_messages)
                            current_messages[:] = compacted
                            new_tokens = sum(estimate_message_tokens(m) for m in current_messages)
                            if logger:
                                logger.write_info_event("context_compacted",
                                    f"工具循环中压缩上下文：{old_count} → {len(current_messages)} 条消息，约 {old_tokens} → {new_tokens} tokens",
                                    details=json.dumps({"old_count": old_count, "new_count": len(current_messages), "old_tokens": old_tokens, "new_tokens": new_tokens}, ensure_ascii=False))
                            yield f"data: {json.dumps({'hint': '上下文已自动压缩，继续执行…'}, ensure_ascii=False)}\n\n"
                except Exception:
                    pass
            else:
                _pop_limit_hint_message(current_messages)
                if logger:
                    logger.write_error_event("step_limit_exceeded", f"工具调用达到上限（{MAX_TOOL_ROUNDS} 轮），已在前一轮引导 AI 总结进度。")
    finally:
        if assistant_message_id is not None and logger is not None:
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
            update_message(
                assistant_message_id,
                content=db_content or stop_note or "（无响应）",
                message_snapshot_json=logger.jsonl_path_str(),
                reasoning_content=logger.build_db_reasoning()
            )
            yield f"data: {json.dumps({'meta': logger.get_run_metadata()}, ensure_ascii=False)}\n\n"
            logger.finalize()
