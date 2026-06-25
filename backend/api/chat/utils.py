"""聊天 API 的共享工具函数"""
import base64
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from fastapi import HTTPException

from .models import Message


def load_file_as_base64_url(file_path: str, mime_type: Optional[str] = None) -> str:
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()

    if not mime_type:
        ext = path.suffix.lower().lstrip(".")
        mime_map = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
        }
        mime_type = mime_map.get(ext, "application/octet-stream")

    return f"data:{mime_type};base64,{data}"


def save_base64_image(base64_str: str, upload_dir: str = None) -> str:
    if upload_dir is None:
        today = datetime.now().strftime("%Y/%m/%d")
        upload_path = Path.home() / ".Aries" / "uploads" / today
        url_prefix = f"/uploads/{today}"
    else:
        upload_path = Path(upload_dir)
        url_prefix = "/uploads"
    upload_path.mkdir(parents=True, exist_ok=True)

    match = re.match(r'^data:image/(\w+);base64,(.+)$', base64_str)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid base64 image format")

    ext = match.group(1)
    if ext == "jpeg":
        ext = "jpg"
    image_data = base64.b64decode(match.group(2))

    filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = upload_path / filename

    with open(file_path, "wb") as f:
        f.write(image_data)

    return f"{url_prefix}/{filename}"


def extract_and_save_images(user_content) -> Tuple[str, list]:
    text_content = ""
    saved_paths = []

    if isinstance(user_content, list):
        text_parts = []
        for part in user_content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
                elif part.get("type") == "image_url":
                    image_url = part.get("image_url", {})
                    if isinstance(image_url, dict):
                        url = image_url.get("url", "")
                        if url.startswith("data:"):
                            file_path = save_base64_image(url)
                            saved_paths.append(file_path)
                        else:
                            saved_paths.append(url)
        text_content = " ".join(text_parts)
    elif isinstance(user_content, str):
        text_content = user_content

    return text_content, saved_paths


def prepare_messages(messages: list[Message]) -> list:
    result = []
    for msg in messages:
        msg_dict = {"role": msg.role}

        if msg.content is None:
            msg_dict["content"] = None
        elif isinstance(msg.content, str):
            msg_dict["content"] = msg.content
        elif isinstance(msg.content, list):
            content_parts = []
            for part in msg.content:
                if isinstance(part, dict):
                    content_parts.append(part)
                else:
                    content_parts.append(part.model_dump())
            msg_dict["content"] = content_parts

        if msg.name:
            msg_dict["name"] = msg.name
        if msg.tool_calls:
            msg_dict["tool_calls"] = msg.tool_calls
        if msg.tool_call_id:
            msg_dict["tool_call_id"] = msg.tool_call_id

        result.append(msg_dict)
    return result


def _replace_text_content(user_message: dict, text: str) -> None:
    if isinstance(user_message.get("content"), str):
        user_message["content"] = text