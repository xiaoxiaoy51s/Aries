"""飞书文件/图片发送（上传到飞书服务器，再以 msg_type=image/file 发送）。"""

from __future__ import annotations

import json
import logging
import mimetypes
from pathlib import Path
from typing import Optional

_log = logging.getLogger(__name__)

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".ico"}
# 飞书上传文件接口支持的 file_type
_FILE_TYPE_MAP = {
    ".opus": "opus",
    ".mp4": "mp4",
    ".pdf": "pdf",
    ".doc": "doc",
    ".docx": "doc",
    ".xls": "xls",
    ".xlsx": "xls",
    ".ppt": "stream",
    ".pptx": "stream",
    ".txt": "stream",
    ".csv": "stream",
    ".json": "stream",
    ".md": "stream",
    ".zip": "stream",
    ".mp3": "stream",
    ".wav": "stream",
    ".flac": "stream",
}


def _is_image(path: str) -> bool:
    return Path(path).suffix.lower() in _IMAGE_EXTS


def _guess_file_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    return _FILE_TYPE_MAP.get(ext, "stream")


def _load_feishu_config() -> dict:
    import json as _json
    from pathlib import Path as _Path
    config_path = _Path.home() / ".Aries" / "bot_config.json"
    if not config_path.exists():
        return {}
    try:
        return _json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_lark_client():
    """构建 lark REST 客户端（用于文件上传和 REST 发送）。"""
    import lark_oapi as lark

    config = _load_feishu_config()
    feishu = config.get("feishu", {})
    app_id = (feishu.get("app_id") or "").strip()
    app_secret = (feishu.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        return None, None
    client = (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .log_level(lark.LogLevel.WARNING)
        .build()
    )
    return client, feishu


def _upload_image(client, file_path: str) -> Optional[str]:
    """上传图片到飞书，返回 image_key。"""
    from lark_oapi.api.im.v1.model.create_image_request import CreateImageRequest
    from lark_oapi.api.im.v1.model.create_image_request_body import CreateImageRequestBody

    try:
        with open(file_path, "rb") as f:
            req = (
                CreateImageRequest.builder()
                .request_body(
                    CreateImageRequestBody.builder()
                    .image_type("message")
                    .image(f)
                    .build()
                )
                .build()
            )
            resp = client.im.v1.image.create(req)
        if resp.success() and resp.data and resp.data.image_key:
            _log.info("[飞书文件] 图片上传成功: %s -> %s", Path(file_path).name, resp.data.image_key)
            return resp.data.image_key
        _log.error("[飞书文件] 图片上传失败: code=%s msg=%s", resp.code, resp.msg)
        return None
    except Exception as e:
        _log.error("[飞书文件] 图片上传异常 %s: %s", file_path, e)
        return None


def _upload_file(client, file_path: str) -> Optional[str]:
    """上传文件到飞书，返回 file_key。"""
    from lark_oapi.api.im.v1.model.create_file_request import CreateFileRequest
    from lark_oapi.api.im.v1.model.create_file_request_body import CreateFileRequestBody

    path = Path(file_path)
    file_type = _guess_file_type(file_path)
    file_name = path.name
    try:
        with open(file_path, "rb") as f:
            req = (
                CreateFileRequest.builder()
                .request_body(
                    CreateFileRequestBody.builder()
                    .file_type(file_type)
                    .file_name(file_name)
                    .file(f)
                    .build()
                )
                .build()
            )
            resp = client.im.v1.file.create(req)
        if resp.success() and resp.data and resp.data.file_key:
            _log.info("[飞书文件] 文件上传成功: %s -> %s", file_name, resp.data.file_key)
            return resp.data.file_key
        _log.error("[飞书文件] 文件上传失败: code=%s msg=%s", resp.code, resp.msg)
        return None
    except Exception as e:
        _log.error("[飞书文件] 文件上传异常 %s: %s", file_path, e)
        return None


def _send_message_via_channel(chat_id: str, msg_type: str, content: dict, file_name: str = "") -> bool:
    """通过运行中的 FeishuChannel WebSocket 发送消息。

    FeishuChannel.send 接受 dict：
    - {"text": "..."} → 文本
    - {"image": {"image_key": "xxx"}} → 图片
    - {"file": {"file_key": "xxx", "file_name": "xxx"}} → 文件
    """
    import asyncio

    try:
        from services.feishu_bot import _runner

        if not (_runner and _runner._channel and _runner._loop and _runner._loop.is_running()):
            return False

        effective_chat_id = (_runner.last_chat_id or "").strip() or chat_id
        if not effective_chat_id:
            _log.warning("[飞书文件] 缺少 chat_id")
            return False

        if msg_type == "image":
            send_payload = {"image": content}
        elif msg_type == "file":
            file_payload = dict(content)
            if file_name:
                file_payload["file_name"] = file_name
            send_payload = {"file": file_payload}
        else:
            send_payload = content

        async def _send():
            await _runner._channel.send(effective_chat_id, send_payload)
            return True

        future = asyncio.run_coroutine_threadsafe(_send(), _runner._loop)
        future.result(timeout=30)
        return True
    except Exception as e:
        _log.warning("[飞书文件] Channel 发送失败: %s", e)
        return False


def _send_message_via_rest(chat_id: str, msg_type: str, content: dict) -> bool:
    """通过 REST API 发送消息。"""
    import lark_oapi as lark
    from lark_oapi.api.im.v1.model.create_message_request import CreateMessageRequest
    from lark_oapi.api.im.v1.model.create_message_request_body import CreateMessageRequestBody

    client, feishu = _get_lark_client()
    if not client:
        _log.error("[飞书文件] 无法创建 REST 客户端")
        return False

    content_str = json.dumps(content, ensure_ascii=False)
    req = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type(msg_type)
            .content(content_str)
            .build()
        )
        .build()
    )
    resp = client.im.v1.message.create(req)
    if resp.success():
        _log.info("[飞书文件] REST 发送成功 msg_type=%s", msg_type)
        return True
    _log.error("[飞书文件] REST 发送失败: code=%s msg=%s", resp.code, resp.msg)
    return False


def send_file_to_feishu(file_path: str, chat_id: str = "") -> bool:
    """发送本地文件到飞书会话。

    自动判断文件类型：
    - 图片（png/jpg/gif/webp...）→ 上传图片 → msg_type=image
    - 其他文件 → 上传文件 → msg_type=file

    优先通过运行中的 FeishuChannel 发送，回退到 REST API。
    """
    path = Path(file_path).expanduser()
    if not path.is_file():
        _log.warning("[飞书文件] 文件不存在: %s", file_path)
        return False

    client, feishu = _get_lark_client()
    if not client:
        _log.error("[飞书文件] 缺少 app_id/app_secret，无法上传")
        return False

    is_img = _is_image(file_path)

    if is_img:
        key = _upload_image(client, str(path))
        if not key:
            return False
        msg_type = "image"
        content = {"image_key": key}
    else:
        key = _upload_file(client, str(path))
        if not key:
            return False
        msg_type = "file"
        content = {"file_key": key}

    # 优先 Channel，回退 REST
    if _send_message_via_channel(chat_id, msg_type, content, file_name=path.name):
        _log.info("[飞书文件] 已发送 %s (%s)", path.name, msg_type)
        return True

    effective_chat_id = chat_id
    if not effective_chat_id:
        # 从运行中 bot 获取
        try:
            from services.feishu_bot import _runner
            if _runner:
                effective_chat_id = (_runner.last_chat_id or "").strip()
        except Exception:
            pass

    if not effective_chat_id:
        _log.warning("[飞书文件] 缺少 chat_id（请先用飞书给 bot 发一条消息）")
        return False

    if _send_message_via_rest(effective_chat_id, msg_type, content):
        _log.info("[飞书文件] 已发送 %s (%s via REST)", path.name, msg_type)
        return True

    return False
