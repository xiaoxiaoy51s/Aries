"""平台消息推送工具（QQ / 微信 / 飞书）。"""

from __future__ import annotations

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "send_message_to_user",
        "description": (
            "向用户主动发送文本消息到指定平台（微信/QQ/飞书）。"
            "发送前会检查对应平台是否已绑定；未绑定则返回失败，请停止重试并告知用户前往设置中绑定。"
            "普通对话回复无需调用本工具（系统会自动送达）；"
            "仅在定时任务结果推送、或需要向非当前会话平台发消息时使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "要发送给用户的文本内容。",
                },
                "platform": {
                    "type": "string",
                    "enum": ["微信", "QQ", "飞书"],
                    "description": "目标推送平台。",
                },
            },
            "required": ["message", "platform"],
            "additionalProperties": False,
        },
    },
}

_PLATFORM_ALIASES = {
    "微信": "wechat",
    "wechat": "wechat",
    "qq": "qq",
    "QQ": "qq",
    "飞书": "feishu",
    "feishu": "feishu",
}


def _normalize_platform(raw: str) -> str:
    return _PLATFORM_ALIASES.get((raw or "").strip(), "")


async def execute(*, message: str = "", platform: str = "", context: dict | None = None) -> str:
    from app.services.bot_manager import (
        PLATFORM_NAMES,
        get_bot_user_email,
        is_platform_bound,
        platform_unbound_message,
    )
    from app.services.platform_push import push_message_to_platform

    text = (message or "").strip()
    if not text:
        return "缺少 message 参数"

    plat = _normalize_platform(platform)
    if not plat:
        return f"未知平台: {platform}（请使用：微信、QQ 或 飞书）"

    user_email = (context or {}).get("user_email") or get_bot_user_email() or ""
    if not is_platform_bound(plat, user_email or None):
        return platform_unbound_message(plat)

    ok = await push_message_to_platform(plat, text, email=user_email or None)
    label = PLATFORM_NAMES.get(plat, plat)
    if ok:
        preview = text if len(text) <= 80 else text[:80] + "…"
        return f"已通过{label}发送消息: {preview}"
    return f"{label}消息发送失败，请检查 bot 是否在线，并确认用户曾向 bot 发送过消息"
