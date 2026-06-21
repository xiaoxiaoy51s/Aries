"""QQ / 微信 / 飞书 固定会话的消息处理（仅 agent 模式）。"""

import asyncio
import json
import logging
import os
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import httpx

from api.modes.agent_mode import (
    build_agent_system_prompt,
    get_agent_skills_and_tools,
    stream_agent_mode,
)
from db.chat import get_conversation_history, get_recent_messages, save_message
from db.sessions import get_session
from models.model_manager import resolve_active_model_config
from services.chat_ws import broadcast_stream_event, notify_new_message, notify_session_update
from services.platform_segment import PlatformStreamSink
from utils.url_utils import normalize_base_url

_log = logging.getLogger(__name__)

SendSegmentFn = Callable[[str], Awaitable[None]]

PLATFORMS = ("qq", "wechat", "feishu")
HISTORY_ROUNDS = 14
HISTORY_LIMIT = HISTORY_ROUNDS * 2
REASONING_ROUNDS = 2
ASSISTANT_MAX_LEN = 2000

# 每个平台当前进行中的任务和取消事件
_platform_tasks: dict[str, asyncio.Task] = {}
_platform_cancel_events: dict[str, asyncio.Event] = {}


def session_id_for(platform: str) -> str:
    return f"__{platform}__"


def _platform_system_extra(platform: str) -> str:
    names = {"qq": "QQ", "wechat": "微信", "feishu": "飞书"}
    label = names.get(platform, platform)
    return (
        f" You are chatting via {label}. Please answer in a concise and helpful way."
        " Use Chinese unless the user asks otherwise."
        " You are in AGENT mode: you MUST use available tools (web search, cli, skills) to complete tasks."
        " Do NOT say you are in plain text mode or cannot use tools."
        " When the user asks to create/save a file, use tools to write it to the work directory."
    )


async def _cancel_platform_task(platform: str) -> None:
    """取消指定平台正在进行的对话任务。"""
    prev_task = _platform_tasks.get(platform)
    if prev_task and not prev_task.done():
        _log.info("[平台 %s] 新消息到达，取消上一轮对话", platform)
        prev_event = _platform_cancel_events.get(platform)
        if prev_event:
            prev_event.set()
        prev_task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(prev_task), timeout=3.0)
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
            pass
    _platform_tasks.pop(platform, None)
    _platform_cancel_events.pop(platform, None)


async def run_agent_async(platform: str, text: str) -> str:
    base_url, api_key, model = resolve_active_model_config()
    if not base_url or not api_key:
        return "（AI 未配置，请先在设置中填写 API Key 和 Base URL）"

    session_id = session_id_for(platform)
    return await run_agent_in_session(session_id, text)


async def run_agent_in_session(
    session_id: str,
    text: str,
    segment_sink: Optional[PlatformStreamSink] = None,
    cancel_event: Optional[asyncio.Event] = None,
    skip_save_user: bool = False,
) -> str:
    """在指定 session 中以 agent 模式跑一轮对话，返回最终助手回复。

    适用于：项目会话、平台会话（__wechat__/__feishu__/__qq__）、定时任务等。
    会自动加载该 session 的历史消息作为上下文，调用 stream_agent_mode 跑完整 agent 循环，
    并把 user / assistant 消息持久化到 chat_messages。
    """
    base_url, api_key, model = resolve_active_model_config()
    if not base_url or not api_key:
        return "（AI 未配置，请先在设置中填写 API Key 和 Base URL）"

    _meta = get_session(session_id) or {}
    work_dir = (_meta.get("work_dir") or "").strip() or None

    if not skip_save_user:
        save_message(session_id, "user", text, mode="agent")

    skills_context, _, mcp_context, subagents_context = get_agent_skills_and_tools()
    system_prompt = build_agent_system_prompt(
        skills_context,
        work_dir=work_dir,
        session_id=session_id,
        mcp_context=mcp_context,
        subagents_context=subagents_context,
    )

    # 平台会话追加额外提示
    if session_id in (session_id_for("wechat"), session_id_for("qq"), session_id_for("feishu")):
        platform = (
            "wechat" if session_id == session_id_for("wechat")
            else "qq" if session_id == session_id_for("qq")
            else "feishu"
        )
        system_prompt += _platform_system_extra(platform)

    from db.chat import build_agent_reasoning_context

    history = get_conversation_history(
        session_id,
        limit=HISTORY_LIMIT,
        max_assistant_len=ASSISTANT_MAX_LEN,
        include_last=False,
    )
    messages = [{"role": "system", "content": system_prompt}]
    reasoning_ctx = build_agent_reasoning_context(session_id, rounds=REASONING_ROUNDS)
    if reasoning_ctx:
        messages.append(reasoning_ctx)
    messages.extend(history)
    messages.append({"role": "user", "content": text})

    request = SimpleNamespace(
        baseUrl=base_url, apiKey=api_key, model=model,
        public_url="", temperature=None, max_tokens=None
    )
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {"model": model, "messages": messages, "stream": True}

    async for sse_line in stream_agent_mode(
        request, messages, headers, payload, session_id,
        work_dir=work_dir,
        segment_sink=segment_sink,
        cancel_event=cancel_event,
    ):
        # 解析 SSE 事件并转发给前端 WebSocket
        if sse_line.startswith("data: "):
            raw = sse_line[6:].strip()
            if raw and raw != "[DONE]":
                try:
                    event_data = json.loads(raw)
                    await broadcast_stream_event(session_id, event_data)
                except (json.JSONDecodeError, Exception):
                    pass

    recent = get_recent_messages(session_id, limit=1)
    for msg in reversed(recent):
        if msg.get("role") == "assistant" and (msg.get("content") or "").strip():
            return msg["content"].strip()

    return "（Agent 未生成有效回复）"


def run_agent_sync(platform: str, text: str) -> str:
    try:
        return asyncio.run(run_agent_async(platform, text))
    except Exception as e:
        _log.error("[平台 %s] agent 调用失败: %s", platform, e)
        return f"（Agent 执行失败: {e}）"


def extract_files_from_reply(reply: str) -> list[str]:
    if not reply:
        return []
    home = Path.home() / ".Aries"
    found: list[str] = []
    pattern = re.compile(
        r"[`\"']?([^\s`\"'<>|]+\.(?:txt|md|pdf|docx|xlsx|csv|json|png|jpg|jpeg))[`\"']?",
        re.I,
    )
    for match in pattern.finditer(reply):
        raw = match.group(1).strip().strip("`'\"")
        for cand in (Path(raw), home / raw):
            try:
                if cand.is_file():
                    found.append(str(cand.resolve()))
                    break
            except Exception:
                pass
    return list(dict.fromkeys(found))


async def process_inbound_message_async(
    platform: str,
    text: str,
    send_segment: Optional[SendSegmentFn] = None,
) -> tuple[str, list[str]]:
    """处理平台消息 - 自动取消同平台上一轮对话。

    当同一平台的新消息到达时，会先取消正在进行的对话任务，
    然后开始处理新消息。流式输出通过 send_segment 回调实时推送到平台。
    """
    text = (text or "").strip()
    if not text:
        return "", []

    sid = session_id_for(platform)

    # 取消同平台上一轮对话
    await _cancel_platform_task(platform)

    # 创建本轮的取消事件
    cancel_event = asyncio.Event()
    _platform_cancel_events[platform] = cancel_event

    # 注册当前任务
    current_task = asyncio.current_task()
    if current_task:
        _platform_tasks[platform] = current_task

    segment_sink = PlatformStreamSink(send_segment) if send_segment else None

    try:
        # 先保存用户消息到 DB，再通知前端加载
        save_message(sid, "user", text, mode="agent")
        await notify_new_message(sid, "user", text)

        reply = await run_agent_in_session(
            sid,
            text,
            segment_sink=segment_sink,
            cancel_event=cancel_event,
            skip_save_user=True,
        )
        # 通知前端：AI 回复已完成
        await notify_session_update(sid)
    except asyncio.CancelledError:
        _log.info("[平台 %s] 对话已被新消息取消", platform)
        # 被取消时也通知前端刷新（已有部分内容已保存到 DB）
        await notify_session_update(sid)
        if send_segment:
            try:
                await send_segment("（上一轮对话已取消，正在处理新消息）")
            except Exception:
                pass
        return "", []
    except Exception as e:
        _log.error("[平台 %s] agent 调用失败: %s", platform, e)
        reply = f"（Agent 执行失败: {e}）"
        if send_segment:
            try:
                await send_segment(reply)
            except Exception:
                pass
        await notify_session_update(sid)
    finally:
        # 清理任务注册（仅当当前任务仍注册时）
        if _platform_tasks.get(platform) is current_task:
            _platform_tasks.pop(platform, None)
        if _platform_cancel_events.get(platform) is cancel_event:
            _platform_cancel_events.pop(platform, None)

    files = extract_files_from_reply(reply)
    # 已分段推送时不再重复发送完整回复
    if send_segment:
        return "", files
    return reply, files


def process_inbound_message(platform: str, text: str) -> tuple[str, list[str]]:
    """同步入口（向后兼容）。"""
    return asyncio.run(process_inbound_message_async(platform, text))
