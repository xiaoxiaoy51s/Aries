import json
import os
import platform
import asyncio
import uuid
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from services.platform_segment import PlatformStreamSink

from utils.url_utils import normalize_base_url
from utils.skills_manager import (
    discover_skills,
    get_all_tool_definitions,
    build_skills_context_from_entries,
)
from utils.agent_tools import execute_async as execute_tool
from utils.message_snapshot import (
    create_assistant_snapshot,
    set_summary_block,
    finalize_snapshot,
)
from utils.session_logger import SessionLogger
from utils.token_counter import extract_usage_from_stream_chunk
from memory.agent_memory import build_agent_memory_system_section
from db.chat import save_message, update_message
from prompt import CODING_BEHAVIOR_RULES
from prompt.edit_code_prompts import build_optimized_edit_prompt

# 工具调用轮次上限：100 轮足够完成复杂任务（重构+测试验证）。
# 另有连续相同工具检测（REPEAT_TOOL_LIMIT=8）防止 AI 卡在循环里。
MAX_TOOL_ROUNDS = 100
# 连续调用相同工具名超过此次数，判定为卡在循环，立即停止
REPEAT_TOOL_LIMIT = 8
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


_HINT_PREFIXES = (
    "【系统提醒】你当前已接近本地工具调用上限",
    "【系统提醒】检测到连续",
)


def _pop_limit_hint_message(messages: list[dict[str, Any]]) -> None:
    """移除临时追加的系统提示（工具上限/重复检测），避免污染会话历史。"""
    if messages and messages[-1].get("role") == "system":
        content = messages[-1].get("content", "")
        if isinstance(content, str) and any(content.startswith(p) for p in _HINT_PREFIXES):
            messages.pop()


def _cancel_cli_invocations() -> None:
    """[已弃用] 保留为 no-op 兼容旧引用，不再在用户停止 / AI 完成时强制清理控制台。

    改造原因：用户希望 IDE 风格的控制台回放，PTY / ps1 调度进程在用户主动关闭
    对应 ConsolePanel 之前都不应被强制终止。软件关闭时的兜底清理由
    `backend/main.py` 的 lifespan 统一处理。
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


def build_agent_system_prompt_parts(
    skills_context: str,
    work_dir: str | None = None,
    session_id: str | None = None,
    mcp_context: str = "",
    subagents_context: str = "",
) -> dict[str, str]:
    """构建 Agent 模式的系统提示词，并按"功能模块"分块返回。

    返回 dict:
        base: 身份/会话/工作目录/输出规范/Skill 使用规范（不含 skills 详情、rules、mcp）
        rules: 用户 rules.md + AI 项目记忆（agent.md）
        skills: 已安装本地 Skills 详情
        mcp: MCP 插件描述
        subagents: 可委派的子 Agent 精简路由表
        full: 拼接完整 system prompt（与旧版一致）
    """
    from pathlib import Path
    today_str = datetime.now().strftime("%Y-%m-%d")

    if work_dir and work_dir.strip():
        wd = str(Path(work_dir).expanduser().resolve())
        tmp_dir = str(Path(wd) / ".Aries_tmp")
        target_note = wd
    else:
        wd_path = Path.home() / ".Aries" / "work_dir"
        wd_path.mkdir(parents=True, exist_ok=True)
        wd = str(wd_path)
        tmp_dir = str(Path.home() / ".Aries" / "tmp")
        target_note = wd

    base = (
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
        "在使用skill前，必须阅读SKILL.md文件，了解技能的用途和使用方法。不要直接上来就调用工具，有些工具虽然可以通过描述知道对应的使用方法，但是md文件中会有更加详细的使用说明。\n"
        "\n"
        + CODING_BEHAVIOR_RULES
        + "\n\n"
        + build_optimized_edit_prompt(
            has_replace_string=True,
            has_multi_replace=True,
            has_apply_patch=True,
        )
    )

    # Subagent 使用规范仅在确有可用 subagent 时注入，避免浪费上下文
    SUBAGENT_USAGE_RULES = (
        "\n"
        "# Subagent 使用规范\n"
        "下方「Available Subagents」列出了系统中可委派的子 Agent。每个 Subagent 拥有独立上下文与能力组合，适合复杂、多步、可被打包成角色的任务。\n"
        "- 选择 Subagent 前若需要了解可组合的 skill / mcp 全集，请调用 capability_search 工具检索（它会返回包括 disabled / unavailable 状态在内的所有能力）。\n"
        "- 你也可以基于检索结果生成新的 Subagent 配置文件（写到 ~/.Aries/agent/<name>.json）。\n"
        "\n"
        "# Subagent 调用约束\n"
        "- 通过 `delegate_to_subagent` 工具委派任务。委派时 task 必须详尽，子 Agent 看不到当前对话历史。\n"
        "- 子 Agent 一次性返回最终结果（result 或 error），不能交互式追问；它会通过自己的 `report_to_main` 工具提交结论。\n"
        "- 何时委派：复杂多步任务、需要保护主上下文不被淹没、独立可并行的子查询。\n"
        "- 何时不要委派：简单任务、答案已知、必须串行依赖前序结果、能用一两个工具直接搞定。\n"
        "- 同一轮 tool_calls 中可以并发委派多个不同 Subagent，它们会被真正并行执行；返回后用一段简洁文字向用户汇报整合结论。\n"
        "- 并行委派多个会修改文件的 Subagent 时，建议设置 `isolation: \"worktree\"` 参数，让每个子 Agent 在独立的 git worktree 中工作，避免写入冲突。\n"
    )

    rules = build_agent_memory_system_section(wd) or ""

    skills_section = ""
    if skills_context:
        skills_section = "\n# 已安装的本地 Skills\n" + skills_context

    mcp_section = ""
    if mcp_context:
        mcp_section = f"\n# MCP 插件\n{mcp_context}"

    subagents_section = ""
    if subagents_context:
        subagents_section = SUBAGENT_USAGE_RULES + "\n" + subagents_context

    full = base + rules + subagents_section + skills_section + mcp_section

    return {
        "base": base,
        "rules": rules,
        "skills": skills_section,
        "mcp": mcp_section,
        "subagents": subagents_section,
        "full": full,
    }


def build_agent_system_prompt(
    skills_context: str,
    work_dir: str | None = None,
    session_id: str | None = None,
    mcp_context: str = "",
    subagents_context: str = "",
) -> str:
    """构建 Agent 模式的系统提示词（精简版）

    work_dir: 当前 session 的工作目录；为空时回退到默认 ~/.Aries/work_dir
    session_id: 当前会话 ID；每次用户发消息时传入，供 AI 识别来源与默认推送目标
    """
    return build_agent_system_prompt_parts(
        skills_context=skills_context,
        work_dir=work_dir,
        session_id=session_id,
        mcp_context=mcp_context,
        subagents_context=subagents_context,
    )["full"]


def get_agent_skills_and_tools():
    from utils.mcp_runtime import build_mcp_prompt_context
    from utils.subagent_manager import build_subagent_router_section
    from utils.main_agent_config import get_main_agent_allowed_skills

    allowed_skills = get_main_agent_allowed_skills()
    all_skills = discover_skills()
    # 主 Agent 只加载 allowed_skills 中配置的技能
    if allowed_skills:
        enabled_skills = [s for s in all_skills if s.folder_name in allowed_skills]
    else:
        enabled_skills = []
    skills_context = build_skills_context_from_entries(enabled_skills)
    tool_definitions = get_all_tool_definitions()
    mcp_context = build_mcp_prompt_context()
    subagents_context = build_subagent_router_section()

    # 虚拟工具分组（#7）：工具数过多时自动分组，减少 prompt token 占用
    try:
        from utils.tool_grouper import maybe_group_tools
        tool_definitions, group_context = maybe_group_tools(tool_definitions)
        if group_context:
            # 分组说明拼到 skills_context 中，随 system prompt 注入
            skills_context = (skills_context or "") + "\n\n" + group_context
    except Exception:
        pass

    return skills_context, tool_definitions, mcp_context, subagents_context


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
        logger.set_model(getattr(request, "model", "") or "")
        context_token_info = base_payload.pop("context_token_info", None)  # 旧字段，仅消费占位
        breakdown_inputs = base_payload.pop("context_breakdown_inputs", None) or {}
        snapshot = create_assistant_snapshot(session_id, logger)

        skills_context, tool_definitions, mcp_context, subagents_context = get_agent_skills_and_tools()

        prompt_parts = build_agent_system_prompt_parts(
            skills_context,
            work_dir=work_dir,
            session_id=session_id,
            mcp_context=mcp_context,
            subagents_context=subagents_context,
        )
        system_prompt = prompt_parts["full"]

        # 组装功能模块化的 context usage breakdown，替代旧的按 role 分项
        from utils.token_counter import build_context_usage_breakdown
        model_name = getattr(request, "model", "") or ""
        context_breakdown = build_context_usage_breakdown(
            system_prompt_base=prompt_parts["base"]
                + (prompt_parts.get("mcp") or "")
                + (prompt_parts.get("subagents") or ""),
            tool_definitions=tool_definitions,
            rules_text=prompt_parts["rules"],
            skills_text=prompt_parts["skills"],
            summarized_messages=breakdown_inputs.get("summarized_messages") or [],
            conversation_messages=breakdown_inputs.get("conversation_messages") or [],
            model=model_name,
        )
        # 兼容字段：保留计数信息，便于前端展示
        for k in ("recent_message_count", "memory_count", "reasoning_count"):
            if breakdown_inputs.get(k) is not None:
                context_breakdown[k] = breakdown_inputs[k]
        logger.set_token_usage({"context": context_breakdown})

        # 推送初始 meta 事件（模型名 + 上下文占用），前端立即展示
        yield f"data: {json.dumps({'meta': logger.get_run_metadata()}, ensure_ascii=False)}\n\n"

        # ===== 意图识别（#2）：根据用户消息动态选择 prompt 和工具子集 =====
        intent = "agent"
        try:
            from prompt.edit_code_prompts import (
                classify_intent,
                filter_tools_for_intent,
                get_prompt_for_intent,
                INTENT_AGENT,
            )
            # 从 messages 中提取最后一条用户消息文本
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

            # 根据意图过滤工具（只读意图不加载编辑工具，减少 token）
            if intent != INTENT_AGENT:
                tool_definitions = filter_tools_for_intent(intent, tool_definitions)

            # 追加意图专用 prompt 到 system prompt
            intent_prompt = get_prompt_for_intent(intent)
            if intent_prompt:
                system_prompt = system_prompt + "\n\n" + intent_prompt

            # 推送 intent 事件给前端（UI 可展示当前模式）
            yield f"data: {json.dumps({'intent': intent}, ensure_ascii=False)}\n\n"
        except Exception:
            pass

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
            # 连续相同工具调用检测
            last_tool_name: str = ""
            repeat_count: int = 0

            for round_no in range(1, MAX_TOOL_ROUNDS + 1):
                if await _should_stop_stream(cancel_event, disconnect_check):
                    cancelled = True
                    # 不再终止 PTY / ps1 调度进程：保留控制台会话供回放
                    break

                # 第 24 轮时主动提醒 AI：本地工具调用即将达到上限，请总结已执行内容
                if round_no == MAX_TOOL_ROUNDS - 1:
                    limit_hint = (
                        "【系统提醒】你当前已接近本地工具调用上限（25 轮）。"
                        "本轮请不要再发起新的工具调用，而是总结截至目前已完成的任务内容、"
                        "已修改的文件、已验证的结果，以及剩余未完成的工作。"
                        "用精炼的语言向用户汇报进度，并告知用户如需要继续可发送「继续」。"
                    )
                    # 临时追加到 current_messages 中（作为 system 提示）
                    current_messages.append({"role": "system", "content": limit_hint})
                    # 向前端推送一个低调的提示事件，用于 UI 展示（不弹大警告）
                    yield f"data: {json.dumps({'hint': '工具调用即将达到上限，正在整理执行进度…'}, ensure_ascii=False)}\n\n"

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
                                # 不再终止 PTY / ps1 调度进程：保留控制台会话供回放
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
                    # 后台压缩检查（#6）：Agent 回复完成后，如果是暖缓存则检查是否需要压缩
                    try:
                        from memory.compaction import get_compactor
                        compactor = get_compactor()
                        compactor.maybe_trigger_compaction(
                            session_id,
                            current_messages,
                            context_window=200_000,
                            is_warm=True,  # 刚完成工具调用轮次，视为暖缓存
                        )
                    except Exception:
                        pass
                    # 清理临时追加的工具上限提示，避免污染会话历史
                    _pop_limit_hint_message(current_messages)
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
                # delegate_to_subagent 调用先收集，循环结束后并行执行
                delegate_items: list[dict[str, Any]] = []

                for tc in tool_calls_buffer:
                    stream_stopped = False
                    if await _should_stop_stream(cancel_event, disconnect_check):
                        cancelled = True
                        final_content = full_content
                        # 不再终止 PTY / ps1 调度进程：保留控制台会话供回放
                        break
                    tool_name = tc.get("function", {}).get("name", "")
                    args_str = tc.get("function", {}).get("arguments", "{}")
                    tool_id = tc.get("id") or f"call_{assistant_message_id}_{len(tool_results)}"

                    try:
                        args = json.loads(args_str) if args_str else {}
                    except:
                        args = {}

                    # ===== 收集 delegate_to_subagent 调用，稍后并行执行 =====
                    if tool_name == "delegate_to_subagent":
                        sub_name = str(args.get("subagent_name") or args.get("agent_name") or "").strip()
                        sub_task_text = str(args.get("task") or "").strip()
                        sub_desc = str(args.get("description") or "").strip()
                        sub_context = str(args.get("context") or "")
                        sub_isolation = str(args.get("isolation") or "").strip()

                        delegate_items.append({
                            "tool_id": tool_id,
                            "tool_name": tool_name,
                            "args": args,
                            "sub_name": sub_name,
                            "sub_task": sub_task_text,
                            "sub_desc": sub_desc,
                            "sub_context": sub_context,
                            "sub_isolation": sub_isolation,
                            "round": round_no,
                        })
                        # 推送 tool_call 事件 + 写 JSONL
                        tool_call_payload = {
                            'tool_call_id': tool_id,
                            'tool_name': tool_name,
                            'status': 'running',
                            'args': args,
                            'round': round_no,
                        }
                        yield f"data: {json.dumps({'tool_call': tool_call_payload}, ensure_ascii=False)}\n\n"
                        reasoning_text = logger.write_tool_call(tool_id, tool_name, args)
                        if segment_sink and reasoning_text:
                            await segment_sink.on_reasoning(reasoning_text)
                        logger.write_subagent_block(
                            tool_call_id=tool_id,
                            subagent_name=sub_name,
                            task=sub_desc or sub_task_text,
                            status="running",
                        )
                        continue
                    # ===== delegate_to_subagent 收集结束 =====

                    terminal_session_id = ""
                    if tool_name == "cli_executor":
                        want_new_terminal = bool(args.get("new_terminal"))
                        try:
                            from services.terminal_manager import TerminalManager
                            tm = TerminalManager.get_instance()
                            invocation_key = f"{session_id}:{tool_id}"
                            if want_new_terminal:
                                # AI 明确要求新开终端
                                terminal_session_id = f"ai-{uuid.uuid4().hex[:8]}"
                            else:
                                # 复用同一工作目录的 agent session
                                terminal_session_id = tm.resolve_agent_session_id(work_dir)
                            TerminalManager.register_invocation_session(invocation_key, terminal_session_id)
                        except Exception:
                            terminal_session_id = f"ai-{uuid.uuid4().hex[:8]}"

                    # 发送工具调用开始事件
                    tool_call_payload = {'tool_call_id': tool_id, 'tool_name': tool_name, 'status': 'running', 'args': args, 'round': round_no}
                    if terminal_session_id:
                        tool_call_payload['session_id'] = terminal_session_id
                    yield f"data: {json.dumps({'tool_call': tool_call_payload}, ensure_ascii=False)}\n\n"

                    # 记录工具调用
                    reasoning_text = logger.write_tool_call(tool_id, tool_name, args)
                    if segment_sink:
                        if reasoning_text:
                            await segment_sink.on_reasoning(reasoning_text)
                        await segment_sink.on_tool_start(tool_name)

                    # 执行工具（注入 session 的工作目录）
                    # 使用 execute_async 异步执行，支持用户点击"后台运行"/"停止服务"时立即中断
                    invocation_id = f"{session_id}:{tool_id}"
                    try:
                        result = await asyncio.wait_for(
                            execute_tool(
                                tool_name,
                                args,
                                work_dir=work_dir,
                                session_id=session_id,
                                invocation_id=invocation_id,
                                cancel_event=cancel_event,
                            ),
                            timeout=TOOL_EXECUTION_TIMEOUT_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        # 单次工具执行超时：只打断当前工具返回错误，不强制清理其它控制台会话
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
                            retry_payload = {'tool_call_id': tool_id, 'tool_name': tool_name, 'status': 'running', 'args': retry_args, 'round': round_no}
                            if terminal_session_id:
                                retry_payload['session_id'] = terminal_session_id
                            yield f"data: {json.dumps({'tool_call': retry_payload}, ensure_ascii=False)}\n\n"
                            result = await execute_tool(
                                tool_name,
                                retry_args,
                                work_dir=work_dir,
                                session_id=session_id,
                                invocation_id=invocation_id,
                                cancel_event=cancel_event,
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
                    _file_change = result.get("file_change") if isinstance(result, dict) else None
                    logger.write_tool_result(
                        tool_id, tool_name, status,
                        result=json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                        error=error_msg,
                        session_id=result.get("session_id", "") if isinstance(result, dict) else "",
                        file_change=_file_change,
                    )
                    if segment_sink:
                        await segment_sink.on_tool_done(tool_name, status, output)

                    # 发送工具结果事件
                    result_event: dict[str, Any] = {
                        'tool_name': tool_name,
                        'tool_call_id': tool_id,
                        'status': status,
                        'output': output,
                        'round': round_no,
                    }
                    # 如果工具返回了 session_id（终端会话），一并传给前端
                    result_session_id = result.get("session_id") if isinstance(result, dict) else None
                    if result_session_id:
                        result_event["session_id"] = result_session_id
                    # 终端 PID（PTY 进程 PID，前端可用于显示和调试）
                    result_pid = result.get("pid") if isinstance(result, dict) else None
                    if result_pid:
                        result_event["pid"] = result_pid
                    if isinstance(result, dict) and result.get("auto_detached"):
                        result_event["auto_detached"] = True
                    # 透传 file_change（用于产物区域显示 diff 和回退）
                    _file_change = result.get("file_change") if isinstance(result, dict) else None
                    if _file_change:
                        result_event["file_change"] = _file_change
                    yield f"data: {json.dumps({'tool_result': result_event}, ensure_ascii=False)}\n\n"

                    # 通过 WebSocket 推送实时 meta（duration + token_usage）
                    try:
                        from services.chat_ws import broadcast_stream_event
                        await broadcast_stream_event(session_id, {
                            "meta": logger.get_run_metadata(),
                        })
                    except Exception:
                        pass

                    if stream_stopped:
                        cancelled = True
                        final_content = full_content
                        break

                # ===== 并行执行 delegate_to_subagent 调用 =====
                if delegate_items and not cancelled:
                    from utils.subagent_runtime import run_subagent

                    # 共享事件队列：所有并行子 Agent 的事件都推到这里
                    parallel_event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

                    async def _on_parallel_subagent_event(payload: dict[str, Any]) -> None:
                        await parallel_event_queue.put(payload)

                    # 启动所有子 Agent 任务
                    sub_futures: dict[asyncio.Task, dict[str, Any]] = {}
                    for item in delegate_items:
                        run_kwargs: dict[str, Any] = dict(
                            subagent_name=item["sub_name"],
                            task=item["sub_task"],
                            context=item["sub_context"],
                            work_dir=work_dir,
                            cancel_event=cancel_event,
                            on_event=_on_parallel_subagent_event,
                        )
                        if item.get("sub_isolation"):
                            run_kwargs["isolation"] = item["sub_isolation"]
                        task_obj = asyncio.create_task(run_subagent(**run_kwargs))
                        sub_futures[task_obj] = item

                    # 等待所有子 Agent 完成，期间持续 drain 事件
                    pending_tasks = set(sub_futures.keys())
                    while pending_tasks:
                        if await _should_stop_stream(cancel_event, disconnect_check):
                            for t in pending_tasks:
                                t.cancel()
                            break
                        done, pending_tasks = await asyncio.wait(pending_tasks, timeout=0.5)
                        # Drain 事件
                        while True:
                            try:
                                ev = parallel_event_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break
                            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

                    # 兜底再 drain 一次
                    while True:
                        try:
                            ev = parallel_event_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

                    # 收集结果（保持原始 tool_call 顺序）
                    for task_obj, item in sub_futures.items():
                        tool_id = item["tool_id"]
                        tool_name = item["tool_name"]
                        sub_name = item["sub_name"]
                        sub_desc = item["sub_desc"]
                        sub_task_text = item["sub_task"]

                        try:
                            sub_result = task_obj.result()
                        except asyncio.CancelledError:
                            sub_result = {
                                "error": "用户取消了子 Agent 任务",
                                "status": "cancelled",
                                "log_path": "",
                            }
                        except Exception as exc:
                            sub_result = {
                                "error": f"子 Agent 异常：{exc}",
                                "status": "failed",
                                "log_path": "",
                            }

                        final_status = "success" if "result" in sub_result else sub_result.get("status", "failed")
                        logger.write_subagent_block(
                            tool_call_id=tool_id,
                            subagent_name=sub_name,
                            task=sub_desc or sub_task_text,
                            status=final_status,
                            log_path=str(sub_result.get("log_path") or ""),
                            final_output=str(sub_result.get("result") or ""),
                            error=str(sub_result.get("error") or ""),
                        )

                        tool_results.append({
                            "tool_call_id": tool_id,
                            "role": "tool",
                            "content": json.dumps(sub_result, ensure_ascii=False),
                        })
                        logger.write_tool_result(
                            tool_id, tool_name,
                            "completed" if final_status == "success" else "error",
                            result=json.dumps(sub_result, ensure_ascii=False),
                            error=str(sub_result.get("error") or ""),
                        )
                        yield f"data: {json.dumps({'tool_result': {'tool_name': tool_name, 'tool_call_id': tool_id, 'status': 'completed' if final_status == 'success' else 'error', 'output': sub_result.get('result') or sub_result.get('error') or '', 'round': round_no}}, ensure_ascii=False)}\n\n"
                # ===== 并行执行 delegate_to_subagent 调用结束 =====

                if cancelled:
                    break

                # 连续相同工具调用检测：防止 AI 卡在循环里反复调同一个工具
                # 本轮调用的工具名集合（去重，因为一轮可能调多个工具）
                round_tool_names = set()
                for tc in tool_calls_buffer:
                    fn = tc.get("function", {}).get("name", "")
                    if fn:
                        round_tool_names.add(fn)
                # 如果本轮只调了一种工具，且和上一轮相同，累加计数
                if len(round_tool_names) == 1:
                    single_tool = next(iter(round_tool_names))
                    if single_tool == last_tool_name:
                        repeat_count += 1
                    else:
                        last_tool_name = single_tool
                        repeat_count = 1
                else:
                    # 多种工具或无工具，重置
                    last_tool_name = ""
                    repeat_count = 0

                if repeat_count >= REPEAT_TOOL_LIMIT:
                    repeat_hint = (
                        f"【系统提醒】检测到连续 {repeat_count} 轮调用相同工具「{last_tool_name}」，"
                        "可能陷入了循环。请停止重复调用，总结当前进度和遇到的问题，"
                        "告知用户需要什么信息或帮助来继续。"
                    )
                    current_messages.append({"role": "system", "content": repeat_hint})
                    yield f"data: {json.dumps({'hint': f'检测到重复调用 {last_tool_name}，正在整理进度…'}, ensure_ascii=False)}\n\n"
                    # 下一轮让 AI 总结（不再发 system hint，和 step_limit 一样的策略）
                    # 重置计数，避免下一轮又被触发
                    repeat_count = 0
                    last_tool_name = ""

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

                # ===== 实时上下文压缩 =====
                # 100 轮工具调用会累积大量历史，每轮检测并在超阈值时同步压缩。
                # 压缩策略：保留 system prompt + 最近窗口，旧消息替换为摘要。
                try:
                    from memory.compaction import should_compact, split_messages_for_compaction, build_session_summary
                    from utils.token_counter import estimate_message_tokens
                    if should_compact(current_messages):
                        to_compact, to_keep = split_messages_for_compaction(current_messages)
                        if to_compact and len(to_compact) > 4:
                            # 生成摘要
                            summary = build_session_summary(to_compact)
                            # 构建压缩后的消息列表：system + 摘要 + 近期窗口
                            system_msgs = [m for m in current_messages if m.get("role") == "system"]
                            compacted = system_msgs + [
                                {
                                    "role": "system",
                                    "content": f"## 之前的对话摘要\n\n{summary}\n\n---\n以上是之前对话的摘要，以下是最近的对话内容："
                                }
                            ] + to_keep
                            old_count = len(current_messages)
                            old_tokens = sum(estimate_message_tokens(m) for m in current_messages)
                            current_messages[:] = compacted
                            new_tokens = sum(estimate_message_tokens(m) for m in current_messages)
                            if logger:
                                logger.write_info_event(
                                    "context_compacted",
                                    f"工具循环中压缩上下文：{old_count} → {len(current_messages)} 条消息，"
                                    f"约 {old_tokens} → {new_tokens} tokens",
                                    details=json.dumps({"old_count": old_count, "new_count": len(current_messages), "old_tokens": old_tokens, "new_tokens": new_tokens}, ensure_ascii=False),
                                )
                            # 推送 hint 给前端
                            yield f"data: {json.dumps({'hint': '上下文已自动压缩，继续执行…'}, ensure_ascii=False)}\n\n"
                except Exception:
                    pass
            else:
                # 达到工具调用上限（第 25 轮）。
                # 由于第 24 轮已提醒 AI 总结进度，这里不再弹丑陋的系统警告，
                # 只清理临时提示并静默结束，让 AI 上一次返回的内容作为最终结果。
                _pop_limit_hint_message(current_messages)
                if logger:
                    logger.write_error_event(
                        "step_limit_exceeded",
                        f"工具调用达到上限（{MAX_TOOL_ROUNDS} 轮），已在前一轮引导 AI 总结进度。"
                    )
    finally:
        # 用户主动中断时不再终止 PTY / ps1 调度进程：
        # 控制台会话（包括正在运行的开发服务器、长任务）保留可见、可回放。
        # 兜底清理只在软件关闭时由 main.py 的 lifespan 统一处理。
        if assistant_message_id is not None and logger is not None:
            # 记录中断事件到日志（如果是因为中断而非正常结束）
            if cancelled:
                logger.write_info_event(
                    "stream_interrupted",
                    "用户中断或连接断开，正在保存已有进度到数据库",
                )
            # 刷新所有未写入的缓冲
            reasoning_text, assistant_text = logger.flush_assistant_round()
            # 清理临时 system hint 消息
            _pop_limit_hint_message(current_messages)
            if segment_sink:
                from services.platform_segment import emit_logger_segments
                await emit_logger_segments(
                    segment_sink,
                    reasoning=reasoning_text,
                    assistant=assistant_text,
                )
            # 构建数据库内容：优先用 assistant 文本，
            # 如果为空（被打断在工具执行中间），用最近一轮的 reasoning + 工具摘要
            db_content = logger.build_db_content() or final_content or ""
            if not db_content and cancelled:
                # 被中断且没有 assistant 文本：用 reasoning 和工具摘要作为内容
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
            elif cancelled and db_content:
                stop_note = ""
            update_message(
                assistant_message_id,
                content=db_content or stop_note or "（无响应）",
                message_snapshot_json=logger.jsonl_path_str(),
                reasoning_content=logger.build_db_reasoning()
            )

            # 推送最终 meta 事件（含处理时长 + token 使用），前端更新展示
            yield f"data: {json.dumps({'meta': logger.get_run_metadata()}, ensure_ascii=False)}\n\n"

            logger.finalize()
