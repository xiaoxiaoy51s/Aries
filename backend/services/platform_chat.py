"""QQ / 微信 / 飞书 固定会话的消息处理（仅 agent 模式）。"""

import asyncio
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
from services.platform_segment import PlatformStreamSink
from utils.url_utils import normalize_base_url

_log = logging.getLogger(__name__)

SendSegmentFn = Callable[[str], Awaitable[None]]

PLATFORMS = ("qq", "wechat", "feishu")
HISTORY_ROUNDS = 14
HISTORY_LIMIT = HISTORY_ROUNDS * 2
REASONING_ROUNDS = 2
ASSISTANT_MAX_LEN = 2000


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

    save_message(session_id, "user", text, mode="agent")

    skills_context, _ = get_agent_skills_and_tools()
    system_prompt = build_agent_system_prompt(
        skills_context, work_dir=work_dir, session_id=session_id
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

    async for _event in stream_agent_mode(
        request, messages, headers, payload, session_id,
        work_dir=work_dir,
        segment_sink=segment_sink,
    ):
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
    home = Path.home() / ".MIMOClaw"
    today_dir = home / datetime.now().strftime("%Y-%m-%d")
    found: list[str] = []
    pattern = re.compile(
        r"[`\"']?([^\s`\"'<>|]+\.(?:txt|md|pdf|docx|xlsx|csv|json|png|jpg|jpeg))[`\"']?",
        re.I,
    )
    for match in pattern.finditer(reply):
        raw = match.group(1).strip().strip("`'\"")
        for cand in (Path(raw), home / raw, today_dir / Path(raw).name):
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
    text = (text or "").strip()
    if not text:
        return "", []

    segment_sink = PlatformStreamSink(send_segment) if send_segment else None

    try:
        reply = await run_agent_in_session(
            session_id_for(platform),
            text,
            segment_sink=segment_sink,
        )
    except Exception as e:
        _log.error("[平台 %s] agent 调用失败: %s", platform, e)
        reply = f"（Agent 执行失败: {e}）"
        if send_segment:
            await send_segment(reply)

    files = extract_files_from_reply(reply)
    # 已分段推送时不再重复发送完整回复
    if send_segment:
        return "", files
    return reply, files


def process_inbound_message(platform: str, text: str) -> tuple[str, list[str]]:
    """同步入口（微信等阻塞线程）。"""
    return asyncio.run(process_inbound_message_async(platform, text))
