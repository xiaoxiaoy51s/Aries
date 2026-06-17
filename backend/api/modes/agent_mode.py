import json
import os
import platform
import asyncio
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from services.platform_segment import PlatformStreamSink

from utils.url_utils import normalize_base_url
from utils.skills_manager import (
    discover_skills,
    get_all_tool_definitions,
    execute_tool,
    build_skills_context_from_entries,
)
from utils.message_snapshot import (
    create_assistant_snapshot,
    set_summary_block,
    finalize_snapshot,
)
from utils.session_logger import SessionLogger
from db.chat import save_message, update_message

MAX_TOOL_ROUNDS = 30
CONFIRMATION_TIMEOUT_SECONDS = 120.0
LLM_CONNECT_TIMEOUT_SECONDS = 30.0
LLM_READ_TIMEOUT_SECONDS = 900.0
LLM_WRITE_TIMEOUT_SECONDS = 120.0
TOOL_EXECUTION_TIMEOUT_SECONDS = 600.0

_pending_confirmations: dict[str, asyncio.Event] = {}
_pending_confirmation_results: dict[str, bool] = {}


def register_confirmation_wait(tool_call_id: str) -> asyncio.Event:
    event = asyncio.Event()
    _pending_confirmations[tool_call_id] = event
    return event


def resolve_confirmation(tool_call_id: str, confirmed: bool) -> bool:
    tid = str(tool_call_id or "").strip()
    if not tid:
        return False
    event = _pending_confirmations.get(tid)
    if event is None:
        return False
    _pending_confirmation_results[tid] = confirmed
    event.set()
    return True


async def wait_for_confirmation(tool_call_id: str, timeout: float = 600.0) -> bool:
    event = _pending_confirmations.get(tool_call_id)
    if not event:
        return False
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        _pending_confirmations.pop(tool_call_id, None)
        _pending_confirmation_results.pop(tool_call_id, None)
        return False
    return _pending_confirmation_results.pop(tool_call_id, False)


async def wait_for_confirmation_with_cancel(
    tool_call_id: str,
    cancel_event: Optional[asyncio.Event] = None,
    timeout: float = 600.0,
) -> bool:
    """Wait for user tool confirmation, but abort if the chat stream is cancelled."""
    event = _pending_confirmations.get(tool_call_id)
    if not event:
        return False

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while loop.time() < deadline:
        if cancel_event and cancel_event.is_set():
            resolve_confirmation(tool_call_id, False)
            return False
        if tool_call_id in _pending_confirmation_results:
            confirmed = _pending_confirmation_results.pop(tool_call_id, False)
            _pending_confirmations.pop(tool_call_id, None)
            return confirmed
        if event.is_set():
            _pending_confirmations.pop(tool_call_id, None)
            return _pending_confirmation_results.pop(tool_call_id, False)
        try:
            await asyncio.wait_for(event.wait(), timeout=min(0.2, deadline - loop.time()))
        except asyncio.TimeoutError:
            continue

    _pending_confirmations.pop(tool_call_id, None)
    _pending_confirmation_results.pop(tool_call_id, None)
    return False


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


def _cancel_cli_invocations() -> None:
    """用户停止/取消时调用：终止所有正在运行的 CLI 进程并清理临时日志。

    防止上一次未结束的 ps1/cmd 调度文件或 done 文件被下一轮误读，
    也避免后台进程占用 PTY 句柄导致后续命令死锁。
    """
    try:
        from utils.cli_executor import CLIExecutor
        for inv_id in CLIExecutor.get_active_invocations():
            CLIExecutor.set_interrupt_action(inv_id, "terminate")
        CLIExecutor.terminate_all_active(action="terminate")
    except Exception:
        pass
    try:
        from utils.cli_executor import CLIExecutor as _CE
        _CE.clear_runtime_dir()
    except Exception:
        pass
    try:
        from services.terminal_manager import TerminalManager
        TerminalManager.terminate_all_active(action="terminate")
        TerminalManager.clear_runtime_dir()
    except Exception:
        pass


def _session_context_note(session_id: str | None) -> str:
    """生成当前会话说明，供 system prompt 与工具默认行为使用。"""
    sid = (session_id or "").strip()
    if not sid:
        return "当前 session_id：未知"

    from db.scheduled_task import infer_platform

    platform = infer_platform(sid)
    platform_labels = {"wechat": "微信", "qq": "QQ", "feishu": "飞书"}
    if platform:
        label = platform_labels.get(platform, platform)
        return (
            f"当前 session_id：`{sid}`\n"
            f"消息来源：{label}（用户从此平台发来消息；"
            f"创建定时任务时若用户未指定推送平台，默认推送到{label}）"
        )
    return (
        f"当前 session_id：`{sid}`\n"
        "消息来源：网页聊天（创建定时任务时若用户未指定推送平台，默认在当前网页会话中继续）"
    )


def build_agent_system_prompt(
    skills_context: str,
    work_dir: str | None = None,
    session_id: str | None = None,
    mcp_context: str = "",
) -> str:
    """构建 Agent 模式的系统提示词（精简版）

    work_dir: 当前 session 的工作目录；为空时回退到默认 ~/.MIMOClaw
    session_id: 当前会话 ID；每次用户发消息时传入，供 AI 识别来源与默认推送目标
    """
    from pathlib import Path
    today_str = datetime.now().strftime("%Y-%m-%d")

    if work_dir and work_dir.strip():
        wd = str(Path(work_dir).expanduser().resolve())
        # 临时脚本目录与工作目录并列
        tmp_dir = str(Path(wd) / ".MIMOClaw_tmp")
        target_note = wd
    else:
        wd = str(Path.home() / ".MIMOClaw" / "work_dir")
        tmp_dir = str(Path.home() / ".MIMOClaw" / "tmp")
        target_note = f"{wd}\\{today_str}"

    prompt = (
        "# 身份\n"
        "你是一个强大的多用途 AI 助手，擅长任务规划、文档创建、网络研究和代码执行。"
        f"今天的日期是 {today_str}，当前操作系统：{platform.system()}。\n"
        "\n"
        "# 当前会话\n"
        f"{_session_context_note(session_id)}\n"
        "\n"
        "# 工作目录\n"
        f"工作目录：`{wd}`\n"
        f"临时脚本目录：`{tmp_dir}`\n"
        f"⚠️ 所有生成的文件都应保存到工作目录：`{target_note}` 下！\n"
        "\n"
        "# 输出规范\n"
        "- 工具轮：输出「分析+计划」，再调用工具\n"
        "- 最终轮：直接输出精炼总结\n"
        "- 批量调用：无依赖的工具可同一轮调用\n"
        "- 所有工具失败时：2次尝试内停止，告知障碍，禁止伪造结果\n"
        "\n"
        "# Skill 使用规范\n"
        "在使用skill前，必须阅读SKILL.md文件，了解技能的用途和使用方法。不要直接上来就调用工具，有些工具虽然可以通过描述知道对应的使用方法，但是md文件中会有更加详细的使用说明。"
    )

    if skills_context:
        prompt += (
            "\n# 已安装的本地 Skills\n"
            f"{skills_context}"
        )

    if mcp_context:
        prompt += f"\n# MCP 插件\n{mcp_context}"

    return prompt


def get_agent_skills_and_tools():
    from utils.mcp_runtime import build_mcp_prompt_context

    skills = discover_skills()
    enabled_skills = [s for s in skills if s.enabled]
    skills_context = build_skills_context_from_entries(enabled_skills)
    tool_definitions = get_all_tool_definitions()
    mcp_context = build_mcp_prompt_context()
    return skills_context, tool_definitions, mcp_context


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
    """Agent 模式 - 支持多轮工具调用

    work_dir: 当前 session 的工作目录；会注入到 system prompt 和工具调用中
    """
    from utils.url_utils import normalize_base_url
    import httpx

    final_content = ""
    cancelled = False
    assistant_message_id = None
    logger = None
    snapshot = ""

    try:
        assistant_message_id = save_message(session_id, "assistant", "", message_snapshot_json="", mode="agent")
        logger = SessionLogger(session_id=session_id, message_id=assistant_message_id)
        snapshot = create_assistant_snapshot(session_id, logger)

        skills_context, tool_definitions, mcp_context = get_agent_skills_and_tools()

        system_prompt = build_agent_system_prompt(
            skills_context, work_dir=work_dir, session_id=session_id, mcp_context=mcp_context
        )

        current_messages = [{"role": "system", "content": system_prompt}]
        current_messages.extend(messages)

        base_url = normalize_base_url(request.baseUrl)
        llm_timeout = httpx.Timeout(
            connect=LLM_CONNECT_TIMEOUT_SECONDS,
            read=LLM_READ_TIMEOUT_SECONDS,
            write=LLM_WRITE_TIMEOUT_SECONDS,
            pool=30.0,
        )

        async with httpx.AsyncClient(timeout=llm_timeout, trust_env=False) as client:
            for round_no in range(1, MAX_TOOL_ROUNDS + 1):
                if await _should_stop_stream(cancel_event, disconnect_check):
                    cancelled = True
                    _cancel_cli_invocations()
                    break
                reasoning_emitted_before_content = False
                current_payload = {
                    "model": request.model,
                    "messages": current_messages,
                    "stream": True,
                }

                if tool_definitions:
                    current_payload["tools"] = tool_definitions
                    current_payload["tool_choice"] = "auto"

                if request.temperature is not None:
                    current_payload["temperature"] = request.temperature
                if request.max_tokens is not None:
                    current_payload["max_tokens"] = request.max_tokens

                full_content = ""
                tool_calls_buffer = []

                try:
                    async with client.stream(
                        "POST",
                        f"{base_url}/chat/completions",
                        headers=headers,
                        json=current_payload,
                    ) as response:
                        if response.status_code != 200:
                            error_text = await response.aread()
                            error_msg = error_text.decode()
                            # 记录 API 错误到数据库
                            if logger:
                                logger.write_error_event("api_error", error_msg)
                            yield f"data: {json.dumps({'error': error_msg})}\n\n"
                            return

                        async for line in response.aiter_lines():
                            if await _should_stop_stream(cancel_event, disconnect_check):
                                final_content = full_content
                                cancelled = True
                                _cancel_cli_invocations()
                                break
                            if line.startswith("data: "):
                                data = line[6:]
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    choices = chunk.get("choices", [])
                                    if not choices:
                                        continue

                                    delta = choices[0].get("delta", {})
                                    finish_reason = choices[0].get("finish_reason")

                                    if "tool_calls" in delta and delta["tool_calls"]:
                                        for tc_delta in delta["tool_calls"]:
                                            index = tc_delta.get("index", 0)

                                            while len(tool_calls_buffer) <= index:
                                                tool_calls_buffer.append({
                                                    "id": "",
                                                    "type": "function",
                                                    "function": {"name": "", "arguments": ""}
                                                })

                                            tc = tool_calls_buffer[index]

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
                                        full_content += content
                                        logger.record_assistant_content(content)
                                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

                                    if finish_reason == "tool_calls":
                                        break

                                    if finish_reason == "stop":
                                        break

                                except json.JSONDecodeError:
                                    continue

                        if cancelled:
                            break
                except httpx.TimeoutException:
                    error_msg = (
                        f"模型 API 读取超时（{int(LLM_READ_TIMEOUT_SECONDS)} 秒内无新数据）。"
                        "常见于 Playwright 等多轮工具任务后模型响应较慢，请稍后重试或拆分任务。"
                    )
                    if logger:
                        logger.write_error_event("timeout", error_msg)
                    yield f"data: {json.dumps({'error': error_msg}, ensure_ascii=False)}\n\n"
                    break
                except httpx.HTTPError as exc:
                    error_msg = f"模型 API 请求失败：{exc}"
                    if logger:
                        logger.write_error_event("http_error", error_msg)
                    yield f"data: {json.dumps({'error': error_msg}, ensure_ascii=False)}\n\n"
                    break

                final_content = full_content

                if cancelled:
                    break

                if not tool_calls_buffer:
                    if segment_sink:
                        reasoning_text, assistant_text = logger.flush_assistant_round()
                        from services.platform_segment import emit_logger_segments
                        await emit_logger_segments(
                            segment_sink,
                            reasoning=reasoning_text,
                            assistant=assistant_text,
                        )
                    break

                # 本轮分析文本落盘，再执行工具（避免多轮时只保存最后一轮）
                reasoning_text, assistant_text = logger.flush_assistant_round()
                if segment_sink:
                    from services.platform_segment import emit_logger_segments
                    await emit_logger_segments(
                        segment_sink,
                        reasoning=reasoning_text,
                        assistant=assistant_text,
                    )

                # 执行工具调用
                tool_results = []
                for tc in tool_calls_buffer:
                    stream_stopped = False
                    if await _should_stop_stream(cancel_event, disconnect_check):
                        cancelled = True
                        final_content = full_content
                        _cancel_cli_invocations()
                        break
                    tool_name = tc.get("function", {}).get("name", "")
                    args_str = tc.get("function", {}).get("arguments", "{}")
                    tool_id = tc.get("id") or f"call_{assistant_message_id}_{len(tool_results)}"

                    try:
                        args = json.loads(args_str) if args_str else {}
                    except:
                        args = {}

                    # 发送工具调用开始事件
                    yield f"data: {json.dumps({'tool_call': {'tool_call_id': tool_id, 'tool_name': tool_name, 'status': 'running', 'args': args, 'round': round_no}}, ensure_ascii=False)}\n\n"

                    # 记录工具调用
                    reasoning_text = logger.write_tool_call(tool_id, tool_name, args)
                    if segment_sink:
                        if reasoning_text:
                            await segment_sink.on_reasoning(reasoning_text)
                        await segment_sink.on_tool_start(tool_name)

                    # 执行工具（注入 session 的工作目录）
                    # 使用 run_in_executor 避免阻塞事件循环，使前端 WebSocket/PTY 输出能正常工作
                    loop = asyncio.get_running_loop()
                    invocation_id = f"{session_id}:{tool_id}"
                    try:
                        result = await asyncio.wait_for(
                            loop.run_in_executor(
                                None,
                                lambda tn=tool_name, a=args, wd=work_dir, sid=session_id, iid=invocation_id: execute_tool(
                                    tn, a, work_dir=wd, session_id=sid, invocation_id=iid
                                ),
                            ),
                            timeout=TOOL_EXECUTION_TIMEOUT_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        _cancel_cli_invocations()
                        result = {
                            "success": False,
                            "error": "Tool execution timed out",
                            "output": (
                                f"工具 `{tool_name}` 执行超时（>{int(TOOL_EXECUTION_TIMEOUT_SECONDS)} 秒）。"
                                "Playwright 等浏览器任务可能页面加载过慢，请减少 wait_ms 或拆分步骤。"
                            ),
                        }

                    if isinstance(result, dict) and result.get("requires_confirmation"):
                        confirm_event = {
                            "confirmation_required": {
                                "tool_call_id": tool_id,
                                "tool_name": tool_name,
                                "command": result.get("command", ""),
                                "danger_info": result.get("danger_info", ""),
                                "danger_types": result.get("danger_types", []),
                                "args": args,
                                "round": round_no,
                            }
                        }
                        # 必须先注册等待，再推送确认事件，避免用户秒点接受时 404
                        register_confirmation_wait(tool_id)
                        yield f"data: {json.dumps(confirm_event, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'tool_result': {'tool_name': tool_name, 'status': 'pending_confirmation', 'output': '等待用户确认危险命令…', 'round': round_no}}, ensure_ascii=False)}\n\n"

                        confirmed = await wait_for_confirmation_with_cancel(
                            tool_id,
                            cancel_event=cancel_event,
                            timeout=CONFIRMATION_TIMEOUT_SECONDS,
                        )
                        stream_stopped = bool(cancel_event and cancel_event.is_set())
                        if stream_stopped or not confirmed:
                            result = {
                                "success": False,
                                "error": "Stream stopped" if stream_stopped else "User cancelled",
                                "output": "用户已停止生成" if stream_stopped else "用户取消了危险命令执行",
                                "requires_confirmation": False,
                            }
                        else:
                            retry_args = dict(args)
                            retry_args["skip_confirmation"] = True
                            yield f"data: {json.dumps({'tool_call': {'tool_call_id': tool_id, 'tool_name': tool_name, 'status': 'running', 'args': retry_args, 'round': round_no}}, ensure_ascii=False)}\n\n"
                            result = await loop.run_in_executor(
                                None,
                                lambda tn=tool_name, a=retry_args, wd=work_dir, sid=session_id: execute_tool(
                                    tn, a, work_dir=wd, session_id=sid
                                ),
                            )

                    tool_results.append({
                        "tool_call_id": tool_id,
                        "role": "tool",
                        "content": json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                    })

                    # 记录工具结果
                    status = "completed" if not isinstance(result, dict) or not result.get("error") else "error"
                    error_msg = result.get("error", "") if isinstance(result, dict) else ""
                    output = result.get("output", "") if isinstance(result, dict) else str(result)
                    logger.write_tool_result(
                        tool_id, tool_name, status,
                        result=json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                        error=error_msg
                    )
                    if segment_sink:
                        await segment_sink.on_tool_done(tool_name, status, output)

                    # 发送工具结果事件
                    yield f"data: {json.dumps({'tool_result': {'tool_name': tool_name, 'tool_call_id': tool_id, 'status': status, 'output': output, 'round': round_no}}, ensure_ascii=False)}\n\n"

                    if stream_stopped:
                        cancelled = True
                        final_content = full_content
                        break

                if cancelled:
                    break

                # 构建下一轮的消息
                assistant_msg = {
                    "role": "assistant",
                    "content": final_content if final_content else None,
                    "tool_calls": tool_calls_buffer
                }
                current_messages.append(assistant_msg)

                for tr in tool_results:
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tr["tool_call_id"],
                        "content": tr["content"]
                    })
    finally:
        # 收尾：取消/异常时主动终止所有 ps1/cmd 调度进程 + 清空 temp/cli_runtime 残留
        if cancelled:
            _cancel_cli_invocations()
        if assistant_message_id is not None and logger is not None:
            # 保存到数据库（即使中途暂停/异常也要保存已有内容）
            reasoning_text, assistant_text = logger.flush_assistant_round()
            if segment_sink:
                from services.platform_segment import emit_logger_segments
                await emit_logger_segments(
                    segment_sink,
                    reasoning=reasoning_text,
                    assistant=assistant_text,
                )
            db_content = logger.build_db_content() or final_content or ""
            if db_content:
                set_summary_block(snapshot, db_content)
                finalize_snapshot(snapshot)
            elif cancelled:
                logger.flush_reasoning_segment()

            stop_note = "（用户中断）" if cancelled and not db_content else ""
            update_message(
                assistant_message_id,
                content=db_content or stop_note or "（无响应）",
                message_snapshot_json=logger.jsonl_path_str(),
                reasoning_content=logger.build_db_reasoning()
            )

            logger.finalize()
