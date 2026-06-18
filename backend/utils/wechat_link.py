"""微信 iLink 登录流程"""

import base64
import io
import logging
import time
from typing import Any, Optional

import httpx

_log = logging.getLogger(__name__)

BASE_URL = "https://ilinkai.weixin.qq.com"

# 全局状态
_qrcode_state: dict[str, Any] = {}


def _generate_qrcode_base64(url: str) -> str:
    """将 URL 转为 base64 图片"""
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


def generate_qrcode() -> dict[str, Any]:
    """获取微信登录二维码"""
    global _qrcode_state

    # 如果已有未过期的二维码，直接返回
    if _qrcode_state.get("qrcode_key") and _qrcode_state.get("expire_time", 0) > time.time():
        return {
            "success": True,
            "qrcode_img": _qrcode_state.get("qrcode_img", ""),
            "qrcode_key": _qrcode_state["qrcode_key"],
            "message": "请使用微信扫描二维码",
        }

    try:
        with httpx.Client(timeout=15, trust_env=False) as client:
            resp = client.get(f"{BASE_URL}/ilink/bot/get_bot_qrcode?bot_type=3")
            data = resp.json()

        if data.get("ret") != 0:
            return {"success": False, "error": f"获取二维码失败: ret={data.get('ret')}"}

        qrcode_key = data.get("qrcode", "")
        qrcode_url = data.get("qrcode_img_content", "")

        if not qrcode_key or not qrcode_url:
            return {"success": False, "error": "二维码数据异常"}

        qrcode_img = _generate_qrcode_base64(qrcode_url)

        _qrcode_state = {
            "qrcode_key": qrcode_key,
            "qrcode_img": qrcode_img,
            "qrcode_url": qrcode_url,
            "expire_time": time.time() + 480,  # 8 分钟有效期
        }

        _log.info("[微信] 二维码已生成: %s...", qrcode_key[:12])

        return {
            "success": True,
            "qrcode_img": qrcode_img,
            "qrcode_key": qrcode_key,
            "message": "请使用微信扫描二维码",
        }

    except httpx.HTTPError as e:
        _log.error("[微信] 获取二维码失败: %s", e)
        return {"success": False, "error": f"网络请求失败: {e}"}
    except Exception as e:
        _log.error("[微信] 获取二维码异常: %s", e)
        return {"success": False, "error": str(e)}


def poll_qrcode_status(key: Optional[str] = None) -> dict[str, Any]:
    """轮询二维码扫码状态"""
    global _qrcode_state

    qrcode_key = key or _qrcode_state.get("qrcode_key")
    if not qrcode_key:
        return {"status": "expired", "message": "二维码已过期，请重新获取"}

    try:
        with httpx.Client(timeout=15, trust_env=False) as client:
            resp = client.get(
                f"{BASE_URL}/ilink/bot/get_qrcode_status?qrcode={qrcode_key}",
                headers={"iLink-App-ClientVersion": "1"},
            )
            data = resp.json()

        status = data.get("status", "wait")

        if status == "wait":
            return {
                "status": "pending",
                "message": "等待扫码...",
            }

        elif status == "scaned":
            return {
                "status": "scaned",
                "message": "已扫码，请在手机上确认...",
            }

        elif status == "confirmed":
            bot_token = data.get("bot_token", "")
            ilink_bot_id = data.get("ilink_bot_id", "")
            ilink_user_id = data.get("ilink_user_id", "")
            baseurl = data.get("baseurl") or BASE_URL

            # 保存登录信息
            _qrcode_state = {}

            _log.info("[微信] 登录成功: bot_id=%s, user_id=%s", ilink_bot_id, ilink_user_id)

            return {
                "status": "confirmed",
                "message": "微信授权成功",
                "bot_token": bot_token,
                "ilink_bot_id": ilink_bot_id,
                "ilink_user_id": ilink_user_id,
                "baseurl": baseurl,
            }

        elif status == "expired":
            _qrcode_state = {}
            return {
                "status": "expired",
                "message": "二维码已过期，请重新获取",
            }

        else:
            return {
                "status": "pending",
                "message": "等待扫码...",
            }

    except httpx.HTTPError as e:
        _log.error("[微信] 轮询状态失败: %s", e)
        return {"status": "error", "message": f"网络请求失败: {e}"}
    except Exception as e:
        _log.error("[微信] 轮询状态异常: %s", e)
        return {"status": "error", "message": str(e)}


def clear_qrcode_state() -> None:
    """清除二维码状态（用户取消或退出时调用）"""
    global _qrcode_state
    _qrcode_state = {}
