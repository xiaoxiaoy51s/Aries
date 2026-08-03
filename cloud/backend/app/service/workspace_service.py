"""用户工作目录与文件上传/下载业务逻辑。"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.config.settings import settings
from app.tools.sandbox import (
    ensure_workspace,
    get_upload_dir,
    get_workspaces_root,
    list_workspaces,
    resolve_workspace_path,
    validate_workspace_name,
)


class WorkspaceService:
    @staticmethod
    def list_user_workspaces(user_email: str) -> list[dict[str, Any]]:
        ensure_workspace(user_email, "default")
        return list_workspaces(user_email)

    @staticmethod
    def create_workspace(user_email: str, name: str) -> dict[str, Any]:
        path = ensure_workspace(user_email, name)
        stat = path.stat()
        return {"name": path.name, "path": str(path), "modified_at": stat.st_mtime}

    @staticmethod
    def list_files(user_email: str, workspace_name: str, rel_path: str = "") -> list[dict[str, Any]]:
        workspace = ensure_workspace(user_email, workspace_name)
        target, err = resolve_workspace_path(workspace, rel_path or ".")
        if err or target is None:
            raise ValueError(err or "路径无效")
        if not target.exists():
            raise FileNotFoundError(f"路径不存在：{rel_path or '.'}")
        if not target.is_dir():
            raise ValueError(f"不是目录：{rel_path}")

        items: list[dict[str, Any]] = []
        for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            rel = os.path.relpath(entry, workspace).replace("\\", "/")
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "path": rel,
                "is_dir": entry.is_dir(),
                "size": stat.st_size if entry.is_file() else 0,
                "modified_at": stat.st_mtime,
            })
        return items

    @staticmethod
    def resolve_download_path(user_email: str, workspace_name: str, rel_path: str) -> Path:
        workspace = ensure_workspace(user_email, workspace_name)
        target, err = resolve_workspace_path(workspace, rel_path)
        if err or target is None:
            raise ValueError(err or "路径无效")
        if not target.exists():
            raise FileNotFoundError(f"文件不存在：{rel_path}")
        if not target.is_file():
            raise ValueError(f"不是文件：{rel_path}")
        return target

    @staticmethod
    def save_file_content(user_email: str, workspace_name: str, rel_path: str, content: str) -> dict:
        """将文本内容写入工作目录内的文件。"""
        workspace = ensure_workspace(user_email, workspace_name)
        target, err = resolve_workspace_path(workspace, rel_path)
        if err or target is None:
            raise ValueError(err or "路径无效")
        if not target.exists():
            raise FileNotFoundError(f"文件不存在：{rel_path}")
        if not target.is_file():
            raise ValueError(f"不是文件：{rel_path}")
        if len(content.encode("utf-8")) > settings.SHELL_MAX_FILE_SIZE:
            raise ValueError(f"内容过大（上限 {settings.SHELL_MAX_FILE_SIZE} 字节）")
        target.write_text(content, encoding="utf-8")
        return {"path": rel_path, "size": len(content.encode("utf-8"))}

    @staticmethod
    def create_entry(user_email: str, workspace_name: str, rel_path: str, is_dir: bool) -> dict[str, Any]:
        """在工作目录内创建空文件或文件夹。"""
        workspace = ensure_workspace(user_email, workspace_name)
        target, err = resolve_workspace_path(workspace, rel_path)
        if err or target is None:
            raise ValueError(err or "路径无效")
        if target == workspace:
            raise ValueError("不能在根路径创建同名项")
        if target.exists():
            raise ValueError(f"已存在：{rel_path}")
        if is_dir:
            target.mkdir(parents=True, exist_ok=False)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")
        rel = os.path.relpath(target, workspace).replace("\\", "/")
        return {"path": rel, "name": target.name, "is_dir": is_dir}

    @staticmethod
    async def save_upload_to_workspace(
        user_email: str,
        workspace_name: str,
        rel_dir: str,
        file: UploadFile,
    ) -> dict[str, Any]:
        workspace = ensure_workspace(user_email, workspace_name)
        dest_dir, err = resolve_workspace_path(workspace, rel_dir or ".")
        if err or dest_dir is None:
            raise ValueError(err or "目标目录无效")
        dest_dir.mkdir(parents=True, exist_ok=True)
        if not dest_dir.is_dir():
            raise ValueError("目标路径不是目录")

        original = (file.filename or "upload").replace("\\", "/").split("/")[-1]
        safe_name = _safe_filename(original)
        dest = dest_dir / safe_name
        if dest.exists():
            stem = dest.stem
            suffix = dest.suffix
            dest = dest_dir / f"{stem}_{uuid.uuid4().hex[:6]}{suffix}"

        content = await file.read()
        if len(content) > settings.SHELL_MAX_FILE_SIZE:
            raise ValueError(f"文件过大（上限 {settings.SHELL_MAX_FILE_SIZE} 字节）")
        dest.write_bytes(content)

        rel = os.path.relpath(dest, workspace).replace("\\", "/")
        return {"path": rel, "name": dest.name, "size": len(content)}

    @staticmethod
    async def save_upload_to_upload_dir(user_email: str, file: UploadFile) -> dict[str, Any]:
        upload_dir = get_upload_dir(user_email)
        original = (file.filename or "upload").replace("\\", "/").split("/")[-1]
        safe_name = _safe_filename(original)
        dest = upload_dir / safe_name
        if dest.exists():
            stem = dest.stem
            suffix = dest.suffix
            dest = upload_dir / f"{stem}_{uuid.uuid4().hex[:6]}{suffix}"

        content = await file.read()
        if len(content) > settings.SHELL_MAX_FILE_SIZE:
            raise ValueError(f"文件过大（上限 {settings.SHELL_MAX_FILE_SIZE} 字节）")
        dest.write_bytes(content)

        rel = dest.name
        return {"path": rel, "name": dest.name, "size": len(content), "full_path": str(dest)}

    @staticmethod
    def list_upload_files(user_email: str) -> list[dict[str, Any]]:
        upload_dir = get_upload_dir(user_email)
        items: list[dict[str, Any]] = []
        for entry in sorted(upload_dir.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_file():
                continue
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "path": entry.name,
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
            })
        return items

    @staticmethod
    def resolve_upload_download(user_email: str, filename: str) -> Path:
        upload_dir = get_upload_dir(user_email)
        target = upload_dir / _safe_filename(filename.replace("\\", "/").split("/")[-1])
        if not target.exists() or not target.is_file():
            raise FileNotFoundError("文件不存在")
        try:
            target.resolve().relative_to(upload_dir.resolve())
        except ValueError:
            raise ValueError("路径无效")
        return target

    @staticmethod
    def delete_workspace_file(user_email: str, workspace_name: str, rel_path: str) -> None:
        workspace = ensure_workspace(user_email, workspace_name)
        target, err = resolve_workspace_path(workspace, rel_path)
        if err or target is None:
            raise ValueError(err or "路径无效")
        if not target.exists():
            raise FileNotFoundError(f"路径不存在：{rel_path}")
        if target == workspace:
            raise ValueError("不能删除工作目录根路径")
        if target.is_dir():
            import shutil
            shutil.rmtree(target)
        else:
            target.unlink()

    @staticmethod
    def rename_workspace_file(user_email: str, workspace_name: str, rel_path: str, new_name: str) -> dict:
        workspace = ensure_workspace(user_email, workspace_name)
        target, err = resolve_workspace_path(workspace, rel_path)
        if err or target is None:
            raise ValueError(err or "路径无效")
        if not target.exists():
            raise FileNotFoundError(f"路径不存在：{rel_path}")
        if target == workspace:
            raise ValueError("不能重命名工作目录根路径")
        safe = _safe_filename(new_name)
        if not safe or safe in (".", ".."):
            raise ValueError("名称无效")
        dest = target.parent / safe
        try:
            dest.resolve().relative_to(workspace.resolve())
        except ValueError:
            raise ValueError("目标路径无效")
        if dest.exists() and dest != target:
            raise ValueError("同名项已存在")
        os.rename(target, dest)
        rel = os.path.relpath(dest, workspace).replace("\\", "/")
        return {"path": rel, "name": dest.name, "is_dir": dest.is_dir()}

    @staticmethod
    def workspace_exists(user_email: str, workspace_name: str) -> bool:
        try:
            name = validate_workspace_name(workspace_name)
        except ValueError:
            return False
        return (get_workspaces_root(user_email) / name).is_dir()

    @staticmethod
    def rename_workspace(user_email: str, old_name: str, new_name: str) -> dict:
        """重命名工作目录（目录本身重命名）。"""
        root = get_workspaces_root(user_email)
        old_path = root / validate_workspace_name(old_name)
        if not old_path.exists():
            raise FileNotFoundError(f"工作目录不存在：{old_name}")
        new_path = root / validate_workspace_name(new_name)
        if new_path.exists():
            raise ValueError(f"目标名称已存在：{new_name}")
        old_path.rename(new_path)
        stat = new_path.stat()
        return {"name": new_path.name, "path": str(new_path), "modified_at": stat.st_mtime}

    @staticmethod
    def delete_workspace(user_email: str, workspace_name: str) -> None:
        """删除工作目录（删除整个目录树）。"""
        root = get_workspaces_root(user_email)
        path = root / validate_workspace_name(workspace_name)
        if not path.exists():
            raise FileNotFoundError(f"工作目录不存在：{workspace_name}")
        if path == root / "default":
            raise ValueError("不能删除默认工作目录")
        import shutil
        shutil.rmtree(path)


def _safe_filename(name: str) -> str:
    clean = (name or "file").strip()
    clean = clean.replace("\x00", "").replace("\\", "_").replace("/", "_")
    if not clean or clean in (".", ".."):
        clean = "file"
    return clean[:200]
