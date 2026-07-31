"""QQ / 微信 / 飞书 固定会话的消息处理（适配 cloud 后端）。

对齐参考 backend：
- Agent + DB 跑在独立 PlatformAgentLoop（避开飞书 SDK 劫持 get_event_loop）
- 平台回复不在 agent 过程中按 token 推送
- Agent 结束后，在 bot 自身 loop 上按 JSONL 的每个 assistant_text 段落逐块推送
"""

from __future__ import annotations

import asyncio
import logging
import threading
import traceback
from concurrent.futures import Future

from sqlalchemy import select

from app.database import async_session_for_loop
from app.model.user import User
from app.service.model_config_service import ModelConfigService
from app.service.session_service import SessionService
from app.services.platform_segment import push_final_reply
from app.utils.session_logger import read_jsonl_events

_log = logging.getLogger(__name__)

PLATFORM_NAMES = {"qq": "QQ", "wechat": "微信", "feishu": "飞书"}

_platform_futures: dict[str, Future] = {}
_platform_cancel_flags: dict[str, threading.Event] = {}
_shutting_down = False

_agent_loop: asyncio.AbstractEventLoop | None = None
_agent_thread: threading.Thread | None = None
_agent_ready = threading.Event()
_agent_lock = threading.Lock()


def session_id_for(platform: str, email: str = "") -> str:
    from app.service.scheduled_task_service import session_id_for as _sid

    return _sid(platform, email)


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """兼容旧接口。"""
    return


def mark_shutting_down() -> None:
    global _shutting_down
    _shutting_down = True
    for flag in list(_platform_cancel_flags.values()):
        flag.set()
    loop = _agent_loop
    if loop and loop.is_running():
        loop.call_soon_threadsafe(loop.stop)


def ensure_agent_loop() -> asyncio.AbstractEventLoop:
    """确保 PlatformAgentLoop 线程已启动。"""
    global _agent_loop, _agent_thread
    with _agent_lock:
        if _agent_loop is not None and _agent_loop.is_running():
            return _agent_loop

        _agent_ready.clear()

        def _run() -> None:
            global _agent_loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _agent_loop = loop
            _agent_ready.set()
            loop.run_forever()
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

        _agent_thread = threading.Thread(
            target=_run, daemon=True, name="PlatformAgentLoop"
        )
        _agent_thread.start()

    if not _agent_ready.wait(timeout=5):
        raise RuntimeError("PlatformAgentLoop 启动超时")
    assert _agent_loop is not None
    return _agent_loop


async def _await_future(fut: Future):
    while not fut.done():
        await asyncio.sleep(0.05)
        if _shutting_down:
            fut.cancel()
            raise asyncio.CancelledError("服务正在关闭")
    return fut.result()


async def _cancel_platform_task(platform: str) -> None:
    prev_fut = _platform_futures.pop(platform, None)
    prev_flag = _platform_cancel_flags.pop(platform, None)
    if prev_flag:
        prev_flag.set()
    if prev_fut and not prev_fut.done():
        _log.info("[平台 %s] 新消息到达，取消上一轮对话", platform)
        prev_fut.cancel()
        try:
            await asyncio.wait_for(_await_future(prev_fut), timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
            pass


async def _resolve_bot_user(db):
    from app.services.bot_manager import get_bot_user_email

    email = get_bot_user_email()
    if email:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            return user

    result = await db.execute(select(User).limit(100))
    users = result.scalars().all()
    if not users:
        return None
    for user in users:
        model = await ModelConfigService.get_active_model(user.email)
        if model:
            return user
    return users[0]


def _assistant_segments_from_log(log_path: str) -> list[str]:
    """读取 JSONL 中每一段完整 assistant_text（非整 token）。"""
    if not log_path:
        return []
    events = read_jsonl_events(log_path)
    segments: list[str] = []
    for ev in events:
        if ev.get("type") != "assistant_text":
            continue
        body = (ev.get("text") or "").strip()
        if body:
            segments.append(body)
    return segments


async def _send_error(send_segment, message: str) -> None:
    if not send_segment or not message:
        return
    try:
        await send_segment(message)
    except Exception as e:
        _log.warning("[平台] 错误消息推送失败: %s", e)


async def _run_agent_for_platform(
    platform: str,
    user_text: str,
    *,
    cancel_flag: threading.Event,
) -> tuple[str | None, str, str]:
    """在 PlatformAgentLoop 上跑 Agent（不推送平台），返回 (email, log_path, early_error)。"""
    from app.service.chat_service import ChatService

    session_maker = async_session_for_loop()

    if _shutting_down:
        return None, "", "（服务正在关闭，请稍后重试）"

    async with session_maker() as db:
        user = await _resolve_bot_user(db)
        if not user:
            return None, "", "（系统未注册用户，请在网页端注册后重试）"
        model = await ModelConfigService.get_active_model(user.email)
        if not model:
            return None, "", "（AI 未配置，请先在设置中添加模型并激活）"

        sid = session_id_for(platform, user.email)
        session = await SessionService.get_session(db, sid)
        if not session:
            title = f"{PLATFORM_NAMES.get(platform, platform)} Bot"
            await SessionService.create_session(
                db, sid, user.id, title, user_email=user.email, workspace_dir="default"
            )
            _log.info("[平台 %s] 已创建会话 %s", platform, sid)

        assistant_log_path = ""
        # 不传 segment_sink：避免跨 loop 实时推送；结束后按 JSONL 整段发送
        async for _sse in ChatService.chat_stream(
            db,
            user.email,
            user.id,
            sid,
            user_text,
            platform=platform,
            segment_sink=None,
            cancel_event=cancel_flag,
        ):
            if cancel_flag.is_set():
                break

        messages = await SessionService.get_messages(db, sid)
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("log_path"):
                assistant_log_path = msg["log_path"]
                break

        return user.email, assistant_log_path, ""


async def process_inbound_message_async(
    platform: str,
    text: str,
    send_segment=None,
) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    if _shutting_down:
        _log.warning("[平台 %s] 服务正在关闭，跳过消息处理", platform)
        return ""

    _log.info("[平台 %s] 收到消息: %s", platform, text[:120])

    await _cancel_platform_task(platform)

    cancel_flag = threading.Event()
    _platform_cancel_flags[platform] = cancel_flag

    agent_loop = ensure_agent_loop()
    fut = asyncio.run_coroutine_threadsafe(
        _run_agent_for_platform(platform, text, cancel_flag=cancel_flag),
        agent_loop,
    )
    _platform_futures[platform] = fut

    try:
        user_email, assistant_log_path, early_error = await _await_future(fut)

        if early_error:
            await _send_error(send_segment, early_error)
            return early_error if not send_segment else ""

        if not user_email:
            msg = "（系统未注册用户，请在网页端注册后重试）"
            await _send_error(send_segment, msg)
            return msg if not send_segment else ""

        segments = _assistant_segments_from_log(assistant_log_path)
        reply = "\n\n".join(segments).strip()
        _log.info("[平台 %s] 回复段数=%s 总长=%s", platform, len(segments), len(reply))

        # 按 JSONL 中每个 assistant_text 段落逐块发送（每段内部仍按平台上限拆分）
        if send_segment and segments:
            for seg in segments:
                try:
                    await push_final_reply(send_segment, seg)
                except Exception as e:
                    _log.warning("[平台 %s] 推送失败: %s", platform, e)
                    break
            _log.info("[平台 %s] 回复推送完成", platform)

        return reply if not send_segment else ""

    except asyncio.CancelledError:
        _log.info("[平台 %s] 对话已被新消息取消", platform)
        await _send_error(send_segment, "（上一轮对话已取消，正在处理新消息）")
        return ""
    except Exception:
        _log.error("[平台 %s] agent 失败:\n%s", platform, traceback.format_exc())
        msg = "（Agent 执行异常，请检查后端日志）"
        await _send_error(send_segment, msg)
        return msg if not send_segment else ""
    finally:
        if _platform_futures.get(platform) is fut:
            _platform_futures.pop(platform, None)
        if _platform_cancel_flags.get(platform) is cancel_flag:
            _platform_cancel_flags.pop(platform, None)
