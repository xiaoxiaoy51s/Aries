"""平台账号绑定 API（QQ / 微信 / 飞书）。"""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.qq_bot import start_qq_bot, stop_qq_bot
from services.feishu_bot import start_feishu_bot, stop_feishu_bot
from services.wechat_bot import start_wechat_bot, stop_wechat_bot
from utils.wechat_link import generate_qrcode, poll_qrcode_status
from utils.feishu_link import (
    generate_qrcode as generate_feishu_qrcode,
    poll_auth_status as poll_feishu_auth_status,
    cancel_registration as cancel_feishu_registration,
    logout_cli,
    is_configured as feishu_is_configured,
    is_authorized as feishu_is_authorized,
    setup_manual_app,
)

router = APIRouter(prefix="/platforms", tags=["platforms"])

_BOT_CONFIG_PATH = Path.home() / ".MIMOClaw" / "bot_config.json"

PLATFORMS = ("qq", "feishu", "wechat")
PLATFORM_NAMES = {"qq": "QQ", "feishu": "飞书", "wechat": "微信"}


def _load_config() -> dict:
    if not _BOT_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(_BOT_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(config: dict) -> None:
    _BOT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _BOT_CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _is_bot_running(platform: str) -> bool:
    if platform == "qq":
        from services.qq_bot import _runner
        return _runner is not None and _runner.is_running()
    elif platform == "feishu":
        from services.feishu_bot import _runner
        return _runner is not None and _runner.is_running()
    elif platform == "wechat":
        from services.wechat_bot import _runner
        return _runner is not None and _runner.is_running()
    return False


def _restart_platform(platform: str):
    try:
        if platform == "qq":
            stop_qq_bot()
            start_qq_bot()
        elif platform == "feishu":
            stop_feishu_bot()
            start_feishu_bot()
        elif platform == "wechat":
            stop_wechat_bot()
            start_wechat_bot()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[{platform}] 启动机器人失败: {e}")


def _stop_platform(platform: str):
    if platform == "qq":
        stop_qq_bot()
    elif platform == "feishu":
        stop_feishu_bot()
    elif platform == "wechat":
        stop_wechat_bot()


# ---------- Schemas ----------

class QQConfigRequest(BaseModel):
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    mode: str = "agent"


class FeishuConfigRequest(BaseModel):
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    mode: str = "agent"


class WeChatConfigRequest(BaseModel):
    enabled: bool = False
    mode: str = "agent"


class WeChatQRCodePollRequest(BaseModel):
    qrcode_key: Optional[str] = None


class FeishuQRCodePollRequest(BaseModel):
    device_code: Optional[str] = None


class PlatformStatus(BaseModel):
    platform: str
    name: str
    enabled: bool
    running: bool
    configured: bool


def _is_configured(platform: str, pconf: dict) -> bool:
    if platform == "feishu":
        return feishu_is_configured()
    elif platform == "qq":
        return bool(pconf.get("app_id") and pconf.get("app_secret"))
    elif platform == "wechat":
        return bool(pconf.get("bot_token"))
    return False


# ---------- APIs ----------

@router.get("/")
def list_platforms():
    config = _load_config()
    result = []
    for p in PLATFORMS:
        pconf = config.get(p, {})
        enabled = pconf.get("enabled", False)
        configured = _is_configured(p, pconf)
        result.append(PlatformStatus(
            platform=p,
            name=PLATFORM_NAMES.get(p, p),
            enabled=enabled,
            running=_is_bot_running(p),
            configured=configured,
        ))
    return {"platforms": result}


@router.get("/{platform}")
def get_platform(platform: str):
    if platform not in PLATFORMS:
        raise HTTPException(status_code=404, detail="Unknown platform")
    config = _load_config()
    pconf = config.get(platform, {})
    # 隐藏敏感字段
    safe_conf = {k: v for k, v in pconf.items() if k not in ("app_secret", "bot_token")}
    return {
        "platform": platform,
        "name": PLATFORM_NAMES.get(platform, platform),
        "enabled": pconf.get("enabled", False),
        "running": _is_bot_running(platform),
        "configured": bool(pconf.get("app_id") or pconf.get("bot_token")),
        "config": safe_conf,
    }


# ---------- QQ ----------

@router.post("/qq")
def save_qq_config(body: QQConfigRequest):
    config = _load_config()
    existing = config.get("qq", {})
    existing.update({
        "enabled": body.enabled,
        "app_id": body.app_id,
        "app_secret": body.app_secret,
        "mode": body.mode,
    })
    config["qq"] = existing
    _save_config(config)
    if body.enabled and body.app_id and body.app_secret:
        _restart_platform("qq")
    elif not body.enabled:
        _stop_platform("qq")
    return {"success": True, "platform": "qq", "enabled": body.enabled}


@router.delete("/qq")
def unbind_qq():
    config = _load_config()
    config["qq"] = {"enabled": False}
    _save_config(config)
    _stop_platform("qq")
    return {"success": True, "message": "QQ 授权已解除"}


# ---------- 飞书 ----------

@router.post("/feishu")
def save_feishu_config(body: FeishuConfigRequest):
    # 手动配置模式：直接填 app_id + app_secret
    if body.app_id and body.app_secret:
        result = setup_manual_app(body.app_id, body.app_secret)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "飞书配置失败"))
        config = _load_config()
        existing = config.get("feishu", {})
        existing.update({
            "enabled": body.enabled,
            "mode": body.mode,
        })
        config["feishu"] = existing
        _save_config(config)
    else:
        config = _load_config()
        existing = config.get("feishu", {})
        existing.update({
            "enabled": body.enabled,
            "mode": body.mode,
        })
        config["feishu"] = existing
        _save_config(config)

    if body.enabled:
        _restart_platform("feishu")
    else:
        _stop_platform("feishu")
    return {"success": True, "platform": "feishu", "enabled": body.enabled}


@router.post("/feishu/qrcode")
def feishu_qrcode():
    return generate_feishu_qrcode()


@router.post("/feishu/qrcode/poll")
def feishu_qrcode_poll(body: FeishuQRCodePollRequest):
    result = poll_feishu_auth_status(body.device_code)
    if result.get("status") == "confirmed":
        _restart_platform("feishu")
    return result


@router.delete("/feishu")
def unbind_feishu():
    _stop_platform("feishu")
    cancel_feishu_registration()
    logout_cli()
    return {"success": True, "message": "飞书授权已解除"}


@router.post("/feishu/cancel")
def cancel_feishu():
    cancel_feishu_registration()
    return {"success": True, "message": "飞书注册流程已取消"}


# ---------- 微信 ----------

@router.post("/wechat")
def save_wechat_config(body: WeChatConfigRequest):
    config = _load_config()
    existing = config.get("wechat", {})
    existing.update({
        "enabled": body.enabled,
        "mode": body.mode,
    })
    config["wechat"] = existing
    _save_config(config)
    if body.enabled:
        _restart_platform("wechat")
    else:
        _stop_platform("wechat")
    return {"success": True, "platform": "wechat", "enabled": body.enabled}


@router.post("/wechat/qrcode")
def wechat_qrcode():
    return generate_qrcode()


@router.post("/wechat/qrcode/poll")
def wechat_qrcode_poll(body: WeChatQRCodePollRequest):
    result = poll_qrcode_status(body.qrcode_key)
    if result.get("status") == "confirmed":
        _restart_platform("wechat")
    return result


@router.delete("/wechat")
def unbind_wechat():
    config = _load_config()
    config["wechat"] = {"enabled": False}
    _save_config(config)
    _stop_platform("wechat")
    return {"success": True, "message": "微信授权已解除"}


# ---------- 快捷切换 ----------

@router.post("/{platform}/toggle")
def toggle_platform(platform: str):
    if platform not in PLATFORMS:
        raise HTTPException(status_code=404, detail="Unknown platform")
    config = _load_config()
    pconf = config.get(platform, {})
    new_enabled = not pconf.get("enabled", False)

    if new_enabled and not _is_configured(platform, pconf):
        raise HTTPException(status_code=400, detail=f"{PLATFORM_NAMES.get(platform, platform)} 尚未配置，无法启用")

    pconf["enabled"] = new_enabled
    config[platform] = pconf
    _save_config(config)

    if new_enabled:
        _restart_platform(platform)
    else:
        _stop_platform(platform)

    return {"success": True, "platform": platform, "enabled": new_enabled}
