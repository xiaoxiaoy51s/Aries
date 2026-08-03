"""飞书机器人（lark-oapi SDK FeishuChannel WebSocket 长连接，全局单例）
—— 适配 cloud 后端

参照 backend/services/feishu_bot.py，适配 cloud 后端 import 路径。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Optional

from app.services.platform_chat import process_inbound_message_async

_log = logging.getLogger(__name__)

_runner: Optional[_FeishuRunner] = None
_lock = threading.Lock()


_feishu_user_email: str = ""


def _load_feishu_config(user_email: str) -> dict:
    import json
    from pathlib import Path
    config_path = Path.home() / ".Aries" / user_email / "config.json"
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


class _FeishuRunner:
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._channel: Optional[Any] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.last_chat_id: str = ""
        self._tenant_token: str = ""
        self._token_expires_at: float = 0.0

    async def _get_tenant_token(self) -> str:
        """获取飞书 tenant_access_token（缓存，提前 5 分钟刷新）。"""
        import time
        if self._tenant_token and time.time() < self._token_expires_at - 300:
            return self._tenant_token
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    json={"app_id": self.app_id, "app_secret": self.app_secret},
                )
                resp.raise_for_status()
                data = resp.json()
            self._tenant_token = data.get("tenant_access_token", "")
            expire = data.get("expire", 7200)
            self._token_expires_at = time.time() + expire
            return self._tenant_token
        except Exception as e:
            _log.warning("[飞书] 获取 tenant_access_token 失败: %s", e)
            return ""

    async def _download_feishu_image(self, image_key: str) -> str:
        """通过飞书 API 下载图片，返回 base64 data URL。"""
        token = await self._get_tenant_token()
        if not token:
            return ""
        try:
            import httpx
            import base64
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(
                    f"https://open.feishu.cn/open-apis/im/v1/images/{image_key}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"image_type": "message"},
                )
                resp.raise_for_status()
            ct = resp.headers.get("content-type", "image/jpeg")
            b64 = base64.b64encode(resp.content).decode()
            return f"data:{ct};base64,{b64}"
        except Exception as e:
            _log.warning("[飞书] 下载图片失败 (key=%s): %s", image_key, e)
            return ""

    def start(self):
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="FeishuBot",
        )
        self._thread.start()
        _log.info("[飞书] 机器人已启动")

    def stop(self):
        self._running = False
        loop = self._loop
        channel = self._channel
        if loop and not loop.is_closed() and channel is not None:
            try:
                asyncio.run_coroutine_threadsafe(channel.disconnect(), loop)
            except Exception as e:
                _log.debug("[飞书] 提交 disconnect 失败: %s", e)
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass
        self._channel = None
        self._loop = None

    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    async def _on_message(self, msg: Any):
        try:
            _log.info("[飞书] 收到消息: %s", (msg.content_text or "")[:80])

            import json
            msg_type = getattr(msg, "message_type", "") or ""
            text = ""
            images: list[str] = []

            if msg_type == "image":
                # 图片消息：content_text 是 JSON {"image_key":"..."}
                raw_content = getattr(msg, "content_text", "") or getattr(msg, "content", "") or ""
                try:
                    content_obj = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
                    image_key = content_obj.get("image_key", "") if isinstance(content_obj, dict) else ""
                except Exception:
                    image_key = ""
                if image_key:
                    data_url = await self._download_feishu_image(image_key)
                    if data_url:
                        images.append(data_url)
            else:
                text = (msg.content_text or "").strip()

            if not text and not images:
                return

            chat_id = (msg.chat_id or "").strip()
            if chat_id:
                self.last_chat_id = chat_id
                try:
                    from app.services.bot_manager import persist_recipient
                    persist_recipient("feishu", last_chat_id=chat_id)
                except Exception:
                    pass

            # 用 create_task 后台处理，不阻塞事件循环，让新消息能及时触发取消
            asyncio.create_task(self._process_message_task(text, chat_id, images))
        except Exception as e:
            _log.error("[飞书] 处理消息失败: %s", e)

    async def _process_message_task(self, text: str, chat_id: str, images: list[str] | None = None):
        try:
            async def _send_segment(seg: str):
                await self._channel.send(chat_id, {"text": seg})

            reply = await process_inbound_message_async(
                "feishu", text, send_segment=_send_segment, images=images or None
            )
            _log.info("[飞书] Agent 分段推送完成, chat_id=%s", chat_id)
        except asyncio.CancelledError:
            _log.info("[飞书] 对话已被新消息取消")
            return
        except RuntimeError as e:
            if "shutdown" in str(e).lower():
                _log.warning("[飞书] 进程关闭中，跳过消息处理")
                return
            raise
        except Exception as e:
            _log.error("[飞书] 处理消息失败: %s", e)
            return

    async def _connect(self):
        import contextlib
        import os

        from lark_oapi.channel import FeishuChannel
        from lark_oapi import LogLevel

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

        if not self.app_id or not self.app_secret:
            _log.error("[飞书] 缺少 app_id 或 app_secret")
            self._running = False
            return

        # lark-oapi：构造 FeishuChannel 时可能 get_event_loop()；当前线程 loop 已在
        # run_until_complete 中，必须临时换成空闲 loop。构造完成后立刻恢复，
        # 否则后续 asyncpg/agent 会拿到错误的 loop（Future attached to a different loop）。
        _original_get_event_loop = asyncio.get_event_loop
        _sdk_loop = asyncio.new_event_loop()
        asyncio.get_event_loop = lambda: _sdk_loop

        try:
            import lark_oapi.ws.client as _ws_client
        except ImportError:
            _ws_client = None
        _saved_ws_loop = getattr(_ws_client, "loop", None) if _ws_client else None
        if _ws_client:
            _ws_client.loop = _sdk_loop

        try:
            with _no_proxy():
                self._channel = FeishuChannel(
                    app_id=self.app_id,
                    app_secret=self.app_secret,
                    log_level=LogLevel.WARNING,
                )
        finally:
            # 构造完立刻恢复，避免消息处理/DB 落到 _sdk_loop
            asyncio.get_event_loop = _original_get_event_loop

        try:
            self._channel.on("message", self._on_message)

            _log.info("[飞书] 开始连接 FeishuChannel...")
            with _no_proxy():
                await self._channel.connect()
        except Exception as e:
            _log.error("[飞书] Channel 连接失败: %s", e)
        finally:
            if _ws_client and _saved_ws_loop is not None:
                _ws_client.loop = _saved_ws_loop
            self._running = False
            try:
                _sdk_loop.close()
            except Exception:
                pass

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        try:
            loop.run_until_complete(self._connect())
        except RuntimeError:
            pass
        except Exception as e:
            _log.error("[飞书] 运行事件循环失败: %s", e)
        finally:
            self._loop = None
            try:
                loop.close()
            except Exception:
                pass


def start_feishu_bot(user_email: str = "") -> bool:
    global _runner, _feishu_user_email
    _feishu_user_email = user_email
    if not user_email:
        return False
    config = _load_feishu_config(user_email)
    feishu = config.get("feishu", {})
    if not feishu.get("enabled"):
        return False

    app_id = (feishu.get("app_id") or "").strip()
    app_secret = (feishu.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        _log.warning("[飞书] 无法启动机器人: 缺少 app_id 或 app_secret")
        return False

    with _lock:
        existing = _runner
        if existing and existing.is_running():
            return True
        runner = _FeishuRunner(app_id, app_secret)
        runner.start()
        _runner = runner
        return True


def stop_feishu_bot():
    global _runner
    with _lock:
        runner = _runner
        _runner = None
    if runner:
        runner.stop()
        _log.info("[飞书] 机器人已停止")


def restart_feishu_bot(user_email: str = ""):
    global _feishu_user_email
    email = user_email or _feishu_user_email
    stop_feishu_bot()
    import time
    time.sleep(1)
    if email:
        return start_feishu_bot(email)
    return False
