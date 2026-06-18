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

    context_token = (wechat.get("context_token") or "").strip()
    recipient = (
        (wechat.get("last_from_user_id") or "").strip()
        or (wechat.get("to_user_id") or "").strip()
    )
    if not recipient:
        _log.warning("[Push/微信] 缺少收消息用户，请先用手机给 bot 发一条消息")
        return False

    segments = _split_text(text)

    # 优先使用运行中的 bot 客户端
    try:
        from services.wechat_bot import _runner

        if _runner and _runner.client:
            _runner.client._running = True
            try:
                for seg in segments:
                    result = _runner.client.send_message(
                        seg,
                        to_user_id=recipient,
                        context_token=context_token,
                    )
                    _log.info("[Push/微信] 运行中 bot 返回: %s", result)
                return True
            except Exception as e:
                _log.warning("[Push/微信] 运行中 bot 推送失败: %s", e)
    except Exception as e:
        _log.warning("[Push/微信] 运行中 bot 不可用: %s", e)

    try:
        from services.wechat_bot import WeChatBotClient

        client = WeChatBotClient(
            bot_token=bot_token,
            to_user_id=wechat.get("to_user_id", ""),
            context_token=context_token,
            last_from_user_id=recipient,
        )
        client._running = True
        try:
            for seg in segments:
                result = client.send_message(seg, to_user_id=recipient, context_token=context_token)
                _log.info("[Push/微信] 独立客户端返回: %s", result)
            return True
        finally:
            client._close_client()
    except Exception as e:
        _log.error("[Push/微信] 推送失败: %s", e)
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
            async def _send_via_channel() -> bool:
                await _runner._channel.send(chat_id, {"text": text})
                return True

            future = asyncio.run_coroutine_threadsafe(_send_via_channel(), _runner._loop)
            future.result(timeout=30)
            _log.info("[Push/飞书] 推送成功（Channel）")
            return True
    except Exception as e:
        _log.warning("[Push/飞书] Channel 推送失败，尝试 REST: %s", e)

    # REST API 兜底
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

    # 优先使用运行中的 bot 客户端
    try:
        from services.qq_bot import _runner

        if _runner and _runner._client:
            chat_type = _runner._client.last_chat_type or "c2c"
            if chat_type == "group":
                group_openid = _runner._client.last_group_openid
                if not group_openid:
                    _log.warning("[Push/QQ] 缺少 last_group_openid")
                    return False
                for seg in _split_text(text):
                    msg_seq = int(time.time() * 1000) % 1000000 + random.randint(1, 1000)
                    await _runner._client.api.post_group_message(
                        group_openid=group_openid,
                        msg_type=0,
                        content=seg,
                        msg_seq=msg_seq,
                    )
            else:
                user_openid = _runner._client.last_user_openid
                if not user_openid:
                    _log.warning("[Push/QQ] 缺少 last_user_openid")
                    return False
                for seg in _split_text(text):
                    msg_seq = int(time.time() * 1000) % 1000000 + random.randint(1, 1000)
                    await _runner._client.api.post_c2c_message(
                        openid=user_openid,
                        msg_type=0,
                        content=seg,
                        msg_seq=msg_seq,
                    )
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
