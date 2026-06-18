"""飞书 lark-oapi SDK 配置管理（全局单例，无用户系统）"""

import base64
import contextlib
import io
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

import lark_oapi as lark
from lark_oapi import LogLevel

_log = logging.getLogger(__name__)

_qrcode_lock = threading.Lock()

_PROXY_KEYS = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
               "http_proxy", "https_proxy", "all_proxy"]


@contextlib.contextmanager
def _no_proxy():
    saved = {}
    for key in _PROXY_KEYS:
        if key in os.environ:
            saved[key] = os.environ.pop(key)
    try:
        yield
    finally:
        for key, value in saved.items():
            os.environ[key] = value


_session_cache: dict[str, Any] = {}
_registration_threads: dict[str, threading.Thread] = {}


def _load_feishu_config() -> dict:
    config_path = Path.home() / ".Aries" / "bot_config.json"
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_feishu_config(feishu: dict) -> None:
    config_path = Path.home() / ".Aries" / "bot_config.json"
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    config["feishu"] = feishu
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_feishu_home() -> Path:
    return Path.home() / ".Aries" / "feishu-sdk"


def _ensure_home() -> Path:
    home = _get_feishu_home()
    home.mkdir(parents=True, exist_ok=True)
    return home


def _get_client() -> Optional[lark.Client]:
    config = _load_feishu_config()
    feishu = config.get("feishu", {})
    app_id = feishu.get("app_id", "")
    app_secret = feishu.get("app_secret", "")
    if not app_id or not app_secret:
        return None
    try:
        with _no_proxy():
            client = lark.Client.builder() \
                .app_id(app_id) \
                .app_secret(app_secret) \
                .log_level(LogLevel.WARNING) \
                .build()
        return client
    except Exception as e:
        _log.error("[飞书] 创建客户端失败: %s", e)
        return None


def is_configured() -> bool:
    config = _load_feishu_config()
    feishu = config.get("feishu", {})
    app_id = feishu.get("app_id", "")
    app_secret = feishu.get("app_secret", "")
    return bool(app_id and app_secret)


def is_authorized() -> bool:
    config = _load_feishu_config()
    feishu = config.get("feishu", {})
    return bool(feishu.get("authorized", False))


def _mark_authorized() -> None:
    config = _load_feishu_config()
    feishu = config.get("feishu", {})
    feishu["authorized"] = True
    _save_feishu_config(feishu)


def setup_manual_app(app_id: str, app_secret: str) -> dict[str, Any]:
    if not app_id or not app_secret:
        return {"success": False, "error": "App ID 和 App Secret 不能为空"}

    client = None
    try:
        with _no_proxy():
            client = lark.Client.builder() \
                .app_id(app_id) \
                .app_secret(app_secret) \
                .log_level(LogLevel.WARNING) \
                .build()
    except Exception as e:
        return {"success": False, "error": f"创建客户端失败: {e}"}

    try:
        with _no_proxy():
            response = client.im.v1.bot.get()
        if not response.success():
            return {
                "success": False,
                "error": f"验证失败: code={response.code}, msg={response.msg}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"连接飞书服务器失败: {e}"
        }

    feishu = {
        "app_id": app_id,
        "app_secret": app_secret,
        "sdk_ready": True,
        "authorized": True,
    }
    _save_feishu_config(feishu)

    _log.info("[飞书] 手动配置成功: app_id=%s", app_id)
    return {
        "success": True,
        "message": "飞书应用配置成功",
        "app_id": app_id
    }


def _generate_qrcode_base64(url: str) -> str:
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except ImportError:
        return url


class _RegistrationState:
    def __init__(self):
        self.qr_url: str = ""
        self.status: str = "pending"
        self.result: Optional[dict] = None
        self.error: Optional[str] = None
        self.expire_in: int = 300
        self.interval: int = 5


_registration_states: dict[str, _RegistrationState] = {}
_cancel_flags: dict[str, bool] = {}


def _handle_qr_code(info: dict) -> None:
    state = _registration_states.get("global")
    if state:
        state.qr_url = info.get("url", "")
        state.expire_in = info.get("expire_in", 300)
        _log.info("[飞书] 收到二维码 URL: %.100s...", state.qr_url)


def _handle_status_change(info: dict) -> None:
    state = _registration_states.get("global")
    if state:
        state.status = info.get("status", "polling")
        if "interval" in info:
            state.interval = info["interval"]
        _log.info("[飞书] 状态变化: %s", state.status)


def cancel_registration() -> None:
    """取消正在进行的注册流程。"""
    _cancel_flags["global"] = True
    state = _registration_states.get("global")
    if state and state.status not in ("confirmed", "error"):
        state.status = "cancelled"
        state.error = "用户取消"
    _log.info("[飞书] 注册流程已取消")


def _register_app_thread() -> None:
    state = _registration_states.get("global")
    if not state:
        return

    _cancel_flags.pop("global", None)
    _log.info("[飞书] 开始注册飞书应用...")

    try:
        with _no_proxy():
            result = lark.register_app(
                on_qr_code=_handle_qr_code,
                on_status_change=_handle_status_change,
            )

        if _cancel_flags.get("global"):
            _log.info("[飞书] 注册已被取消，丢弃结果")
            return

        state.result = result
        state.status = "confirmed"
        _log.info("[飞书] 应用注册成功: client_id=%s", result.get("client_id"))

        app_id = result.get("client_id", "")
        app_secret = result.get("client_secret", "")

        feishu = {
            "app_id": app_id,
            "app_secret": app_secret,
            "sdk_ready": True,
            "authorized": True,
        }
        _save_feishu_config(feishu)

    except Exception as e:
        if _cancel_flags.get("global"):
            _log.info("[飞书] 注册已被取消")
            return
        state.error = str(e)
        state.status = "error"
        _log.error("[飞书] 应用注册失败: %s", e)


def start_registration() -> dict[str, Any]:
    _ensure_home()

    if is_configured():
        return {
            "success": True,
            "phase": "configured",
            "message": "飞书应用已配置，请直接授权"
        }

    state = _RegistrationState()
    _registration_states["global"] = state

    existing = _registration_threads.get("global")
    if existing and existing.is_alive():
        if state.qr_url:
            return {
                "success": True,
                "phase": "registering",
                "qrcode_img": _generate_qrcode_base64(state.qr_url),
                "message": f"等待扫码授权... (二维码 {state.expire_in}秒内有效)"
            }
        return {
            "success": True,
            "phase": "registering",
            "message": "正在获取二维码..."
        }

    thread = threading.Thread(
        target=_register_app_thread,
        daemon=True,
        name="FeishuReg-global"
    )
    _registration_threads["global"] = thread
    thread.start()

    for _ in range(30):
        if state.qr_url:
            return {
                "success": True,
                "phase": "registering",
                "qrcode_img": _generate_qrcode_base64(state.qr_url),
                "message": f"请使用飞书 App 扫码授权 (二维码 {state.expire_in}秒内有效)"
            }
        if state.error:
            return {
                "success": False,
                "phase": "error",
                "message": f"获取二维码失败: {state.error}"
            }
        time.sleep(0.5)

    return {
        "success": True,
        "phase": "registering",
        "message": "正在获取二维码，请稍候..."
    }


def poll_registration_status() -> dict[str, Any]:
    state = _registration_states.get("global")
    if not state:
        if is_configured():
            return {
                "status": "configured",
                "message": "飞书应用已配置"
            }
        return {
            "status": "none",
            "message": "未开始注册流程"
        }

    if state.status == "confirmed":
        return {
            "status": "confirmed",
            "message": "飞书授权成功"
        }
    elif state.status == "cancelled":
        return {
            "status": "cancelled",
            "message": "注册已取消"
        }
    elif state.status == "error":
        return {
            "status": "error",
            "message": f"注册失败: {state.error}"
        }
    elif state.qr_url:
        return {
            "status": "pending",
            "phase": "registering",
            "qrcode_img": _generate_qrcode_base64(state.qr_url),
            "message": f"请使用飞书 App 扫码授权 (二维码 {state.expire_in}秒内有效)"
        }
    else:
        return {
            "status": "pending",
            "phase": "registering",
            "message": "正在获取二维码，请稍候..."
        }


def generate_qrcode() -> dict[str, Any]:
    if is_configured():
        if is_authorized():
            return {
                "success": True,
                "phase": "authorized",
                "message": "飞书已授权"
            }
        return {
            "success": True,
            "phase": "configured",
            "message": "飞书应用已配置"
        }

    return start_registration()


def poll_auth_status(device_code: Optional[str] = None) -> dict[str, Any]:
    if is_authorized():
        return {"status": "confirmed", "message": "飞书授权成功"}

    return poll_registration_status()


def logout_cli() -> None:
    _registration_threads.pop("global", None)
    _registration_states.pop("global", None)

    home = _get_feishu_home()
    if home.exists():
        import shutil
        try:
            shutil.rmtree(home)
            _log.info("[飞书] 已清理 feishu-sdk 目录")
        except Exception as e:
            _log.warning("[飞书] 清理 feishu-sdk 失败: %s", e)

    config = _load_feishu_config()
    if "feishu" in config:
        del config["feishu"]
        config_path = Path.home() / ".Aries" / "bot_config.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    with _qrcode_lock:
        _session_cache.pop("global", None)
