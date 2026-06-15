"""微信 iLink Bot 监听（全局单例）"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import threading
import time
import uuid
from typing import Any, Callable, Optional

import httpx

from services.platform_chat import process_inbound_message_async

_log = logging.getLogger(__name__)

ILINK_BASE = "https://ilinkai.weixin.qq.com"

_runner: Optional[WeChatRunner] = None
_lock = threading.Lock()


def _random_uin() -> str:
    return base64.b64encode(str(random.randint(0, 0xFFFFFFFF)).encode()).decode()


def _load_wechat_config() -> dict:
    import json
    from pathlib import Path
    config_path = Path.home() / ".MIMOClaw" / "bot_config.json"
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


class WeChatBotClient:
    def __init__(
        self,
        bot_token: str = "",
        to_user_id: str = "",
        context_token: str = "",
        get_updates_buf: str = "",
        last_from_user_id: str = "",
    ):
        self.bot_token = bot_token
        self.to_user_id = to_user_id
        self.context_token = context_token
        self._cursor = get_updates_buf
        self.last_from_user_id = last_from_user_id or to_user_id
        self._client = httpx.Client(timeout=35, trust_env=False)
        self._running = False

    def _recipient_user_id(self) -> str:
        return (self.last_from_user_id or self.to_user_id or "").strip()

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Authorization": f"Bearer {self.bot_token}",
            "X-WECHAT-UIN": _random_uin(),
        }

    def _ensure_client(self):
        if self._client.is_closed:
            self._client = httpx.Client(timeout=35, trust_env=False)

    def _post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        if not self._running:
            return {"ret": 0}
        self._ensure_client()
        body["base_info"] = {"channel_version": "1.0.3"}
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = self._headers()
        headers["Content-Length"] = str(len(raw))
        resp = self._client.post(
            f"{ILINK_BASE}/ilink/bot/{endpoint}",
            content=raw,
            headers=headers,
        )
        text = resp.text.strip()
        if not text or text == "{}":
            return {"ret": 0}
        return json.loads(text)

    def get_updates(self) -> list[dict[str, Any]]:
        result = self._post("getupdates", {"get_updates_buf": self._cursor})
        self._cursor = result.get("get_updates_buf", self._cursor)
        msgs = result.get("msgs", [])
        for msg in msgs:
            ct = msg.get("context_token", "")
            if ct:
                self.context_token = ct
            from_user = (msg.get("from_user_id") or "").strip()
            if from_user:
                self.last_from_user_id = from_user
        return msgs

    def send_message(
        self,
        text: str,
        to_user_id: Optional[str] = None,
        context_token: Optional[str] = None,
    ) -> dict[str, Any]:
        return self._post("sendmessage", {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id or self.to_user_id,
                "client_id": f"bot-{uuid.uuid4().hex[:12]}",
                "message_type": 2,
                "message_state": 2,
                "context_token": context_token or self.context_token,
                "item_list": [{"type": 1, "text_item": {"text": text}}],
            }
        })

    def start_listening(
        self,
        handler: Callable[[str], tuple[str, list[str]]],
        on_state_change: Optional[Callable[[], None]] = None,
    ):
        self._running = True
        try:
            while self._running:
                try:
                    msgs = self.get_updates()
                    if on_state_change:
                        on_state_change()
                    for msg in msgs:
                        if not self._running:
                            break
                        ct = msg.get("context_token", "") or self.context_token
                        from_user = (msg.get("from_user_id") or "").strip() or self._recipient_user_id()
                        text = ""
                        for item in msg.get("item_list", []):
                            if item.get("type") == 1:
                                text = item.get("text_item", {}).get("text", "")
                        if not text:
                            continue
                        _log.info("[微信] 来自 %s: %s", from_user, text[:80])
                        try:
                            reply, _files = handler(text)
                        except Exception as exc:
                            _log.error("[微信] handler 异常: %s", exc)
                            reply = f"（处理消息时出错: {exc}）"
                        if reply:
                            self.send_message(reply, to_user_id=from_user, context_token=ct)
                except httpx.HTTPError as e:
                    if not self._running:
                        break
                    err = str(e).lower()
                    if "closed" in err:
                        _log.info("[微信] 连接已关闭，退出监听")
                        break
                    _log.warning("[微信] 网络异常: %s", e)
                    time.sleep(5)
                except Exception as e:
                    if not self._running:
                        break
                    err = str(e).lower()
                    if "closed" in err:
                        _log.info("[微信] 客户端已关闭，退出监听")
                        break
                    _log.error("[微信] listen error: %s", e)
                    time.sleep(5)
        finally:
            self._close_client()

    def _close_client(self):
        try:
            if self._client and not self._client.is_closed:
                self._client.close()
        except Exception:
            pass

    def stop(self):
        self._running = False


class WeChatRunner:
    def __init__(self):
        self.client: Optional[WeChatBotClient] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def _load_client(self) -> bool:
        config = _load_wechat_config()
        wechat = config.get("wechat", {})
        if not wechat.get("enabled"):
            return False
        self.client = WeChatBotClient(
            bot_token=wechat.get("bot_token", ""),
            to_user_id=wechat.get("to_user_id", ""),
            context_token=wechat.get("context_token", ""),
            get_updates_buf=wechat.get("get_updates_buf", ""),
            last_from_user_id=wechat.get("last_from_user_id", "") or wechat.get("to_user_id", ""),
        )
        return True

    def start(self):
        if self._running:
            return
        if not self._load_client():
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="WeChatBot",
        )
        self._thread.start()
        _log.info("[微信] 机器人已启动")

    def stop(self):
        self._running = False
        if self.client:
            self.client.stop()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=15)
        self.client = None
        self._thread = None
        _log.info("[微信] 机器人已停止")

    def is_running(self) -> bool:
        return (
            self._running
            and self._thread is not None
            and self._thread.is_alive()
        )

    def _run_loop(self):
        assert self.client is not None
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            self.client._running = True
            try:
                stale = self.client.get_updates()
                if stale:
                    _log.info("[微信] 启动时跳过 %d 条积压消息", len(stale))
            except Exception as e:
                _log.warning("[微信] 清理积压失败: %s", e)

            def handle(text: str) -> tuple[str, list[str]]:
                client = self.client
                try:
                    async def _send_segment(seg: str):
                        if not client:
                            return
                        client.send_message(
                            seg,
                            to_user_id=client._recipient_user_id(),
                            context_token=client.context_token,
                        )

                    return loop.run_until_complete(
                        process_inbound_message_async(
                            "wechat", text, send_segment=_send_segment
                        )
                    )
                except RuntimeError as e:
                    if "shutdown" in str(e).lower():
                        _log.warning("[微信] 进程关闭中，跳过消息处理")
                        return "", []
                    raise

            self.client.start_listening(handle)
        finally:
            loop.close()
            self._running = False


def start_wechat_bot() -> bool:
    global _runner
    with _lock:
        if _runner and _runner.is_running():
            return True
        _runner = WeChatRunner()
        _runner.start()
        return _runner.is_running()


def stop_wechat_bot():
    global _runner
    with _lock:
        if _runner:
            _runner.stop()
            _runner = None


def restart_wechat_bot():
    stop_wechat_bot()
    time.sleep(0.3)
    start_wechat_bot()
