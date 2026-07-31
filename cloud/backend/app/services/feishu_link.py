"""飞书 lark-oapi SDK 配置管理（云后端版）。

配置路径：~/.Aries/{user_email}/config.json
扫码注册通过 lark.register_app() SDK 实现。
"""

import asyncio
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


# ── 配置读写（用户级）──

def _feishu_config_path(user_email: str) -> Path:
    return Path.home() / ".Aries" / user_email / "config.json"


def _load_feishu_config(user_email: str) -> dict:
    config_path = _feishu_config_path(user_email)
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_feishu_config(user_email: str, feishu: dict) -> None:
    config_path = _feishu_config_path(user_email)
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


# ── 状态查询 ──

def is_configured(user_email: str) -> bool:
    config = _load_feishu_config(user_email)
    feishu = config.get("feishu", {})
    return bool(feishu.get("app_id") and feishu.get("app_secret"))


def is_authorized(user_email: str) -> bool:
    config = _load_feishu_config(user_email)
    feishu = config.get("feishu", {})
    return bool(feishu.get("authorized", False))


# ── 手动配置 ──

def setup_manual_app(user_email: str, app_id: str, app_secret: str) -> dict[str, Any]:
    if not app_id or not app_secret:
        return {"success": False, "error": "App ID 和 App Secret 不能为空"}

    try:
        import lark_oapi as lark
        from lark_oapi import LogLevel

        with _no_proxy():
            client = lark.Client.builder() \
                .app_id(app_id) \
                .app_secret(app_secret) \
                .log_level(LogLevel.WARNING) \
                .build()
            response = client.im.v1.bot.get()
        if not response.success():
            return {
                "success": False,
                "error": f"验证失败: code={response.code}, msg={response.msg}"
            }
    except Exception as e:
        return {"success": False, "error": f"连接飞书服务器失败: {e}"}

    feishu = {
        "app_id": app_id,
        "app_secret": app_secret,
        "sdk_ready": True,
        "authorized": True,
    }
    _save_feishu_config(user_email, feishu)
    _log.info("[飞书] 手动配置成功: app_id=%s", app_id)
    return {"success": True, "message": "飞书应用配置成功", "app_id": app_id}


# ── 扫码注册 ──

_session_cache: dict[str, Any] = {}
_registration_threads: dict[str, threading.Thread] = {}


class _RegistrationState:
    def __init__(self):
        self.qr_url: str = ""
        self.status: str = "pending"
        self.result: Optional[dict] = None
        self.error: Optional[str] = None
        self.expire_in: int = 300
        self.interval: int = 5
        self.user_email: str = ""  # 记录是哪个用户发起的注册


_registration_states: dict[str, _RegistrationState] = {}
_cancel_flags: dict[str, bool] = {}


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
    _log.info("[飞书] 开始注册飞书应用... (user=%s)", state.user_email)

    # 注册线程新建 event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # lark_oapi.ws.client 模块级 loop 是 uvicorn 的（正在运行中），
    # 替换为全新的 loop，避免 "already running" 报错。
    try:
        import lark_oapi.ws.client as _ws_client
        _ws_client.loop = asyncio.new_event_loop()
    except Exception:
        pass

    try:
        import lark_oapi as lark

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
        _save_feishu_config(state.user_email, feishu)

    except Exception as e:
        if _cancel_flags.get("global"):
            _log.info("[飞书] 注册已被取消")
            return
        state.error = str(e)
        state.status = "error"
        _log.error("[飞书] 应用注册失败: %s", e)
    finally:
        try:
            loop.close()
        except Exception:
            pass


def start_registration(user_email: str) -> dict[str, Any]:
    _ensure_home()

    if is_configured(user_email):
        return {
            "success": True,
            "phase": "configured",
            "message": "飞书应用已配置，请直接授权"
        }

    state = _RegistrationState()
    state.user_email = user_email
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
        return {
            "status": "none",
            "message": "未开始注册流程"
        }

    if state.status == "confirmed":
        return {"status": "confirmed", "message": "飞书授权成功"}
    elif state.status == "cancelled":
        return {"status": "cancelled", "message": "注册已取消"}
    elif state.status == "error":
        return {"status": "error", "message": f"注册失败: {state.error}"}
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


def generate_qrcode(user_email: str) -> dict[str, Any]:
    if is_configured(user_email):
        if is_authorized(user_email):
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

    return start_registration(user_email)


def poll_auth_status(user_email: str, device_code: Optional[str] = None) -> dict[str, Any]:
    if is_authorized(user_email):
        return {"status": "confirmed", "message": "飞书授权成功"}
    return poll_registration_status()


def logout_cli(user_email: str) -> None:
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

    config = _load_feishu_config(user_email)
    if "feishu" in config:
        del config["feishu"]
        config_path = _feishu_config_path(user_email)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    with _qrcode_lock:
        _session_cache.pop("global", None)
