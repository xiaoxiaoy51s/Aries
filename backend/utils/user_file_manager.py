from __future__ import annotations

import fnmatch
import os
from datetime import datetime
from pathlib import Path
from typing import Any


class UserFileManager:
    def __init__(self, user_email: str | None = None, work_dir: str | None = None) -> None:
        self.user_email = user_email or os.environ.get("USER_EMAIL", "")
        self.default_base = Path.home() / ".MIMOClaw"
        # 如果显式传了 work_dir 就用它，否则用默认 ~/.MIMOClaw
        if work_dir and work_dir.strip():
            self.base_dir = Path(work_dir).expanduser().resolve()
        else:
            self.base_dir = self.default_base
        self.user_dir = self.base_dir
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.user_dir.mkdir(parents=True, exist_ok=True)

    def get_today_dir(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        today_dir = self.user_dir / today
        today_dir.mkdir(parents=True, exist_ok=True)
        return today_dir

    def get_user_dir(self) -> Path:
        return self.user_dir

    def resolve_list_dir(self, subdir: str | None = None) -> Path:
        if not subdir:
            return self.user_dir
        candidate = Path(subdir)
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
        # 如果工作目录是用户自定义的，就不要再套日期子目录
        is_custom_work_dir = self.base_dir != self.default_base

        user_dir_str = str(self.user_dir).replace("\\", "/")
        today_str = datetime.now().strftime("%Y-%m-%d")

        if use_today and not is_custom_work_dir and path_str.startswith(today_str + "/"):
            base = self.user_dir
            target = (base / candidate).resolve()
        elif path_str.startswith(user_dir_str):
            target = candidate.resolve()
        else:
            if use_today and not is_custom_work_dir:
                base = self.get_today_dir()
            else:
                base = self.user_dir
            target = (base / candidate).resolve()

        if not self._is_allowed_path(target):
            raise ValueError(f"无效路径: {target}")

        return target

    def _is_allowed_path(self, path: Path) -> bool:
        try:
            path.resolve()
            return True
        except (OSError, RuntimeError, ValueError):
            return False

    def delete_file(self, file_path: str) -> bool:
        target = self.resolve_file_path(file_path, use_today=False)
        if not target.exists():
            return False
        if target.is_dir():
            import shutil
            shutil.rmtree(target)
            return True
        target.unlink()
        return True
