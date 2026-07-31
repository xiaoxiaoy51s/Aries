"""Bot 平台绑定 API（QQ / 飞书 / 微信）。

配置路径：~/.Aries/{user_email}/config.json
- QQ：表单输入 app_id + app_secret
- 飞书：扫码绑定（lark-oapi SDK register_app）
- 微信：扫码绑定（iLink Bot API）
所有端点需 JWT 认证，通过 user.email 定位用户级配置。
"""

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.interceptor.auth_interceptor import get_current_user
from app.model.user import User
from app.services.bot_manager import (
    PLATFORM_NAMES,
    _bot_config_path,
    _load_bot_config,
    is_platform_bound,
    is_platform_enabled,
    restart_platform,
    stop_platform,
)

router = APIRouter(prefix="/api/bot", tags=["bot"])
_log = logging.getLogger(__name__)

_SENSITIVE_KEYS = ("app_secret", "bot_token")


# ── DTO ────────────────────────────────────────────────

class PlatformStatus(BaseModel):
    platform: str
    name: str
    enabled: bool
    bound: bool


class QQConfigRequest(BaseModel):
    app_id: str
    app_secret: str
    enabled: bool = True


class ToggleRequest(BaseModel):
    enabled: bool


class WeChatPollRequest(BaseModel):
    qrcode_key: Optional[str] = None


# ── 工具函数 ────────────────────────────────────────────

def _save_platform_config(email: str, platform: str, data: dict[str, Any]) -> None:
    """读-改-写：把 platform 配置写入 ~/.Aries/{email}/config.json"""
    path = _bot_config_path(email)
    config: dict = {}
    if path.exists():
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    config[platform] = data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_config(pconf: dict) -> dict:
    """脱敏：移除 app_secret / bot_token"""
    return {k: v for k, v in pconf.items() if k not in _SENSITIVE_KEYS}


# ── 列表 / 详情 ─────────────────────────────────────────

@router.get("/platforms", response_model=list[PlatformStatus])
async def list_platforms(user: User = Depends(get_current_user)):
    """列出三个平台的状态。"""
    result: list[PlatformStatus] = []
    for plat, name in PLATFORM_NAMES.items():
        result.append(PlatformStatus(
            platform=plat,
            name=name,
            enabled=is_platform_enabled(plat, user.email),
            bound=is_platform_bound(plat, user.email),
        ))
    return result


@router.get("/platforms/{platform}")
async def get_platform(platform: str, user: User = Depends(get_current_user)):
    """获取单个平台详情（脱敏）。"""
    if platform not in PLATFORM_NAMES:
        raise HTTPException(404, "未知平台")
    config = _load_bot_config(user.email)
    pconf = config.get(platform, {})
    return {
        "platform": platform,
        "name": PLATFORM_NAMES[platform],
        "enabled": pconf.get("enabled", False),
        "bound": is_platform_bound(platform, user.email),
        "config": _safe_config(pconf),
    }


# ── QQ（表单输入）──────────────────────────────────────

@router.post("/platforms/qq")
async def save_qq(req: QQConfigRequest, user: User = Depends(get_current_user)):
    """保存 QQ 配置（app_id + app_secret）。"""
    if not req.app_id.strip() or not req.app_secret.strip():
        raise HTTPException(400, "App ID 和 App Secret 不能为空")
    _save_platform_config(user.email, "qq", {
        "enabled": req.enabled,
        "app_id": req.app_id.strip(),
        "app_secret": req.app_secret.strip(),
        "mode": "agent",
    })
    if req.enabled:
        restart_platform("qq", user.email)
    else:
        stop_platform("qq", user.email)
    _log.info("[Bot] QQ 配置已保存: user=%s", user.email)
    return {"success": True, "message": "QQ 配置已保存"}


# ── 微信（扫码绑定）────────────────────────────────────

@router.post("/platforms/wechat/qrcode")
async def wechat_qrcode(user: User = Depends(get_current_user)):
    """获取微信扫码二维码。"""
    from app.services.wechat_link import generate_qrcode
    result = generate_qrcode()
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "获取二维码失败"))
    return result


@router.post("/platforms/wechat/qrcode/poll")
async def wechat_qrcode_poll(req: WeChatPollRequest, user: User = Depends(get_current_user)):
    """轮询微信扫码状态。confirmed 时自动写入凭据。"""
    from app.services.wechat_link import poll_qrcode_status
    result = poll_qrcode_status(req.qrcode_key)

    if result.get("status") == "confirmed":
        # 写入凭据到用户配置
        config = _load_bot_config(user.email)
        wechat = config.get("wechat", {})
        wechat.update({
            "bot_token": result.get("bot_token", ""),
            "ilink_bot_id": result.get("ilink_bot_id", ""),
            "ilink_user_id": result.get("ilink_user_id", ""),
            "baseurl": result.get("baseurl", ""),
            "enabled": True,
            "mode": "agent",
        })
        _save_platform_config(user.email, "wechat", wechat)
        restart_platform("wechat", user.email)
        _log.info("[Bot] 微信扫码绑定成功: user=%s", user.email)

    return result


# ── 飞书（扫码绑定）────────────────────────────────────

@router.post("/platforms/feishu/qrcode")
async def feishu_qrcode(user: User = Depends(get_current_user)):
    """获取飞书扫码二维码。"""
    from app.services.feishu_link import generate_qrcode
    result = generate_qrcode(user.email)

    # 如果已配置或已授权，直接返回
    if result.get("phase") in ("configured", "authorized"):
        return result

    if not result.get("success"):
        raise HTTPException(400, result.get("message", result.get("error", "获取二维码失败")))

    return result


@router.post("/platforms/feishu/qrcode/poll")
async def feishu_qrcode_poll(user: User = Depends(get_current_user)):
    """轮询飞书扫码状态。confirmed 时自动写入凭据。"""
    from app.services.feishu_link import poll_auth_status
    result = poll_auth_status(user.email)

    if result.get("status") == "confirmed":
        # 确保启用
        config = _load_bot_config(user.email)
        feishu = config.get("feishu", {})
        if not feishu.get("enabled"):
            feishu["enabled"] = True
            feishu["mode"] = "agent"
            _save_platform_config(user.email, "feishu", feishu)
        restart_platform("feishu", user.email)
        _log.info("[Bot] 飞书扫码绑定成功: user=%s", user.email)

    return result


@router.post("/platforms/feishu/cancel")
async def feishu_cancel(user: User = Depends(get_current_user)):
    """取消飞书注册流程。"""
    from app.services.feishu_link import cancel_registration
    cancel_registration()
    return {"success": True, "message": "已取消飞书注册"}


# ── 通用 ────────────────────────────────────────────────

@router.post("/platforms/{platform}/toggle")
async def toggle_platform(req: ToggleRequest, platform: str, user: User = Depends(get_current_user)):
    """快捷启用/禁用平台（仅改 enabled 字段，不清除凭据）。"""
    if platform not in PLATFORM_NAMES:
        raise HTTPException(404, "未知平台")
    config = _load_bot_config(user.email)
    pconf = config.get(platform, {})
    pconf["enabled"] = req.enabled
    _save_platform_config(user.email, platform, pconf)
    if req.enabled and is_platform_bound(platform, user.email):
        restart_platform(platform, user.email)
    elif not req.enabled:
        stop_platform(platform, user.email)
    _log.info("[Bot] %s 已%s: user=%s", PLATFORM_NAMES[platform], "启用" if req.enabled else "禁用", user.email)
    return {"success": True, "message": f"{PLATFORM_NAMES[platform]} 已{'启用' if req.enabled else '禁用'}"}


@router.delete("/platforms/{platform}")
async def unbind_platform(platform: str, user: User = Depends(get_current_user)):
    """解绑平台：清除凭据，enabled=false。"""
    if platform not in PLATFORM_NAMES:
        raise HTTPException(404, "未知平台")

    # 飞书解绑时清理 SDK 目录
    if platform == "feishu":
        from app.services.feishu_link import logout_cli
        logout_cli(user.email)
        stop_platform("feishu", user.email)
        return {"success": True, "message": "飞书已解绑"}

    # 微信解绑时清除二维码状态
    if platform == "wechat":
        from app.services.wechat_link import clear_qrcode_state
        clear_qrcode_state()
        stop_platform("wechat", user.email)

    config = _load_bot_config(user.email)
    config[platform] = {"enabled": False}
    _save_platform_config(user.email, platform, config[platform])
    stop_platform(platform, user.email)
    _log.info("[Bot] %s 已解绑: user=%s", PLATFORM_NAMES[platform], user.email)
    return {"success": True, "message": f"{PLATFORM_NAMES[platform]} 已解绑"}
