"""QQ / 微信 / 飞书 主动消息推送（定时任务等场景）。"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time

from typing import Any

_log = logging.getLogger(__name__)

MAX_SEGMENT_LEN = 2000


def _config_for_platform(platform: str, email: str | None = None) -> dict:
    from app.services.bot_manager import _load_bot_config, get_bot_user_email

    email = email or get_bot_user_email()
    config = _load_bot_config(email)
    return config.get(platform, {})


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


def push_wechat_message(text: str, email: str | None = None) -> bool:
    """主动推送微信消息。"""
    if not text.strip():
        _log.warning("[Push/微信] 内容为空，跳过")
        return False

    wechat = _config_for_platform("wechat", email)
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

    runtime_token = ""
    runtime_recipient = ""
    try:
        from app.services.wechat_bot import _runner

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

    from app.services.wechat_bot import WeChatBotClient

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

    if context_token:
        try:
            if _try_send(context_token):
                return True
        except Exception as e:
            _log.warning("[Push/微信] 首次发送失败: %s", e)

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
                try:
                    from app.services.bot_manager import persist_recipient

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


async def push_feishu_message(text: str, email: str | None = None) -> bool:
    """主动推送飞书消息。"""
    if not text.strip():
        return False

    feishu = _config_for_platform("feishu", email)
    chat_id = (feishu.get("last_chat_id") or "").strip()

    try:
        from app.services.feishu_bot import _runner

        if _runner and _runner._channel and _runner._loop and _runner._loop.is_running():
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

        client = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .log_level(lark.LogLevel.WARNING)
            .build()
        )

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


async def _qq_access_token(app_id: str, app_secret: str) -> str:
    """获取 QQ 机器人 access_token（主进程 REST 推送用）。"""
    import httpx

    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
        resp = await client.post(
            "https://bots.qq.com/app/getAppAccessToken",
            json={"appId": app_id, "clientSecret": app_secret},
        )
        data = resp.json()
        token = (data.get("access_token") or "").strip()
        if not token:
            raise RuntimeError(f"获取 QQ access_token 失败: {data}")
        return token


async def _push_qq_via_rest(qq: dict, text: str) -> bool:
    """无 bot 进程内 _runner 时，走 QQ OpenAPI REST 主动推送。"""
    import httpx

    app_id = (qq.get("app_id") or "").strip()
    app_secret = (qq.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        _log.warning("[Push/QQ] REST 缺少 app_id/app_secret")
        return False

    chat_type = qq.get("last_chat_type") or "c2c"
    segments = _split_text(text)

    try:
        token = await _qq_access_token(app_id, app_secret)
    except Exception as e:
        _log.error("[Push/QQ] REST 取 token 失败: %s", e)
        return False

    headers = {
        "Authorization": f"QQBot {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        if chat_type == "group":
            group_openid = (qq.get("last_group_openid") or "").strip()
            if not group_openid:
                _log.warning("[Push/QQ] REST 缺少 last_group_openid")
                return False
            url = f"https://api.sgroup.qq.com/v2/groups/{group_openid}/messages"
        else:
            user_openid = (qq.get("last_user_openid") or "").strip()
            if not user_openid:
                _log.warning("[Push/QQ] REST 缺少 last_user_openid（请先用 QQ 给 bot 发一条消息）")
                return False
            url = f"https://api.sgroup.qq.com/v2/users/{user_openid}/messages"

        for seg in segments:
            msg_seq = int(time.time() * 1000) % 1000000 + random.randint(1, 1000)
            payload = {"content": seg, "msg_type": 0, "msg_id": "", "msg_seq": msg_seq}
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                _log.error("[Push/QQ] REST 发送失败 status=%s body=%s", resp.status_code, resp.text[:300])
                return False

    _log.info("[Push/QQ] REST 推送成功 type=%s", chat_type)
    return True


async def push_qq_message(text: str, email: str | None = None) -> bool:
    """主动推送 QQ 消息。优先用进程内 botpy client，否则走 REST。"""
    if not text.strip():
        return False

    qq = _config_for_platform("qq", email)
    if not qq.get("enabled"):
        return False

    try:
        from app.services.qq_bot import _runner

        if _runner and _runner._client:
            loop = _runner._loop
            if not loop or not loop.is_running():
                _log.warning("[Push/QQ] bot 事件循环未运行，尝试 REST")
            else:
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
        _log.warning("[Push/QQ] Channel 推送失败，尝试 REST: %s", e)

    return await _push_qq_via_rest(qq, text)


async def push_message_to_platform(platform: str, text: str, email: str | None = None) -> bool:
    if platform == "wechat":
        return await asyncio.to_thread(push_wechat_message, text, email)
    if platform == "feishu":
        return await push_feishu_message(text, email)
    if platform == "qq":
        return await push_qq_message(text, email)
    return False
