from __future__ import annotations

import fnmatch
import os
from datetime import datetime
from pathlib import Path
from typing import Any


class UserFileManager:
    def __init__(self, user_email: str | None = None, work_dir: str | None = None) -> None:
        self.user_email = user_email or os.environ.get("USER_EMAIL", "")
        # 默认存储根目录：~/.Aries（与 skills/session/uploads/temp 平级）
        self.default_base = Path.home() / ".Aries"
        # 用户工作区：默认存到 ~/.Aries/work_dir 下，让日期子目录更整洁；
        # 显式传 work_dir 时优先使用自定义目录。
        self.default_work_dir = self.default_base / "work_dir"
        if work_dir and work_dir.strip():
            self.base_dir = Path(work_dir).expanduser().resolve()
        else:
            self.base_dir = self.default_work_dir
        self.user_dir = self.base_dir
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.user_dir.mkdir(parents=True, exist_ok=True)

    def get_today_dir(self) -> Path:
        """已废弃：不再使用日期子目录，直接返回 user_dir。"""
        return self.user_dir

    def get_user_dir(self) -> Path:
        return self.user_dir

    def resolve_list_dir(self, subdir: str | None = None) -> Path:
        if not subdir:
            return self.user_dir
        candidate = Path(subdir).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (self.user_dir / subdir).resolve()

    def list_files(self, subdir: str | None = None, pattern: str = "*") -> list[dict[str, Any]]:
        target_dir = self.resolve_list_dir(subdir)
        glob_pattern = (pattern or "*").strip() or "*"

        if not target_dir.exists() or not target_dir.is_dir():
            return []

        files: list[dict[str, Any]] = []
        for item in sorted(target_dir.iterdir(), key=lambda p: p.name.lower()):
            if not fnmatch.fnmatch(item.name, glob_pattern):
                continue
            entry: dict[str, Any] = {
                "name": item.name,
                "path": str(item),
                "absolute_path": str(item.resolve()),
                "is_dir": item.is_dir(),
            }
            if item.is_file():
                stat = item.stat()
                entry["size"] = stat.st_size
                entry["modified"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
            files.append(entry)

        return sorted(files, key=lambda x: (not x["is_dir"], x["name"].lower()))

    def fuzzy_search(self, query: str, subdir: str | None = None) -> list[dict[str, Any]]:
        query_lower = query.lower()
        all_files = self.list_files(subdir)
        return [file_info for file_info in all_files if query_lower in file_info["name"].lower()]

    def resolve_file_path(self, file_path: str, use_today: bool = False) -> Path:
        candidate = Path(file_path)

        if candidate.is_absolute():
            target = candidate.resolve()
            if not self._is_allowed_path(target):
                raise ValueError(f"无效路径: {target}")
            return target

        path_str = str(candidate).replace("\\", "/")

        user_dir_str = str(self.user_dir).replace("\\", "/")

        if path_str.startswith(user_dir_str):
            target = candidate.resolve()
        else:
            base = self.user_dir
            target = (base / candidate).resolve()

        if not self._is_allowed_path(target):
            raise ValueError(f"无效路径: {target}")

        return target

    def is_outside_work_dir(self, path: Path) -> bool:
        """判断路径是否在当前工作目录之外。"""
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError, ValueError):
            return True
        allowed = self.user_dir.resolve()
        if resolved == allowed or str(resolved).startswith(str(allowed) + os.sep):
            return False
        # 也允许默认工作目录下的路径（当使用自定义工作目录时）
        default_wd = self.default_work_dir.resolve()
        if resolved == default_wd or str(resolved).startswith(str(default_wd) + os.sep):
            return False
        return True

    def _is_allowed_path(self, path: Path) -> bool:
        try:
            path.resolve()
            return True
        except (OSError, RuntimeError, ValueError):
            return False

    def delete_file(self, file_path: str) -> bool:
        """删除文件（移到系统回收站，非物理删除）。"""
        result = self.move_to_trash(file_path)
        return result["success"]

    def move_to_trash(self, file_path: str) -> dict[str, Any]:
        """将文件或目录移到系统回收站（跨平台，调用操作系统 API）。

        使用 send2trash 库，底层调用：
        - Windows: IFileOperation COM 接口
        - macOS: NSWorkspace recycleURLs
        - Linux: FreeDesktop.org Trash 规范

        Returns:
            dict: {success, error, previous_content, is_dir}
        """
        from send2trash import send2trash

        target = self.resolve_file_path(file_path, use_today=False)
        if not target.exists():
            return {"success": False, "error": f"文件不存在: {target}"}

        is_dir = target.is_dir()

        # 删除前读取文本内容，用于日志记录和回退（仅文件，非目录）
        previous_content = ""
        if not is_dir and target.is_file():
            try:
                previous_content = target.read_text(encoding="utf-8", errors="replace")
            except Exception:
                previous_content = ""

        # 移到系统回收站
        try:
            send2trash(str(target))
        except Exception as exc:
            return {"success": False, "error": f"移到回收站失败: {exc}"}

        return {
            "success": True,
            "error": "",
            "previous_content": previous_content,
            "is_dir": is_dir,
        }
