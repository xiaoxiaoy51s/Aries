"""QQ 机器人（botpy，全局单例）"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import threading
import time
from typing import Any, Optional

from services.platform_chat import process_inbound_message_async

_log = logging.getLogger(__name__)

try:
    import botpy
    from botpy.message import Message

    BOTPY_AVAILABLE = True
except ImportError:
    BOTPY_AVAILABLE = False
    Message = Any  # type: ignore

_runner: Optional[_QQRunner] = None
_lock = threading.Lock()


def _clean_qq_content(content: str) -> str:
    content = re.sub(r'<faceType=\d+[^>]*>', "", content)
    content = re.sub(r"<[^>]+>", "", content)
    return content.strip()


def _get_author_id(message) -> str:
    author = getattr(message, "author", None)
    if author:
        aid = getattr(author, "id", None) or getattr(author, "user_openid", None)
        if aid:
            return str(aid)
    for attr in ("author_user_openid", "member_openid"):
        val = getattr(message, attr, None)
        if val:
            return str(val)
    return "unknown"


async def _reply_qq_message(message, reply: str):
    if not BOTPY_AVAILABLE:
        return
    max_len = 2000
    segments: list[str] = []
    while len(reply) > max_len:
        cut = reply.rfind("\n", 0, max_len)
        if cut < max_len // 2:
            cut = max_len
        segments.append(reply[:cut])
        reply = reply[cut:]
    if reply:
        segments.append(reply)

    for i, seg in enumerate(segments):
        try:
            msg_seq = int(time.time() * 1000) % 1000000 + random.randint(1, 1000) + i
            await message.reply(content=seg, msg_seq=msg_seq)
        except Exception as e:
            _log.error("[QQ] 回复失败: %s", e)


class NonoQQBot(botpy.Client if BOTPY_AVAILABLE else object):
    def __init__(self, intents):
        if BOTPY_AVAILABLE:
            super().__init__(intents=intents)
        self.last_user_openid = ""
        self.last_group_openid = ""
        self.last_chat_type = "c2c"

    async def on_ready(self):
        name = getattr(getattr(self, "robot", None), "name", "?")
        _log.info("[QQ] 机器人 [%s] 已上线", name)

    async def on_message_create(self, message: Message):
        await self._handle_message(message)

    async def on_at_message_create(self, message: Message):
        await self._handle_message(message)

    async def on_direct_message_create(self, message):
        await self._handle_message(message)

    async def on_c2c_message_create(self, message: Message):
        await self._handle_message(message)

    async def on_group_at_message_create(self, message: Message):
        await self._handle_message(message)

    async def _handle_message(self, message: Message):
        raw = (message.content or "").strip()
        content = _clean_qq_content(raw)
        if not content:
            return
        author_id = _get_author_id(message)
        _log.info("[QQ] 来自 %s: %s", author_id, content[:80])

        group_openid = getattr(message, "group_openid", None)
        user_openid = None
        author = getattr(message, "author", None)
        if author:
            user_openid = getattr(author, "user_openid", None) or getattr(author, "id", None)
        if not user_openid:
            user_openid = author_id if author_id != "unknown" else None

        if group_openid:
            self.last_chat_type = "group"
            self.last_group_openid = str(group_openid)
        elif user_openid:
            self.last_chat_type = "c2c"
            self.last_user_openid = str(user_openid)

        # 用 create_task 后台处理，不阻塞事件循环，让新消息能及时触发取消
        asyncio.create_task(self._process_message_task(message, content))

    async def _process_message_task(self, message: Message, content: str):
        try:
            async def _send_segment(seg: str):
                await _reply_qq_message(message, seg)

            reply, files = await process_inbound_message_async(
                "qq", content, send_segment=_send_segment
            )
        except asyncio.CancelledError:
            _log.info("[QQ] 对话已被新消息取消")
            return
        except RuntimeError as e:
            if "shutdown" in str(e).lower():
                _log.warning("[QQ] 进程关闭中，跳过消息处理")
                return
            raise
        if reply:
            await _reply_qq_message(message, reply)
        if files:
            from services.qq_file import send_files_to_qq
            await send_files_to_qq(message, files)


class _QQRunner:
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._thread: Optional[threading.Thread] = None
        self._client: Any = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self):
        if not BOTPY_AVAILABLE:
            _log.warning("[QQ] qq-botpy 未安装，无法启动")
            return

        def _run():
            try:
                logging.getLogger("botpy").addHandler(logging.NullHandler())
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                intents = botpy.Intents.default()
                intents.public_guild_messages = True
                intents.direct_message = True
                intents.value |= 1 << 30
                client = NonoQQBot(intents)
                self._client = client
                client.run(appid=self.app_id, secret=self.app_secret)
            except RuntimeError:
                pass  # stop() 正常退出路径
            except Exception as e:
                _log.error("[QQ] 运行出错: %s", e)
            finally:
                self._loop = None

        self._thread = threading.Thread(
            target=_run,
            daemon=True,
            name="QQBot",
        )
        self._thread.start()
        _log.info("[QQ] 机器人已在后台启动")

    def stop(self):
        client = self._client
        loop = self._loop
        # botpy 的 client 暴露了 close / stop 之类的方法；优先用 call_soon_threadsafe
        if loop and not loop.is_closed() and client is not None:
            close = getattr(client, "close", None)
            if callable(close):
                try:
                    asyncio.run_coroutine_threadsafe(close(), loop)
                except Exception as e:
                    _log.debug("[QQ] 提交 close 失败: %s", e)
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5)
        self._client = None
        self._loop = None
        self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


def _load_qq_config() -> dict:
    import json
    from pathlib import Path
    config_path = Path.home() / ".Aries" / "bot_config.json"
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def start_qq_bot() -> bool:
    global _runner
    config = _load_qq_config()
    qq = config.get("qq", {})
    if not qq.get("enabled"):
        return False
    if not BOTPY_AVAILABLE:
        _log.warning("[QQ] 请安装 qq-botpy: pip install qq-botpy")
        return False

    app_id = (qq.get("app_id") or "").strip()
    app_secret = (qq.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        return False

    with _lock:
        if _runner and _runner.is_running():
            return True
        _runner = _QQRunner(app_id, app_secret)
        _runner.start()
        return True


def stop_qq_bot():
    global _runner
    with _lock:
        if _runner:
            _runner.stop()
            _runner = None


def restart_qq_bot():
    stop_qq_bot()
    time.sleep(0.3)
    start_qq_bot()
