"""QQ / 微信 / 飞书 主动消息推送（定时任务等场景，全局单例）"""

import asyncio
import json
import logging
import random
import time
from typing import Any

_log = logging.getLogger(__name__)

MAX_SEGMENT_LEN = 2000


def _load_bot_config() -> dict:
    import json
    from pathlib import Path
    config_path = Path.home() / ".Aries" / "bot_config.json"
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _split_text(text: str, max_len: int = MAX_SEGMENT_LEN) -> list[str]:
    segments: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        cut = remaining.rfind("\n", 0, max_len)
        if cut < max_len // 2:
            cut = max_len
        segments.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        segments.append(remaining)
    return segments or [""]


def push_wechat_message(text: str) -> bool:
    """主动推送微信消息。"""
    if not text.strip():
        _log.warning("[Push/微信] 内容为空，跳过")
        return False

    config = _load_bot_config()
    wechat = config.get("wechat", {})
    if not wechat.get("enabled"):
        _log.warning("[Push/微信] 未启用，请先在设置中绑定微信")
        return False

    bot_token = (wechat.get("bot_token") or "").strip()
    if not bot_token:
        _log.warning("[Push/微信] 缺少 bot_token")
        return False

    config_recipient = (
        (wechat.get("last_from_user_id") or "").strip()
        or (wechat.get("to_user_id") or "").strip()
    )
    config_context_token = (wechat.get("context_token") or "").strip()

    # 从运行中的 bot 获取最新的 context_token（可能比配置文件中的更新）
    runtime_token = ""
    runtime_recipient = ""
    try:
        from services.wechat_bot import _runner
        if _runner and _runner.client:
            runtime_recipient = (_runner.client.last_from_user_id or "").strip()
            runtime_token = (_runner.client.context_token or "").strip()
    except Exception:
        pass

    recipient = runtime_recipient or config_recipient
    context_token = runtime_token or config_context_token

    if not recipient:
        _log.warning("[Push/微信] 缺少收消息用户，请先用手机给 bot 发一条消息")
        return False

    segments = _split_text(text)

    # 始终用独立客户端发送，避免和 get_updates 的 HTTP 客户端冲突
    from services.wechat_bot import WeChatBotClient

    def _try_send(tok: str) -> bool:
        client = WeChatBotClient(
            bot_token=bot_token,
            to_user_id=wechat.get("to_user_id", ""),
            context_token=tok,
            last_from_user_id=recipient,
        )
        client._running = True
        try:
            for seg in segments:
                result = client.send_message(seg, to_user_id=recipient, context_token=tok)
                ret = result.get("ret", 0)
                if ret != 0:
                    _log.warning("[Push/微信] 发送失败 ret=%s result=%s", ret, result)
                    return False
            _log.info("[Push/微信] 推送成功 recipient=%s", recipient[:8])
            return True
        finally:
            client._close_client()

    # 第一次尝试：用已有的 context_token
    if context_token:
        try:
            if _try_send(context_token):
                return True
        except Exception as e:
            _log.warning("[Push/微信] 首次发送失败: %s", e)

    # 第二次尝试：通过 get_updates 刷新 context_token 后重试
    _log.info("[Push/微信] 尝试刷新 context_token")
    try:
        refresh_client = WeChatBotClient(
            bot_token=bot_token,
            to_user_id=wechat.get("to_user_id", ""),
            context_token=config_context_token,
            get_updates_buf=wechat.get("get_updates_buf", ""),
            last_from_user_id=recipient,
        )
        refresh_client._running = True
        try:
            msgs = refresh_client.get_updates()
            new_token = refresh_client.context_token or ""
            if new_token and new_token != context_token:
                _log.info("[Push/微信] context_token 已刷新")
                # 持久化新 token
                try:
                    from services.bot_manager import persist_recipient
                    persist_recipient("wechat", context_token=new_token)
                except Exception:
                    pass
                if _try_send(new_token):
                    return True
        finally:
            refresh_client._close_client()
    except Exception as e:
        _log.warning("[Push/微信] 刷新 token 失败: %s", e)

    _log.error("[Push/微信] 推送失败，可能 context_token 已过期，请先用手机给 bot 发一条消息")
    return False


async def push_feishu_message(text: str) -> bool:
    """主动推送飞书消息。"""
    if not text.strip():
        return False

    config = _load_bot_config()
    feishu = config.get("feishu", {})
    chat_id = (feishu.get("last_chat_id") or "").strip()

    # 优先使用运行中的 FeishuChannel
    try:
        from services.feishu_bot import _runner

        if _runner and _runner._channel and _runner._loop and _runner._loop.is_running():
            # 优先用运行中 bot 的实时 chat_id（收到消息时更新），配置文件可能未持久化
            effective_chat_id = (_runner.last_chat_id or "").strip() or chat_id
            if not effective_chat_id:
                _log.warning("[Push/飞书] 缺少 chat_id（请先用飞书给 bot 发一条消息以记录会话）")
                return False

            async def _send_via_channel() -> bool:
                await _runner._channel.send(effective_chat_id, {"text": text})
                return True

            future = asyncio.run_coroutine_threadsafe(_send_via_channel(), _runner._loop)
            future.result(timeout=30)
            _log.info("[Push/飞书] 推送成功（Channel）")
            return True
    except Exception as e:
        _log.warning("[Push/飞书] Channel 推送失败，尝试 REST: %s", e)

    # REST API 兜底
    if not chat_id:
        _log.warning("[Push/飞书] REST 推送缺少 chat_id（请先用飞书给 bot 发一条消息以记录会话）")
        return False
    try:
        import lark_oapi as lark
        from lark_oapi.api.im.v1.model.create_message_request import CreateMessageRequest
        from lark_oapi.api.im.v1.model.create_message_request_body import CreateMessageRequestBody

        app_id = (feishu.get("app_id") or "").strip()
        app_secret = (feishu.get("app_secret") or "").strip()
        if not app_id or not app_secret:
            return False

        client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.WARNING) \
            .build()

        content = json.dumps({"text": text}, ensure_ascii=False)
        req = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(content)
                .build()
            )
            .build()
        )
        resp = client.im.v1.message.create(req)
        if resp.success():
            _log.info("[Push/飞书] 推送成功（REST）")
            return True
        _log.error("[Push/飞书] REST 推送失败: %s", resp.msg)
        return False
    except Exception as e:
        _log.error("[Push/飞书] 推送失败: %s", e)
        return False


async def push_qq_message(text: str) -> bool:
    """主动推送 QQ 消息。"""
    if not text.strip():
        return False

    config = _load_bot_config()
    qq = config.get("qq", {})
    if not qq.get("enabled"):
        return False

    # 优先使用运行中的 bot 客户端（必须在 bot 自己的事件循环里发送，否则
    # aiohttp 的 Timeout 上下文会报 "should be used inside a task"）
    try:
        from services.qq_bot import _runner

        if _runner and _runner._client:
            loop = _runner._loop
            if not loop or not loop.is_running():
                _log.warning("[Push/QQ] bot 事件循环未运行")
                return False
            # 内存优先，配置文件回退（重启后内存为空但配置已持久化）
            chat_type = _runner._client.last_chat_type or qq.get("last_chat_type") or "c2c"
            if chat_type == "group":
                group_openid = _runner._client.last_group_openid or qq.get("last_group_openid", "")
                if not group_openid:
                    _log.warning("[Push/QQ] 缺少 last_group_openid")
                    return False
            else:
                user_openid = _runner._client.last_user_openid or qq.get("last_user_openid", "")
                if not user_openid:
                    _log.warning("[Push/QQ] 缺少 last_user_openid")
                    return False

            segments = _split_text(text)

            async def _send_all() -> None:
                if chat_type == "group":
                    for seg in segments:
                        msg_seq = int(time.time() * 1000) % 1000000 + random.randint(1, 1000)
                        await _runner._client.api.post_group_message(
                            group_openid=group_openid,
                            msg_type=0,
                            content=seg,
                            msg_seq=msg_seq,
                        )
                else:
                    for seg in segments:
                        msg_seq = int(time.time() * 1000) % 1000000 + random.randint(1, 1000)
                        await _runner._client.api.post_c2c_message(
                            openid=user_openid,
                            msg_type=0,
                            content=seg,
                            msg_seq=msg_seq,
                        )

            future = asyncio.run_coroutine_threadsafe(_send_all(), loop)
            future.result(timeout=30)
            _log.info("[Push/QQ] 推送成功 type=%s", chat_type)
            return True
    except Exception as e:
        _log.error("[Push/QQ] 推送失败: %s", e, exc_info=True)
        return False


async def push_message_to_platform(platform: str, text: str) -> bool:
    if platform == "wechat":
        return push_wechat_message(text)
    elif platform == "feishu":
        return await push_feishu_message(text)
    elif platform == "qq":
        return await push_qq_message(text)
    return False
