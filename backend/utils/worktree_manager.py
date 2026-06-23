"""Worktree Manager - Git Worktree 文件级隔离

参考 Claude Code 的 Worktree 隔离机制，为并行子 Agent 创建独立工作目录。

核心设计：
- 每个 worktree 存放在 <repo_root>/.Aries/worktrees/<slug>/ 下
- 分支命名：worktree/<slug>
- 创建时记录 original_head，用于后续统计变更
- 清理时 fail-closed：有未提交变更则保留，无变更则自动删除
- 快速恢复：如果 worktree 已存在，直接复用
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

WORKTREE_DIR_NAME = ".Aries"
WORKTREE_SUBDIR = "worktrees"


def _is_git_repo(path: str) -> bool:
    """检查指定路径是否在 git 仓库内。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except Exception:
        return False


def _get_git_root(path: str) -> str | None:
    """获取 git 仓库根目录。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _get_default_branch(repo_root: str) -> str:
    """获取仓库的默认分支名。"""
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "main"


def _get_current_head(repo_root: str) -> str | None:
    """获取当前 HEAD 的 commit SHA。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def create_worktree_for_subagent(
    *,
    repo_root: str,
    slug: str,
) -> dict[str, Any] | None:
    """为子 Agent 创建 git worktree 隔离工作空间。

    返回 worktree_info dict，包含：
        path: worktree 工作目录绝对路径
        branch: 分支名
        original_head: 创建前的 HEAD commit SHA（用于变更统计）
        repo_root: 原始仓库根目录

    如果不是 git 仓库或创建失败，返回 None。
    """
    # 1. 检查是否是 git 仓库
    if not _is_git_repo(repo_root):
        logger.debug("worktree: %s 不是 git 仓库，跳过隔离", repo_root)
        return None

    git_root = _get_git_root(repo_root)
    if not git_root:
        return None

    # 2. 确定工作目录和分支名
    worktree_base = Path(git_root) / WORKTREE_DIR_NAME / WORKTREE_SUBDIR
    worktree_base.mkdir(parents=True, exist_ok=True)
    worktree_path = worktree_base / slug
    branch_name = f"worktree/{slug}"

    # 3. 记录原始 HEAD（用于后续变更统计）
    original_head = _get_current_head(git_root) or ""

    # 4. 快速恢复：如果 worktree 已存在，直接复用
    if worktree_path.exists() and (worktree_path / ".git").exists():
        logger.info("worktree: 复用已存在的 worktree %s", worktree_path)
        return {
            "path": str(worktree_path),
            "branch": branch_name,
            "original_head": original_head,
            "repo_root": git_root,
        }

    # 5. 获取默认分支作为 base
    default_branch = _get_default_branch(git_root)

    # 6. 创建 worktree
    try:
        # 先创建分支
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path), default_branch],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            # 分支可能已存在，尝试用已有分支
            result = subprocess.run(
                ["git", "worktree", "add", str(worktree_path), branch_name],
                cwd=git_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.warning("worktree: 创建失败 %s: %s", worktree_path, result.stderr)
                return None

        logger.info("worktree: 已创建 %s (分支 %s)", worktree_path, branch_name)
        return {
            "path": str(worktree_path),
            "branch": branch_name,
            "original_head": original_head,
            "repo_root": git_root,
        }
    except subprocess.TimeoutExpired:
        logger.warning("worktree: 创建超时")
        return None
    except Exception as exc:
        logger.warning("worktree: 创建异常 %s", exc)
        return None


def count_worktree_changes(
    worktree_path: str,
    original_head: str,
) -> int | None:
    """统计 worktree 中的变更数量（未提交文件 + 新提交数）。

    返回 None 表示无法确定（fail-closed：假设不安全，不删除）。
    返回 0 表示无变更，可以安全删除。
    """
    try:
        # 统计未提交文件
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if status_result.returncode != 0:
            return None  # fail-closed

        uncommitted = len([line for line in status_result.stdout.strip().splitlines() if line.strip()])

        # 统计新提交数（相对于 original_head）
        new_commits = 0
        if original_head:
            rev_result = subprocess.run(
                ["git", "rev-list", "--count", f"{original_head}..HEAD"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if rev_result.returncode == 0:
                new_commits = int(rev_result.stdout.strip() or "0")
            else:
                return None  # fail-closed

        return uncommitted + new_commits
    except Exception:
        return None  # fail-closed


def cleanup_worktree(worktree_info: dict[str, Any]) -> dict[str, Any]:
    """清理 worktree。

    fail-closed 设计：
    - 有未提交文件或新提交 → 保留 worktree，返回 {kept: True, path: ...}
    - 无变更 → 删除 worktree 和分支，返回 {kept: False}
    - 无法确定变更 → 保留 worktree（fail-closed）

    返回 dict:
        kept: bool - worktree 是否被保留
        path: str - worktree 路径（如果保留）
        changes: int | None - 变更数量（None 表示无法确定）
    """
    worktree_path = worktree_info.get("path", "")
    original_head = worktree_info.get("original_head", "")
    repo_root = worktree_info.get("repo_root", "")
    branch = worktree_info.get("branch", "")

    if not worktree_path or not Path(worktree_path).exists():
        return {"kept": False, "changes": 0}

    # 统计变更
    changes = count_worktree_changes(worktree_path, original_head)

    # fail-closed：无法确定变更时保留
    if changes is None:
        logger.info("worktree: 无法确定变更数量，保留 %s", worktree_path)
        return {"kept": True, "path": worktree_path, "changes": None}

    # 有变更 → 保留
    if changes > 0:
        logger.info("worktree: 检测到 %d 个变更，保留 %s", changes, worktree_path)
        return {"kept": True, "path": worktree_path, "changes": changes}

    # 无变更 → 删除
    try:
        if repo_root:
            result = subprocess.run(
                ["git", "worktree", "remove", "--force", worktree_path],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning("worktree: 删除失败 %s: %s", worktree_path, result.stderr)
                return {"kept": True, "path": worktree_path, "changes": 0}

            # 删除分支
            if branch:
                subprocess.run(
                    ["git", "branch", "-D", branch],
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

            logger.info("worktree: 已删除 %s (无变更)", worktree_path)
            return {"kept": False, "changes": 0}
    except Exception as exc:
        logger.warning("worktree: 删除异常 %s: %s", worktree_path, exc)
        return {"kept": True, "path": worktree_path, "changes": 0}

    return {"kept": False, "changes": 0}
