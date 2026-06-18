"""Git integration API: status, branch, diff, commit, pull, push."""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/git", tags=["git"])


class CommitRequest(BaseModel):
    work_dir: str
    message: str


class GitActionRequest(BaseModel):
    work_dir: str


def _run_git(work_dir: str, args: list[str]) -> tuple[int, str, str]:
    """执行 git 命令，返回 (returncode, stdout, stderr)。"""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=work_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "git command timed out"
    except FileNotFoundError:
        return -1, "", "git not found"
    except Exception as e:
        return -1, "", str(e)


def _normalize_work_dir(work_dir: str | None) -> str:
    if work_dir and work_dir.strip():
        path = Path(work_dir).expanduser().resolve()
    else:
        path = Path.home() / ".Aries" / "work_dir"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


@router.get("/branch")
async def git_branch(work_dir: str | None = None) -> dict[str, Any]:
    """获取当前分支名。"""
    wd = _normalize_work_dir(work_dir)
    code, stdout, _ = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_git(wd, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    )
    branch = stdout.strip() if code == 0 else ""
    if not branch:
        # 可能处于 detached HEAD，尝试获取短 commit hash
        code2, stdout2, _ = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _run_git(wd, ["rev-parse", "--short", "HEAD"])
        )
        branch = f"({stdout2.strip()})" if code2 == 0 else "unknown"
    return {"branch": branch}


@router.get("/repo-info")
async def git_repo_info(work_dir: str | None = None) -> dict[str, Any]:
    """检测当前目录是否为 Git 仓库，并返回分支信息。"""
    wd = _normalize_work_dir(work_dir)
    code, _, _ = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_git(wd, ["rev-parse", "--git-dir"])
    )
    is_repo = code == 0
    branch = ""
    if is_repo:
        code2, stdout2, _ = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _run_git(wd, ["symbolic-ref", "--quiet", "--short", "HEAD"])
        )
        branch = stdout2.strip() if code2 == 0 else ""
        if not branch:
            code3, stdout3, _ = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _run_git(wd, ["rev-parse", "--short", "HEAD"])
            )
            branch = f"({stdout3.strip()})" if code3 == 0 else "unknown"
    return {"is_repo": is_repo, "branch": branch}


@router.get("/status")
async def git_status(work_dir: str | None = None) -> dict[str, Any]:
    """获取工作区文件状态列表（未跟踪目录展开为文件）。"""
    wd = _normalize_work_dir(work_dir)

    files: list[dict[str, str]] = []

    # 1. 获取已跟踪文件的变更状态（排除未跟踪条目，因为它们可能是目录）
    code, stdout, _ = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_git(wd, ["status", "--porcelain=v1", "-z"])
    )
    if code == 0:
        entries = stdout.split("\0")
        i = 0
        while i < len(entries):
            entry = entries[i]
            if not entry or len(entry) < 3:
                i += 1
                continue
            status_code = entry[:2]
            path = entry[3:]
            # 跳过未跟踪条目，稍后通过 ls-files 统一获取（会展开为文件）
            if status_code == "??":
                i += 1
                continue
            # 处理重命名: R 状态后面跟着旧路径
            if status_code[0] == "R" and i + 1 < len(entries):
                i += 2
            else:
                i += 1
            status_char = _map_status(status_code)
            files.append({"path": path, "status": status_char})

    # 2. 获取所有未跟踪文件（递归展开目录，遵守 .gitignore）
    code2, stdout2, _ = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_git(wd, ["ls-files", "--others", "--exclude-standard"])
    )
    if code2 == 0:
        for line in stdout2.strip().split("\n"):
            line = line.strip()
            if line and not line.endswith("/"):
                files.append({"path": line, "status": "?"})

    return {"files": files}


def _map_status(code: str) -> str:
    """将 git status 的 XY 状态码映射为单字符标记。"""
    x, y = code[0], code[1]
    if x == "?" or y == "?":
        return "?"
    if x == "A" or y == "A":
        return "A"
    if x == "D" or y == "D":
        return "D"
    if x == "R" or y == "R":
        return "R"
    if x == "U" or y == "U":
        return "U"
    return "M"


@router.get("/diff")
async def git_diff(
    work_dir: str | None = None,
    file_path: str | None = None,
) -> dict[str, Any]:
    """获取指定文件的 diff（原始内容 vs 修改后内容）。

    参考 opencode-dev git.ts 的 patch 逻辑:
    - 已跟踪文件: git diff HEAD -- <file>
    - 未跟踪文件: git diff --no-index /dev/null <file>
    """
    wd = _normalize_work_dir(work_dir)
    if not file_path:
        return {"original": "", "modified": ""}

    # 先检查文件是否被跟踪
    code, stdout, _ = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_git(wd, ["ls-files", "--error-unmatch", file_path])
    )
    is_tracked = code == 0

    if is_tracked:
        # 已跟踪文件: 获取 HEAD 版本和工作区版本
        code, original, _ = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _run_git(wd, ["show", f"HEAD:{file_path}"])
        )
        if code != 0:
            original = ""
        # 读取工作区文件内容
        modified = _read_file(wd, file_path)
    else:
        # 未跟踪文件: 原始为空，修改后为文件内容
        original = ""
        modified = _read_file(wd, file_path)

    return {"original": original, "modified": modified}


def _read_file(work_dir: str, file_path: str) -> str:
    """安全读取文件内容。"""
    try:
        full_path = Path(work_dir) / file_path
        if not full_path.exists() or not full_path.is_file():
            return ""
        return full_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


@router.post("/commit")
async def git_commit(req: CommitRequest) -> dict[str, Any]:
    """提交所有更改。"""
    wd = _normalize_work_dir(req.work_dir)

    # git add -A
    await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_git(wd, ["add", "-A"])
    )

    # git commit
    code, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_git(wd, ["commit", "-m", req.message])
    )
    if code != 0:
        return {"success": False, "message": stderr.strip() or stdout.strip() or "commit failed"}
    return {"success": True, "message": stdout.strip()}


@router.post("/pull")
async def git_pull(req: GitActionRequest) -> dict[str, Any]:
    """拉取远程更新。"""
    wd = _normalize_work_dir(req.work_dir)
    code, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_git(wd, ["pull"])
    )
    if code != 0:
        return {"success": False, "message": stderr.strip() or stdout.strip() or "pull failed"}
    return {"success": True, "message": stdout.strip()}


@router.post("/push")
async def git_push(req: GitActionRequest) -> dict[str, Any]:
    """推送到远程。"""
    wd = _normalize_work_dir(req.work_dir)
    code, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_git(wd, ["push"])
    )
    if code != 0:
        return {"success": False, "message": stderr.strip() or stdout.strip() or "push failed"}
    return {"success": True, "message": stdout.strip()}


@router.post("/init")
async def git_init(req: GitActionRequest) -> dict[str, Any]:
    """初始化 Git 仓库。"""
    wd = _normalize_work_dir(req.work_dir)
    code, stdout, stderr = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_git(wd, ["init"])
    )
    if code != 0:
        return {"success": False, "message": stderr.strip() or stdout.strip() or "init failed"}
    return {"success": True, "message": stdout.strip()}


@router.get("/log")
async def git_log(work_dir: str | None = None, limit: int = 30) -> dict[str, Any]:
    """获取提交历史。"""
    wd = _normalize_work_dir(work_dir)
    code, stdout, _ = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_git(
            wd, ["log", f"--max-count={limit}", "--pretty=format:%H|%s|%an|%ae|%ar"]
        )
    )
    commits: list[dict[str, str]] = []
    if code == 0:
        for line in stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("|", 4)
            if len(parts) >= 5:
                commits.append({
                    "hash": parts[0],
                    "short_hash": parts[0][:7],
                    "message": parts[1],
                    "author": parts[2],
                    "email": parts[3],
                    "date": parts[4],
                })
    return {"commits": commits}


@router.get("/commit-files")
async def git_commit_files(
    work_dir: str | None = None,
    hash: str | None = None,
) -> dict[str, Any]:
    """获取某次提交修改的文件列表。"""
    wd = _normalize_work_dir(work_dir)
    if not hash:
        return {"files": []}
    code, stdout, _ = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_git(wd, ["show", "--name-status", "--pretty=format:", hash])
    )
    files: list[dict[str, str]] = []
    if code == 0:
        for line in stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                raw_status = parts[0]
                # --name-status 返回 M/A/D/Rxx/Cxx 等格式，取首字母即可
                status_char = raw_status[0] if raw_status else "M"
                # R 和 C 后面可能跟百分比数字，只保留首字母
                if status_char not in ("M", "A", "D", "R", "C", "U"):
                    status_char = "M"
                # 重命名/复制: 旧路径在 parts[2]
                path = parts[1]
                files.append({"path": path, "status": status_char})
    return {"files": files}


@router.get("/commit-diff")
async def git_commit_diff(
    work_dir: str | None = None,
    hash: str | None = None,
    file_path: str | None = None,
) -> dict[str, Any]:
    """获取某次提交中指定文件的 diff（与父提交对比）。"""
    wd = _normalize_work_dir(work_dir)
    if not hash or not file_path:
        return {"original": "", "modified": ""}

    # 获取父提交中的文件内容
    code1, original, _ = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_git(wd, ["show", f"{hash}^:{file_path}"])
    )
    if code1 != 0:
        original = ""

    # 获取该提交中的文件内容
    code2, modified, _ = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _run_git(wd, ["show", f"{hash}:{file_path}"])
    )
    if code2 != 0:
        modified = ""

    return {"original": original, "modified": modified}
