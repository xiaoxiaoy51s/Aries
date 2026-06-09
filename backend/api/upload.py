import uuid
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/upload", tags=["upload"])

UPLOAD_DIR = (Path.home() / ".MIMOClaw" / "uploads").resolve()
UPLOAD_DIR.mkdir(exist_ok=True)


class UploadResponse(BaseModel):
    success: bool
    filename: str
    filepath: str
    url: str
    size: int
    mime_type: str


class Base64UploadRequest(BaseModel):
    data: str
    filename: Optional[str] = None
    mime_type: Optional[str] = None


def get_mime_type(filename: str) -> str:
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    mime_map = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "m4a": "audio/mp4",
        "ogg": "audio/ogg",
        "mp4": "video/mp4",
        "webm": "video/webm",
        "mov": "video/quicktime",
        "pdf": "application/pdf",
        "txt": "text/plain",
        "json": "application/json",
    }
    return mime_map.get(ext, "application/octet-stream")


@router.post("/", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    today = datetime.now().strftime("%Y/%m/%d")
    upload_path = UPLOAD_DIR / today
    upload_path.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4().hex[:8]
    original_name = file.filename or "unknown"
    ext = original_name.split(".")[-1] if "." in original_name else ""
    new_filename = f"{file_id}.{ext}" if ext else file_id

    file_path = upload_path / new_filename

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    relative_path = f"{today}/{new_filename}"

    return UploadResponse(
        success=True,
        filename=original_name,
        filepath=str(file_path),
        url=f"/upload/{relative_path}",
        size=len(content),
        mime_type=get_mime_type(original_name),
    )


@router.post("/base64", response_model=UploadResponse)
async def upload_base64(request: Base64UploadRequest):
    try:
        if "," in request.data:
            header, data = request.data.split(",", 1)
            if "data:" in header:
                mime_type = header.split("data:")[1].split(";")[0]
            else:
                mime_type = request.mime_type or "application/octet-stream"
        else:
            data = request.data
            mime_type = request.mime_type or "application/octet-stream"

        content = base64.b64decode(data)

        today = datetime.now().strftime("%Y/%m/%d")
        upload_path = UPLOAD_DIR / today
        upload_path.mkdir(parents=True, exist_ok=True)

        file_id = uuid.uuid4().hex[:8]

        ext_map = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/gif": "gif",
            "image/webp": "webp",
            "audio/mpeg": "mp3",
            "audio/wav": "wav",
            "audio/mp4": "m4a",
            "audio/ogg": "ogg",
            "video/mp4": "mp4",
            "video/webm": "webm",
            "video/quicktime": "mov",
        }
        ext = ext_map.get(mime_type, "bin")

        if request.filename:
            original_name = request.filename
        else:
            original_name = f"{file_id}.{ext}"

        new_filename = f"{file_id}.{ext}"
        file_path = upload_path / new_filename

        with open(file_path, "wb") as f:
            f.write(content)

        relative_path = f"{today}/{new_filename}"

        return UploadResponse(
            success=True,
            filename=original_name,
            filepath=str(file_path),
            url=f"/upload/{relative_path}",
            size=len(content),
            mime_type=mime_type,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to decode base64: {str(e)}")


@router.get("/{year}/{month}/{day}/{filename}")
async def get_uploaded_file(year: str, month: str, day: str, filename: str):
    file_path = UPLOAD_DIR / year / month / day / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


@router.delete("/{year}/{month}/{day}/{filename}")
async def delete_uploaded_file(year: str, month: str, day: str, filename: str):
    file_path = UPLOAD_DIR / year / month / day / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    os.remove(file_path)
    return {"success": True, "message": "File deleted"}
