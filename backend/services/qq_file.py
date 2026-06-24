"""QQ 富媒体文件发送（先上传到 QQ 服务器，再以 msg_type=7 发送）。"""

from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
import random
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

_log = logging.getLogger(__name__)

try:
    from botpy.http import Route

    BOTPY_AVAILABLE = True
except ImportError:
    BOTPY_AVAILABLE = False
    Route = Any  # type: ignore

_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
_VIDEO_EXTS = {".mp4"}
_VOICE_EXTS = {".silk", ".wav", ".mp3", ".flac"}


def _guess_file_type(path: str) -> int:
    """QQ file_type: 1 图片, 2 视频, 3 语音, 4 文件。"""
    ext = Path(path).suffix.lower()
    mime, _ = mimetypes.guess_type(path)
    if ext in _IMAGE_EXTS or (mime and mime.startswith("image/")):
        return 1
    if ext in _VIDEO_EXTS or (mime and mime.startswith("video/")):
        return 2
    if ext in _VOICE_EXTS or (mime and mime.startswith("audio/")):
        return 3
    return 4


def _is_http_url(value: str) -> bool:
    try:
        return urlparse(value).scheme in ("http", "https")
    except Exception:
        return False


def _chat_context(message) -> tuple[bool, str, Any]:
    """返回 (is_group, chat_id, api)。"""
    api = getattr(message, "_api", None)
    group_openid = getattr(message, "group_openid", None)
    if group_openid:
        return True, str(group_openid), api

    author = getattr(message, "author", None)
    openid = None
    if author:
        openid = getattr(author, "user_openid", None) or getattr(author, "id", None)
    if not openid:
        openid = getattr(message, "author_user_openid", None) or getattr(message, "member_openid", None)
    return False, str(openid or ""), api


async def _read_local_file(path: str) -> tuple[Optional[bytes], Optional[str]]:
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        _log.warning("[QQ] 文件不存在: %s", path)
        return None, None
    try:
        data = await asyncio.to_thread(file_path.read_bytes)
        return data, file_path.name
    except Exception as e:
        _log.error("[QQ] 读取文件失败 %s: %s", path, e)
        return None, None


async def _upload_base64(
    api,
    *,
    is_group: bool,
    chat_id: str,
    file_type: int,
    file_data_b64: str,
    file_name: str,
) -> Optional[dict]:
    if not BOTPY_AVAILABLE or not api:
        return None
    if is_group:
        endpoint = "/v2/groups/{group_openid}/files"
        id_key = "group_openid"
    else:
        endpoint = "/v2/users/{openid}/files"
        id_key = "openid"

    payload = {
        id_key: chat_id,
        "file_type": file_type,
        "file_data": file_data_b64,
        "file_name": file_name,
        "srv_send_msg": False,
    }
    route = Route("POST", endpoint, **{id_key: chat_id})
    return await api._http.request(route, json=payload)


async def _upload_url(
    api,
    *,
    is_group: bool,
    chat_id: str,
    file_type: int,
    url: str,
) -> Optional[dict]:
    if not api:
        return None
    try:
        if is_group:
            return await api.post_group_file(
                group_openid=chat_id,
                file_type=file_type,
                url=url,
                srv_send_msg=False,
            )
        return await api.post_c2c_file(
            openid=chat_id,
            file_type=file_type,
            url=url,
            srv_send_msg=False,
        )
    except Exception as e:
        _log.error("[QQ] URL 上传失败 %s: %s", url, e)
        return None


async def _send_rich_media(
    api,
    *,
    is_group: bool,
    chat_id: str,
    media: dict,
    msg_id: Optional[str],
    msg_seq: int,
) -> bool:
    if not api:
        return False
    try:
        if is_group:
            await api.post_group_message(
                group_openid=chat_id,
                msg_type=7,
                msg_id=msg_id,
                msg_seq=msg_seq,
                media=media,
            )
        else:
            await api.post_c2c_message(
                openid=chat_id,
                msg_type=7,
                msg_id=msg_id,
                msg_seq=msg_seq,
                media=media,
            )
        return True
    except Exception as e:
        _log.error("[QQ] 富媒体消息发送失败: %s", e)
        return False


async def _send_one_file(message, file_ref: str, msg_seq: int) -> bool:
    is_group, chat_id, api = _chat_context(message)
    if not chat_id or not api:
        _log.warning("[QQ] 无法确定会话目标，跳过文件发送")
        return False

    msg_id = getattr(message, "id", None)
    file_type = _guess_file_type(file_ref)
    media = None
    filename = Path(file_ref).name

    if _is_http_url(file_ref):
        media = await _upload_url(
            api,
            is_group=is_group,
            chat_id=chat_id,
            file_type=file_type,
            url=file_ref,
        )
        filename = Path(urlparse(file_ref).path).name or filename
    else:
        data, name = await _read_local_file(file_ref)
        if not data:
            return False
        filename = name or filename
        file_type = _guess_file_type(filename)
        file_data_b64 = base64.b64encode(data).decode("ascii")
        media = await _upload_base64(
            api,
            is_group=is_group,
            chat_id=chat_id,
            file_type=file_type,
            file_data_b64=file_data_b64,
            file_name=filename,
        )

    if not media:
        _log.error("[QQ] 上传失败: %s", filename)
        return False

    ok = await _send_rich_media(
        api,
        is_group=is_group,
        chat_id=chat_id,
        media=media,
        msg_id=msg_id,
        msg_seq=msg_seq,
    )
    if ok:
        _log.info("[QQ] 已发送文件 %s (%s)", filename, "群聊" if is_group else "单聊")
    return ok


async def send_file_to_qq(file_path: str) -> bool:
    """主动发送文件到 QQ（不依赖 message 对象，使用运行中 bot 的上下文）。

    从运行中的 NonoQQBot 读取 last_chat_type / last_user_openid / last_group_openid，
    上传文件后以 msg_type=7 发送。
    """
    from services.qq_bot import _runner

    if not (_runner and _runner._client):
        _log.warning("[Push/QQ文件] 运行中 bot 不可用")
        return False

    client = _runner._client
    api = getattr(client, "api", None)
    if not api:
        _log.warning("[Push/QQ文件] 缺少 API 对象")
        return False

    chat_type = client.last_chat_type or "c2c"
    is_group = chat_type == "group"
    chat_id = (client.last_group_openid if is_group else client.last_user_openid or "").strip()
    if not chat_id:
        _log.warning("[Push/QQ文件] 缺少 %s", "group_openid" if is_group else "user_openid")
        return False

    file_ref = (file_path or "").strip()
    if not file_ref:
        return False

    path = Path(file_ref).expanduser()
    if not path.is_file():
        _log.warning("[QQ文件] 文件不存在: %s", file_path)
        return False

    msg_seq = int(time.time() * 1000) % 1000000 + random.randint(1, 1000)
    filename = path.name

    file_data, file_name = await _read_local_file(str(path))
    if not file_data:
        return False
    filename = file_name or filename
    file_type = _guess_file_type(filename)
    file_data_b64 = base64.b64encode(file_data).decode("ascii")

    media = await _upload_base64(
        api,
        is_group=is_group,
        chat_id=chat_id,
        file_type=file_type,
        file_data_b64=file_data_b64,
        file_name=filename,
    )
    if not media:
        _log.error("[QQ文件] 上传失败: %s", filename)
        return False

    ok = await _send_rich_media(
        api,
        is_group=is_group,
        chat_id=chat_id,
        media=media,
        msg_id=None,
        msg_seq=msg_seq,
    )
    if ok:
        _log.info("[QQ文件] 已发送 %s (%s)", filename, "群聊" if is_group else "单聊")
    return ok
