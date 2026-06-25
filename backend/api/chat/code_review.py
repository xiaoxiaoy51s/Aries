"""代码审查专用逻辑"""
import re
import subprocess
from typing import Optional, Tuple

from prompt.code_review_prompts import (
    CODE_REVIEW_SYSTEM_PROMPT,
    CODE_REVIEW_USER_PROMPTS,
    CODE_REVIEW_MODES,
    DEPENDENCY_EXCLUDE_PATTERNS,
)

CODE_REVIEW_MARKER_RE = re.compile(
    r"^@code_review(?:\s+(unstaged|staged|branch|commit|full))?(?:\s+|\n|$)",
    re.IGNORECASE,
)


def extract_code_review_marker(text: str) -> Tuple[Optional[str], str]:
    """提取代码审查标记，返回 (模式, 清理后的文本)"""
    match = CODE_REVIEW_MARKER_RE.match(text or "")
    if not match:
        return None, text
    mode = (match.group(1) or "branch").lower()
    return mode, (text[match.end():] or "").lstrip()


def detect_base_branch(work_dir: str) -> str:
    """自动检测默认基础分支名称。"""
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, cwd=work_dir, timeout=5,
        )
        if result.returncode == 0:
            ref = result.stdout.strip()
            return ref.replace("refs/remotes/origin/", "") or "main"
    except Exception:
        pass
    # 兜底：检查 main / master 是否存在
    for branch in ("main", "master"):
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--verify", f"origin/{branch}"],
                capture_output=True, text=True, cwd=work_dir, timeout=5,
            )
            if r.returncode == 0:
                return branch
        except Exception:
            pass
    return "main"


def fetch_review_diff(mode: str, work_dir: str) -> str:
    """根据审查模式预取 git diff，自动排除依赖文件。"""
    if not work_dir:
        return "(无法获取工作目录，跳过 diff 预取)"

    if mode == "full":
        # 全面审查：返回项目结构概览而非 diff
        try:
            r = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                capture_output=True, text=True, cwd=work_dir, timeout=10,
            )
            files = r.stdout.strip().split("\n") if r.stdout.strip() else []
            # 排除依赖文件
            exclude_suffixes = (".lock", "-lock.json", ".min.js", ".min.css", ".map", ".pyc")
            exclude_dirs = ("node_modules", "__pycache__", "dist", "build", ".next", "vendor", "target")
            filtered = []
            for f in files:
                if not f:
                    continue
                if any(f.endswith(s) for s in exclude_suffixes):
                    continue
                if any(d in f for d in exclude_dirs):
                    continue
                filtered.append(f)
            return "\n".join(filtered[:200]) or "(未找到源代码文件)"
        except Exception as exc:
            return f"(获取项目结构失败: {exc})"

    # 构建 git diff 命令
    if mode == "unstaged":
        cmd = ["git", "diff"]
    elif mode == "staged":
        cmd = ["git", "diff", "--cached"]
    elif mode == "branch":
        base = detect_base_branch(work_dir)
        cmd = ["git", "diff", f"origin/{base}...HEAD"]
    elif mode == "commit":
        cmd = ["git", "diff", "HEAD~1..HEAD"]
    else:
        cmd = ["git", "diff"]

    # 追加依赖排除 pathspec
    cmd.append("--")
    cmd.extend(DEPENDENCY_EXCLUDE_PATTERNS)

    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, cwd=work_dir, timeout=30,
        )
        diff = r.stdout.strip()
        if not diff:
            return "(未检测到代码变更)"
        # 截断超长 diff
        if len(diff) > 50000:
            diff = diff[:50000] + "\n\n...(diff 过长已截断，请聚焦已展示部分)..."
        return diff
    except subprocess.TimeoutExpired:
        return "(获取 diff 超时，请缩小审查范围)"
    except Exception as exc:
        return f"(获取 diff 失败: {exc})"


def build_code_review_context(mode: str, work_dir: Optional[str] = None) -> str:
    """构建代码审查的 system prompt 上下文。"""
    # 预取 diff
    diff_content = fetch_review_diff(mode, work_dir or "")

    # 获取对应模式的 user prompt 模板
    user_prompt_template = CODE_REVIEW_USER_PROMPTS.get(mode, CODE_REVIEW_USER_PROMPTS["branch"])
    user_prompt = user_prompt_template.replace("{diff_content}", diff_content)

    mode_info = CODE_REVIEW_MODES.get(mode, {})
    mode_label = mode_info.get("label", mode)

    return (
        "\n# 代码审查模式\n"
        f"用户消息以 `@code_review {mode}` 开头，本轮必须按以下代码审查规则执行。\n"
        f"当前审查模式：{mode_label}\n\n"
        f"{CODE_REVIEW_SYSTEM_PROMPT}\n\n"
        f"{user_prompt}\n"
    )