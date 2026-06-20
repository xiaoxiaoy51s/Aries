"""
文件搜索工具模块
优先使用项目内置的 ripgrep，保证稳定可用；找不到则回退到 Python 原生实现
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 项目内置 ripgrep 路径
_VENDOR_BIN = Path(__file__).parent.parent / "bin"
_VENDOR_RG = _VENDOR_BIN / ("rg.exe" if sys.platform == "win32" else "rg")


class RipgrepService:
    """搜索服务 - 优先使用内置 ripgrep，回退到 Python 原生实现"""

    def __init__(self):
        self._binary_path: Optional[str] = None
        self._checked = False

    def _find_binary(self) -> Optional[str]:
        """查找 ripgrep 二进制文件"""
        # 1. 优先使用项目内置的 ripgrep（最稳定）
        if _VENDOR_RG.exists():
            return str(_VENDOR_RG)

        # 2. Linux/macOS 上查找系统 PATH 中的 rg（Windows 已内置）
        if sys.platform != "win32":
            system_path = shutil.which("rg")
            if system_path:
                return system_path

        return None

    def _get_binary(self) -> Optional[str]:
        if not self._checked:
            self._binary_path = self._find_binary()
            self._checked = True
            if self._binary_path:
                logger.debug(f"使用 ripgrep: {self._binary_path}")
        return self._binary_path

    def is_available(self) -> bool:
        return self._get_binary() is not None

    def _run_command(
        self,
        args: list[str],
        cwd: str,
        timeout: float = 30.0,
    ) -> Optional[subprocess.CompletedProcess[str]]:
        """运行 ripgrep 命令，失败返回 None"""
        binary = self._get_binary()
        if not binary:
            return None

        try:
            result = subprocess.run(
                [binary] + args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            return result
        except subprocess.TimeoutExpired:
            logger.warning(f"ripgrep 命令超时 ({timeout}s)")
            return None
        except Exception as e:
            logger.warning(f"ripgrep 执行失败: {e}")
            return None

    def glob(
        self,
        pattern: str,
        cwd: str,
        limit: int = 1000,
        exclude_patterns: Optional[list[str]] = None,
    ) -> Optional[list[dict[str, Any]]]:
        """文件搜索，返回 None 表示不可用"""
        args = ["--files", "--glob", pattern, "--no-ignore"]

        if exclude_patterns:
            for exclude in exclude_patterns:
                args.extend(["--glob", f"!{exclude}"])

        args.extend(["--glob", "!**/.git/**", "."])

        result = self._run_command(args, cwd)
        if result is None or result.returncode not in (0, 1):
            return None

        files = []
        for line in result.stdout.strip().split("\n"):
            if line and len(files) < limit:
                normalized = line.replace("\\", "/").lstrip("./")
                if normalized:
                    file_path = Path(cwd) / normalized
                    try:
                        size = file_path.stat().st_size if file_path.exists() else 0
                    except OSError:
                        size = 0
                    files.append({
                        "path": str(file_path),
                        "relative_path": normalized,
                        "name": file_path.name,
                        "is_dir": False,
                        "size": size,
                    })
        return files

    def grep(
        self,
        pattern: str,
        cwd: str,
        include: Optional[str] = None,
        limit: int = 100,
        context_lines: int = 2,
        case_sensitive: bool = True,
        use_regex: bool = True,
        exclude_dirs: Optional[list[str]] = None,
    ) -> Optional[list[dict[str, Any]]]:
        """内容搜索，返回 None 表示不可用"""
        args = ["--json", "--no-messages", "--no-ignore"]

        if not case_sensitive:
            args.append("--ignore-case")

        if context_lines > 0:
            args.extend(["--context", str(context_lines)])

        if include:
            args.extend(["--glob", include])

        if exclude_dirs:
            for exclude_dir in exclude_dirs:
                args.extend(["--glob", f"!**/{exclude_dir}/**"])

        args.extend(["--glob", "!**/.git/**"])

        if use_regex:
            args.extend(["--", pattern])
        else:
            args.extend(["--fixed-strings", "--", pattern])

        args.append(".")

        result = self._run_command(args, cwd, timeout=60.0)
        if result is None or result.returncode not in (0, 1):
            return None

        matches = []
        context_buffer: list[dict[str, Any]] = []

        for line in result.stdout.strip().split("\n"):
            if not line or len(matches) >= limit:
                continue

            try:
                data = json.loads(line)
                msg_type = data.get("type")

                if msg_type == "match":
                    match_data = data.get("data", {})
                    path_data = match_data.get("path", {})
                    lines_data = match_data.get("lines", {})

                    file_path = path_data.get("text", "")
                    line_number = match_data.get("line_number", 0)
                    matched_text = lines_data.get("text", "")

                    if file_path and line_number > 0:
                        abs_path = Path(cwd) / file_path
                        rel_path = file_path.replace("\\", "/").lstrip("./")

                        context = list(context_buffer)
                        context.append({
                            "line_number": line_number,
                            "content": matched_text.rstrip(),
                            "is_match": True,
                        })
                        context_buffer.clear()

                        matches.append({
                            "file": str(abs_path),
                            "relative_path": rel_path,
                            "line_number": line_number,
                            "matched_text": matched_text.rstrip(),
                            "context": context,
                        })
                elif msg_type == "context":
                    match_data = data.get("data", {})
                    lines_data = match_data.get("lines", {})

                    ctx_line = match_data.get("line_number", 0)
                    ctx_text = lines_data.get("text", "").rstrip()

                    if len(context_buffer) < context_lines:
                        context_buffer.append({
                            "line_number": ctx_line,
                            "content": ctx_text,
                            "is_match": False,
                        })
                else:
                    context_buffer.clear()

            except json.JSONDecodeError:
                continue

        return matches[:limit]


# 全局单例
_service: Optional[RipgrepService] = None


def get_ripgrep_service() -> RipgrepService:
    global _service
    if _service is None:
        _service = RipgrepService()
    return _service


def is_ripgrep_available() -> bool:
    return get_ripgrep_service().is_available()
