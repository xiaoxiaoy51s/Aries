"""用户记忆文件业务逻辑。

记忆分两层：
  全局记忆  ~/.Aries/{email}/memory/user_profile.md        跨项目跨对话
  项目记忆  ~/.Aries/{email}/memory/{workspace_name}/memory.md  该 workspace 下所有对话
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.tools.sandbox import get_user_home, validate_workspace_name

# 单个记忆文件最大字符数，防止滥用
MAX_MEMORY_CHARS = 32_000

GLOBAL_MEMORY_FILE = "user_profile.md"
PROJECT_MEMORY_FILE = "memory.md"


class MemoryService:
    # ============ 路径 ============

    @staticmethod
    def _memory_root(user_email: str) -> Path:
        return get_user_home(user_email) / "memory"

    @staticmethod
    def get_global_memory_path(user_email: str) -> Path:
        return MemoryService._memory_root(user_email) / GLOBAL_MEMORY_FILE

    @staticmethod
    def get_project_memory_path(user_email: str, workspace_name: str) -> Path:
        name = validate_workspace_name(workspace_name)
        return MemoryService._memory_root(user_email) / name / PROJECT_MEMORY_FILE

    # ============ 全局记忆 ============

    @staticmethod
    def read_global_memory(user_email: str) -> str:
        path = MemoryService.get_global_memory_path(user_email)
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")[:MAX_MEMORY_CHARS]

    @staticmethod
    def write_global_memory(user_email: str, content: str) -> dict[str, Any]:
        text = (content or "").strip()
        path = MemoryService.get_global_memory_path(user_email)
        if not text:
            # 内容为空时删除文件，保持目录干净
            if path.is_file():
                path.unlink()
            return {"success": True, "content": "", "file_path": str(path), "exists": False}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        return {"success": True, "content": text, "file_path": str(path), "exists": True}

    # ============ 项目记忆 ============

    @staticmethod
    def read_project_memory(user_email: str, workspace_name: str) -> str:
        path = MemoryService.get_project_memory_path(user_email, workspace_name)
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")[:MAX_MEMORY_CHARS]

    @staticmethod
    def write_project_memory(user_email: str, workspace_name: str, content: str) -> dict[str, Any]:
        text = (content or "").strip()
        path = MemoryService.get_project_memory_path(user_email, workspace_name)
        if not text:
            if path.is_file():
                path.unlink()
            return {"success": True, "content": "", "file_path": str(path), "exists": False}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        return {"success": True, "content": text, "file_path": str(path), "exists": True}

    # ============ 项目记忆列表 ============

    @staticmethod
    def list_project_memories(user_email: str) -> list[dict[str, Any]]:
        """扫描 memory 目录下各 workspace 子目录的 memory.md 状态。

        同时合并 workspaces 目录中已有但尚未生成记忆文件的 workspace，
        保证前端下拉框能展示全部可选项目。
        """
        from app.tools.sandbox import get_workspaces_root

        # 收集所有 workspace 名称（来自 workspaces 目录 + memory 目录）
        names: set[str] = set()

        workspaces_root = get_workspaces_root(user_email)
        for entry in workspaces_root.iterdir():
            if entry.is_dir():
                names.add(entry.name)

        memory_root = MemoryService._memory_root(user_email)
        if memory_root.is_dir():
            for entry in memory_root.iterdir():
                if entry.is_dir():
                    names.add(entry.name)

        items: list[dict[str, Any]] = []
        for name in sorted(names, key=lambda s: s.lower()):
            path = MemoryService.get_project_memory_path(user_email, name)
            items.append({
                "workspace": name,
                "has_memory": path.is_file(),
                "file_path": str(path),
            })
        return items
