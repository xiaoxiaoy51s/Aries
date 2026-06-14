import json
import os
import platform
import asyncio
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any, Optional

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


def build_agent_system_prompt(skills_context: str, work_dir: str | None = None) -> str:
    """构建 Agent 模式的系统提示词（精简版）

    work_dir: 当前 session 的工作目录；为空时回退到默认 ~/.MIMOClaw
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
        "⚠️ 文件操作必须先判断是否有专用 skill！\n"
        "优先级：专用 skill > cli_executor + 脚本 > 自己写代码\n"
        f"脚本位置：`{Path.home() / '.MIMOClaw' / 'skills'}`\n"
        "- Skill 分两种类型：\n"
        "  1. 有脚本的 skill（如 pdf/docx/xlsx/pptx）：通过 cli_executor 调用 scripts 目录下的脚本\n"
        "  2. 纯文档 skill（如 ui-ux-pro-max）：只有 SKILL.md，直接阅读文档获取规范，无需调用脚本\n"
        "- 调用 skill 前先阅读 SKILL.md 确认类型\n"
    )

    if skills_context:
        prompt += (
            "\n# 已安装的本地 Skills\n"
            f"{skills_context}"
        )

    return prompt


def get_agent_skills_and_tools():
    skills = discover_skills()
    enabled_skills = [s for s in skills if s.enabled]
    skills_context = build_skills_context_from_entries(enabled_skills)
    tool_definitions = get_all_tool_definitions()
    return skills_context, tool_definitions


async def stream_agent_mode(
    request,
    messages: list,
    headers: dict,
    base_payload: dict,
    session_id: str,
    work_dir: str | None = None,
    cancel_event: Optional[asyncio.Event] = None,
    disconnect_check: Optional[Any] = None,
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

        skills_context, tool_definitions = get_agent_skills_and_tools()

        system_prompt = build_agent_system_prompt(skills_context, work_dir=work_dir)

        current_messages = [{"role": "system", "content": system_prompt}]
        current_messages.extend(messages)

        base_url = normalize_base_url(request.baseUrl)

        async with httpx.AsyncClient(timeout=300.0, trust_env=False) as client:
            for round_no in range(1, MAX_TOOL_ROUNDS + 1):
                if await _should_stop_stream(cancel_event, disconnect_check):
                    cancelled = True
                    _cancel_cli_invocations()
                    break
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

                async with client.stream(
                    "POST",
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=current_payload,
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        yield f"data: {json.dumps({'error': error_text.decode()})}\n\n"
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

                final_content = full_content

                if cancelled:
                    break

                if not tool_calls_buffer:
                    break

                # 本轮分析文本落盘，再执行工具（避免多轮时只保存最后一轮）
                logger.flush_assistant_round()

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
                    logger.write_tool_call(tool_id, tool_name, args)

                    # 执行工具（注入 session 的工作目录）
                    # 使用 run_in_executor 避免阻塞事件循环，使前端 WebSocket/PTY 输出能正常工作
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(
                        None, lambda: execute_tool(tool_name, args, work_dir=work_dir)
                    )

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
                                None, lambda: execute_tool(tool_name, retry_args, work_dir=work_dir)
                            )

                    tool_results.append({
                        "tool_call_id": tool_id,
                        "role": "tool",
                        "content": json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                    })

                    # 记录工具结果
                    status = "completed" if not isinstance(result, dict) or not result.get("error") else "error"
                    error_msg = result.get("error", "") if isinstance(result, dict) else ""
                    logger.write_tool_result(
                        tool_id, tool_name, status,
                        result=json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                        error=error_msg
                    )

                    # 发送工具结果事件
                    output = result.get('output', '') if isinstance(result, dict) else str(result)
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
            logger.flush_assistant_round()
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
