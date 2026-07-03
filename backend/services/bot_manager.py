"""QQ / 微信 / 飞书 Bot 生命周期管理。"""

import json
import logging
import threading
from pathlib import Path

from services.feishu_bot import start_feishu_bot, stop_feishu_bot
from services.qq_bot import start_qq_bot, stop_qq_bot
from services.wechat_bot import start_wechat_bot, stop_wechat_bot

_log = logging.getLogger(__name__)

ARIESCLAW_HOME = Path.home() / ".Aries"


# 从统一的 bot 配置文件中读取启用的平台
_BOT_CONFIG_PATH = ARIESCLAW_HOME / "bot_config.json"


def _load_bot_config() -> dict:
    import json
    if not _BOT_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(_BOT_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


_config_lock = threading.Lock()


def persist_recipient(platform: str, **fields) -> None:
    """把收件人相关字段持久化到 bot_config.json（读-改-写，线程安全）。

    供各平台 bot 在收到用户消息、记录收件人 ID 时调用，避免 bot 重启后
    丢失目标用户标识而无法主动推送。仅当值非空且发生变化时才写盘。
    """
    cleaned = {k: str(v).strip() for k, v in fields.items() if v is not None}
    if not cleaned:
        return
    with _config_lock:
        config = _load_bot_config()
        pconf = config.setdefault(platform, {})
        changed = False
        for k, v in cleaned.items():
            if v and pconf.get(k) != v:
                pconf[k] = v
                changed = True
        if not changed:
            return
        try:
            _BOT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            _BOT_CONFIG_PATH.write_text(
                json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            _log.debug("[BotManager] 已持久化 %s 收件人字段: %s", platform, list(cleaned.keys()))
        except Exception as e:
            _log.warning("[BotManager] 持久化 %s 收件人字段失败: %s", platform, e)


def is_platform_enabled(platform: str) -> bool:
    config = _load_bot_config()
    return config.get(platform, {}).get("enabled", False)


PLATFORM_NAMES = {"qq": "QQ", "feishu": "飞书", "wechat": "微信"}


def is_platform_bound(platform: str) -> bool:
    """检查平台是否已绑定且启用（有凭据且 enabled=true）。"""
    config = _load_bot_config()
    pconf = config.get(platform, {})
    if not pconf.get("enabled", False):
        return False
    if platform == "feishu":
        from services.feishu_link import is_configured
        return is_configured()
    if platform == "qq":
        return bool((pconf.get("app_id") or "").strip() and (pconf.get("app_secret") or "").strip())
    if platform == "wechat":
        return bool((pconf.get("bot_token") or "").strip())
    return False


def platform_unbound_message(platform: str) -> str:
    name = PLATFORM_NAMES.get(platform, platform)
    return f"用户暂未绑定{name}平台，无法发送。请停止发送并告知用户前往设置中绑定{name}。"


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
