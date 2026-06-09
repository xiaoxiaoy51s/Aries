"""QQ / 微信 / 飞书 Bot 生命周期管理。"""

import logging
from pathlib import Path

from services.feishu_bot import start_feishu_bot, stop_feishu_bot
from services.qq_bot import start_qq_bot, stop_qq_bot
from services.wechat_bot import start_wechat_bot, stop_wechat_bot

_log = logging.getLogger(__name__)

MIMOCLAW_HOME = Path.home() / ".MIMOClaw"


# 从统一的 bot 配置文件中读取启用的平台
_BOT_CONFIG_PATH = MIMOCLAW_HOME / "bot_config.json"


def _load_bot_config() -> dict:
    import json
    if not _BOT_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(_BOT_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def is_platform_enabled(platform: str) -> bool:
    config = _load_bot_config()
    return config.get(platform, {}).get("enabled", False)


def start_all_bots():
    started = {"qq": 0, "wechat": 0, "feishu": 0}
    if is_platform_enabled("qq"):
        try:
            if start_qq_bot():
                started["qq"] += 1
        except Exception as e:
            _log.warning("[BotManager] QQ 启动失败: %s", e)
    if is_platform_enabled("wechat"):
        try:
            if start_wechat_bot():
                started["wechat"] += 1
        except Exception as e:
            _log.warning("[BotManager] 微信启动失败: %s", e)
    if is_platform_enabled("feishu"):
        try:
            if start_feishu_bot():
                started["feishu"] += 1
        except Exception as e:
            _log.warning("[BotManager] 飞书启动失败: %s", e)
    _log.info("[BotManager] 启动完成: %s", started)
    return started


def stop_all_bots():
    try:
        stop_qq_bot()
    except Exception:
        pass
    try:
        stop_wechat_bot()
    except Exception:
        pass
    try:
        stop_feishu_bot()
    except Exception:
        pass
