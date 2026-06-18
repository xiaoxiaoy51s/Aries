"""飞书机器人（lark-oapi SDK FeishuChannel WebSocket 长连接，全局单例）"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Optional

from lark_oapi.channel import FeishuChannel
from lark_oapi import LogLevel

from services.platform_chat import process_inbound_message_async

_log = logging.getLogger(__name__)

_runner: Optional[_FeishuRunner] = None
_lock = threading.Lock()


def _load_feishu_config() -> dict:
    import json
    from pathlib import Path
    config_path = Path.home() / ".Aries" / "bot_config.json"
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
        self._channel: Optional[FeishuChannel] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.last_chat_id: str = ""

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
        if self._channel:
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._channel.disconnect())
                loop.close()
            except Exception as e:
                _log.debug("[飞书] 停止 Channel: %s", e)
        self._channel = None
        self._thread = None

    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    async def _on_message(self, msg: Any):
        try:
            _log.info("[飞书] 收到消息: %s", msg.content_text[:80])

            text = (msg.content_text or "").strip()
            if not text:
                return

            chat_id = (msg.chat_id or "").strip()
            if chat_id:
                self.last_chat_id = chat_id

            # 用 create_task 后台处理，不阻塞事件循环，让新消息能及时触发取消
            asyncio.create_task(self._process_message_task(text, chat_id))
        except Exception as e:
            _log.error("[飞书] 处理消息失败: %s", e)

    async def _process_message_task(self, text: str, chat_id: str):
        try:
            async def _send_segment(seg: str):
                await self._channel.send(chat_id, {"text": seg})

            reply, _files = await process_inbound_message_async(
                "feishu", text, send_segment=_send_segment
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
        if reply and self._channel:
            try:
                await self._channel.send(chat_id, {"text": reply})
                _log.info("[飞书] 已回复 chat_id=%s, len=%d", chat_id, len(reply))
            except Exception as send_err:
                _log.error("[飞书] 发送失败: %s", send_err)

    async def _connect(self):
        import contextlib
        import os

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

        with _no_proxy():
            self._channel = FeishuChannel(
                app_id=self.app_id,
                app_secret=self.app_secret,
                log_level=LogLevel.WARNING,
            )

        self._channel.on("message", self._on_message)

        try:
            _log.info("[飞书] 开始连接 FeishuChannel...")
            with _no_proxy():
                await self._channel.connect()
        except Exception as e:
            _log.error("[飞书] Channel 连接失败: %s", e)
        finally:
            self._running = False

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._connect())
        except Exception as e:
            _log.error("[飞书] 运行事件循环失败: %s", e)
        finally:
            self._loop = None
            try:
                loop.close()
            except Exception:
                pass


def start_feishu_bot() -> bool:
    global _runner
    config = _load_feishu_config()
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


def restart_feishu_bot():
    stop_feishu_bot()
    import time
    time.sleep(1)
    return start_feishu_bot()
