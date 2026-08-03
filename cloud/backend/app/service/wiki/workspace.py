"""每用户 wiki 工作区路径。位于 ~/.Aries/{email}/wiki/。

与现有 per-user 根目录（config/sessions/workspaces）并列，邮箱直接作目录名，
沿用项目既有约定（见 model_config_repository / session_logger）。

存储方式（纯文件系统，无数据库/向量）：
- wiki/                    知识库根目录，AI 按需自由创建子文件夹（如 编程/Python/）
- wiki/_index.md           记忆索引：文件夹 -> 内容摘要/关键词/更新时间（AI 维护）
- raw/                     原始素材（上传的文件 / 抓取的链接 html / 口述原文），用于溯源
"""
from __future__ import annotations

from pathlib import Path

_ARIES_HOME = Path.home() / ".Aries"

# 元文件（不视为知识文档，图谱/列表/检索均排除）
_META_EXCLUDE = {"_index.md", "index.md", "log.md", "overview.md", "lint-report.md", "health-report.md"}


class WikiWorkspace:
    """单个用户 wiki 工作区的路径集合。

    索引机制：每个文件夹内都有一份 _index.md（该目录主题 + 子目录入口 + 文档摘要），
    顶层 wiki/_index.md 为总入口。索引文件不视为知识文档。
    """

    def __init__(self, email: str):
        self.email = email
        self.user_home: Path = _ARIES_HOME / email
        self.root: Path = self.user_home / "wiki"
        self.index_file: Path = self.root / "_index.md"   # 顶层总索引
        self.raw: Path = self.user_home / "raw"
        self.raw_links: Path = self.raw / "links"
        self.raw_diary: Path = self.raw / "diary"
        self.raw_notes: Path = self.raw / "notes"

    def ensure(self) -> "WikiWorkspace":
        """创建所有目录，并初始化顶层记忆索引。"""
        for d in (self.root, self.raw, self.raw_links, self.raw_diary, self.raw_notes):
            d.mkdir(parents=True, exist_ok=True)
        if not self.index_file.exists():
            self.index_file.write_text(
                "# 知识库记忆索引\n\n"
                "> 每个文件夹内有自己的 _index.md。本文件是总入口：记录子目录主题与根目录文档摘要。\n\n",
                encoding="utf-8",
            )
        return self

    def index_for(self, folder: Path) -> Path:
        """folder 目录内的 _index.md。"""
        return folder / "_index.md"

    def all_pages(self) -> list[Path]:
        """所有知识文档 md 文件（递归，排除各层 _index.md 等元文件）。"""
        if not self.root.exists():
            return []
        return [p for p in self.root.rglob("*.md") if p.name not in _META_EXCLUDE]

    def all_folders(self) -> list[Path]:
        """含文档（或子目录）的所有文件夹，按相对根目录的路径排序。"""
        folders = {p.parent for p in self.all_pages()}
        return sorted(folders, key=lambda d: self.rel_path(d)) if folders else []

    def rel_path(self, path: Path) -> str:
        """相对 wiki 目录的 posix 路径（含 .md），用于前端展示与溯源。"""
        return path.relative_to(self.root).as_posix()

    def safe_join(self, rel: str) -> Path | None:
        """把相对路径安全解析到 wiki 根内，防路径穿越；非法返回 None。"""
        try:
            target = (self.root / rel).resolve()
            target.relative_to(self.root.resolve())
        except ValueError:
            return None
        return target
