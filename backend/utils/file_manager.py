"""
File Manager - 基础文件管理工具
被 agent_tools.py 直接引用，作为核心后端功能
支持使用 ripgrep 进行高性能文件搜索和内容搜索
"""
from __future__ import annotations

import fnmatch
import logging
import os
import re
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)

# 延迟导入 ripgrep 模块，避免在未安装 ripgrep 时崩溃
_ripgrep_available: bool | None = None


def _check_ripgrep_available() -> bool:
    """检查 ripgrep 是否可用"""
    global _ripgrep_available
    if _ripgrep_available is None:
        try:
            from utils.ripgrep import is_ripgrep_available
            _ripgrep_available = is_ripgrep_available()
        except Exception:
            _ripgrep_available = False
    return _ripgrep_available


class FileManagerTool:
    """Unified file management tool with all file operations.
    
    支持两种搜索模式：
    1. ripgrep 模式：高性能搜索，适合大型代码库
    2. Python 原生模式：兼容性好，适合未安装 ripgrep 的环境
    """

    def __init__(self, user_email: str | None = None, work_dir: str | None = None) -> None:
        from utils.user_file_manager import UserFileManager
        self.manager = UserFileManager(work_dir=work_dir)
        self._work_dir = work_dir or ""
        self._ripgrep_service = None
        self._ripgrep_checked = False

    @property
    def base_dir(self) -> Path:
        return self.manager.get_user_dir()

    def _get_ripgrep_service(self):
        """获取 ripgrep 服务（延迟初始化）"""
        if not self._ripgrep_checked:
            self._ripgrep_checked = True
            if _check_ripgrep_available():
                try:
                    from utils.ripgrep import get_ripgrep_service
                    self._ripgrep_service = get_ripgrep_service()
                    logger.info("已启用 ripgrep 高性能搜索模式")
                except Exception as e:
                    logger.warning(f"初始化 ripgrep 失败，将使用 Python 原生搜索: {e}")
        return self._ripgrep_service

    def execute_read_file(
        self,
        *,
        file_path: str,
        encoding: str = "utf-8",
        max_chars: int = 40000,
        start_line: int | None = None,
        end_line: int | None = None,
        fuzzy_search: bool = True,
        use_today: bool = False,
        skip_confirmation: bool = False,
    ) -> dict[str, Any]:
        """Read file content with optional line range."""
        normalized_path = str(file_path or "").strip()
        if not normalized_path:
            return self._error_response("缺少 file_path 参数", "")
        try:
            target = self.manager.resolve_file_path(normalized_path, use_today=use_today)
        except ValueError as exc:
            return self._error_response(str(exc), normalized_path)
        oob = self._check_out_of_bounds(target, skip_confirmation)
        if oob:
            return oob
        if not target.exists():
            if fuzzy_search:
                similar = self._find_similar_files(normalized_path)
                if similar:
                    return self._error_response(
                        f"文件不存在。您是否想查找: {similar}?",
                        normalized_path
                    )
            return self._error_response("文件不存在", normalized_path)
        if target.is_dir():
            return self._error_response("路径是目录，不是文件", normalized_path)
        try:
            with open(target, "rb") as f:
                chunk = f.read(8192)
                if b"\x00" in chunk:
                    return self._error_response("无法读取二进制文件", normalized_path)
        except Exception as exc:
            return self._error_response(f"读取失败: {exc}", normalized_path)
        try:
            with open(target, "r", encoding=encoding, errors="replace") as f:
                lines = f.readlines()
        except Exception as exc:
            return self._error_response(f"读取失败: {exc}", normalized_path)
        total_lines = len(lines)
        if start_line is not None or end_line is not None:
            start = (start_line or 1) - 1
            end = (end_line or total_lines)
            start = max(0, start)
            end = min(total_lines, end)
            lines = lines[start:end]
            line_offset = start
        else:
            line_offset = 0
        content = "".join(lines)
        truncated = len(content) > max_chars
        if truncated:
            content = content[:max_chars]
        output_lines = [f"文件: {target.name}", f"路径: {target}", f"行数: {total_lines}", ""]
        if truncated:
            output_lines.append(f"内容已截断（超过 {max_chars} 字符限制）")
            output_lines.append("")
        for i, line in enumerate(lines[:1000], start=line_offset + 1):
            output_lines.append(f"{i:4d}| {line.rstrip()}")
        if len(lines) > 1000:
            output_lines.append(f"\n... 还有 {len(lines) - 1000} 行 ...")
        return {
            "success": True,
            "error": "",
            "output": "\n".join(output_lines),
            "content": content,
            "file_path": str(target),
            "working_dir": str(self.base_dir),
            "truncated": truncated,
        }

    def execute_write_file(
        self,
        *,
        file_path: str,
        content: str,
        append: bool = False,
        create_dirs: bool = True,
        encoding: str = "utf-8",
        use_today: bool = False,
        skip_confirmation: bool = False,
    ) -> dict[str, Any]:
        """Write content to file."""
        normalized_path = str(file_path or "").strip()
        if not normalized_path:
            return self._error_response("缺少 file_path 参数", "")
        text = str(content or "")
        try:
            target = self.manager.resolve_file_path(normalized_path, use_today=use_today)
        except ValueError as exc:
            return self._error_response(str(exc), normalized_path)
        oob = self._check_out_of_bounds(target, skip_confirmation)
        if oob:
            return oob
        parent = target.parent
        if not parent.exists():
            if not create_dirs:
                return self._error_response(f"目录不存在: {parent}", normalized_path)
            parent.mkdir(parents=True, exist_ok=True)

        # 记录变更前的内容（用于产物区域 diff 和回退）
        file_change = None
        if not append:
            previous_content = ""
            operation = "create"
            if target.exists():
                try:
                    previous_content = target.read_text(encoding=encoding)
                    operation = "modify"
                except Exception:
                    previous_content = ""
            file_change = {
                "file_path": str(target),
                "operation": operation,
                "previous_content": previous_content,
                "new_content": text,
            }

        mode = "a" if append else "w"
        try:
            with open(target, mode, encoding=encoding) as f:
                f.write(text)
        except Exception as exc:
            return self._error_response(f"写入失败: {exc}", normalized_path)
        action = "追加到" if append else "写入"
        result = {
            "success": True,
            "error": "",
            "output": f"成功{action}文件\n{target}",
            "file_path": str(target),
            "working_dir": str(self.base_dir),
        }
        if file_change:
            result["file_change"] = file_change
        return result

    def execute_edit_file(
        self,
        *,
        file_path: str,
        edit_type: str,
        new_content: str,
        start_line: int | None = None,
        end_line: int | None = None,
        search_text: str | None = None,
        use_regex: bool = False,
        occurrence: int = -1,
        encoding: str = "utf-8",
        use_today: bool = False,
        skip_confirmation: bool = False,
    ) -> dict[str, Any]:
        """Edit specific parts of a file."""
        normalized_path = str(file_path or "").strip()
        if not normalized_path:
            return self._error_response("缺少 file_path 参数", "")
        try:
            target = self.manager.resolve_file_path(normalized_path, use_today=use_today)
        except ValueError as exc:
            return self._error_response(str(exc), normalized_path)
        oob = self._check_out_of_bounds(target, skip_confirmation)
        if oob:
            return oob
        if not target.exists():
            return self._error_response("文件不存在", normalized_path)
        try:
            with open(target, "r", encoding=encoding) as f:
                lines = f.readlines()
        except Exception as exc:
            return self._error_response(f"读取失败: {exc}", normalized_path)
        _original_content = "".join(lines)
        if edit_type == "line_range":
            if start_line is None or end_line is None:
                return self._error_response("line_range 需要 start_line 和 end_line 参数", normalized_path)
            start = max(0, start_line - 1)
            end = min(len(lines), end_line)
            new_lines = new_content.split("\n")
            if new_lines and not new_lines[-1]:
                new_lines = new_lines[:-1]
            new_lines = [line + "\n" for line in new_lines]
            lines = lines[:start] + new_lines + lines[end:]
        elif edit_type == "search_replace":
            if search_text is None:
                return self._error_response("search_replace 需要 search_text 参数", normalized_path)
            content = "".join(lines)
            if use_regex:
                if occurrence == -1:
                    new_text = re.sub(search_text, new_content, content)
                else:
                    matches = list(re.finditer(search_text, content))
                    if occurrence <= len(matches):
                        match = matches[occurrence - 1]
                        new_text = content[:match.start()] + new_content + content[match.end():]
                    else:
                        new_text = content
            else:
                if occurrence == -1:
                    new_text = content.replace(search_text, new_content)
                elif occurrence == 1:
                    new_text = content.replace(search_text, new_content, 1)
                else:
                    parts = content.split(search_text)
                    if occurrence <= len(parts) - 1:
                        new_text = search_text.join(parts[:occurrence]) + new_content + search_text.join(parts[occurrence:])
                    else:
                        new_text = content
            lines = new_text.split("\n")
            if lines and not lines[-1]:
                lines = lines[:-1]
            lines = [line + "\n" for line in lines]
        elif edit_type == "insert_line":
            if start_line is None:
                return self._error_response("insert_line 需要 start_line 参数", normalized_path)
            insert_pos = start_line - 1
            insert_pos = max(0, min(insert_pos, len(lines)))
            new_lines = new_content.split("\n")
            if new_lines and not new_lines[-1]:
                new_lines = new_lines[:-1]
            new_lines = [line + "\n" for line in new_lines]
            lines = lines[:insert_pos] + new_lines + lines[insert_pos:]
        else:
            return self._error_response(f"未知的 edit_type: {edit_type}", normalized_path)
        new_content_str = "".join(lines)
        # 记录变更前的内容（用于产物区域 diff 和回退）
        try:
            with open(target, "w", encoding=encoding) as f:
                f.write(new_content_str)
        except Exception as exc:
            return self._error_response(f"写入失败: {exc}", normalized_path)
        result = {
            "success": True,
            "error": "",
            "output": f"成功编辑文件\n{target}\n修改类型: {edit_type}",
            "file_path": str(target),
            "working_dir": str(self.base_dir),
        }
        result["file_change"] = {
            "file_path": str(target),
            "operation": "modify",
            "previous_content": _original_content,
            "new_content": new_content_str,
        }
        return result

    def execute_list_files(
        self,
        *,
        subdir: str = "",
        pattern: str = "*",
        skip_confirmation: bool = False,
        **extra: Any,
    ) -> dict[str, Any]:
        """List files in directory.
        
        优先使用 ripgrep 进行高性能文件搜索，如果 ripgrep 不可用则回退到 Python 原生实现。
        """
        # 检查列出的目录是否超出工作目录
        target_dir = self.manager.resolve_list_dir(subdir if subdir else None)
        oob = self._check_out_of_bounds(target_dir, skip_confirmation)
        if oob:
            return oob
        if "pattenrn" in extra and pattern == "*":
            pattern = str(extra.pop("pattenrn") or "*")
        if "patern" in extra and pattern == "*":
            pattern = str(extra.pop("patern") or "*")
        extra.pop("pattenrn", None)
        extra.pop("patern", None)
        
        # 尝试使用 ripgrep 进行高性能搜索
        ripgrep_service = self._get_ripgrep_service()
        if ripgrep_service and pattern != "*":
            try:
                files = ripgrep_service.glob(
                    pattern=pattern,
                    cwd=str(target_dir),
                    limit=1000,
                    exclude_patterns=["__pycache__", ".git", "node_modules", ".venv", "venv", "dist", "build"],
                )
                if files:
                    return self._format_list_files_result(files, pattern)
            except Exception as e:
                logger.warning(f"ripgrep glob 失败，回退到 Python 原生搜索: {e}")
        
        # 回退到 Python 原生实现
        try:
            files = self.manager.list_files(
                subdir=subdir if subdir else None,
                pattern=pattern or "*",
            )
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "output": f"列出文件失败\n异常: {exc}",
                "files": [],
                "count": 0,
            }
        if not files:
            return {
                "success": True,
                "error": "",
                "output": "没有找到任何文件",
                "files": [],
                "count": 0,
            }
        file_list = []
        dir_list = []
        for file_info in files:
            display_path = file_info.get("path") or file_info.get("name", "")
            if file_info.get("is_dir"):
                dir_list.append(f"{display_path}/")
            else:
                size = file_info.get("size", 0)
                size_str = self._format_size(size)
                file_list.append(f"{display_path} ({size_str})")
        output_lines = [f"找到 {len(files)} 个项目"]
        if dir_list:
            output_lines.append(f"\n目录 ({len(dir_list)} 个):")
            output_lines.extend(dir_list[:20])
            if len(dir_list) > 20:
                output_lines.append(f"  ... 还有 {len(dir_list) - 20} 个目录")
        if file_list:
            output_lines.append(f"\n文件 ({len(file_list)} 个):")
            output_lines.extend(file_list[:20])
            if len(file_list) > 20:
                output_lines.append(f"  ... 还有 {len(file_list) - 20} 个文件")
        return {
            "success": True,
            "error": "",
            "output": "\n".join(output_lines),
            "files": files,
            "count": len(files),
        }

    def _format_list_files_result(self, files: list[dict[str, Any]], pattern: str) -> dict[str, Any]:
        """格式化 ripgrep 搜索结果"""
        file_list = []
        for file_info in files:
            display_path = file_info.get("relative_path") or file_info.get("path") or file_info.get("name", "")
            size = file_info.get("size", 0)
            size_str = self._format_size(size)
            file_list.append(f"{display_path} ({size_str})")
        
        output_lines = [
            f"找到 {len(files)} 个文件 (使用 ripgrep 高性能搜索)",
            f"搜索模式: {pattern}",
            "",
            "文件列表:",
        ]
        output_lines.extend(file_list[:50])
        if len(file_list) > 50:
            output_lines.append(f"  ... 还有 {len(file_list) - 50} 个文件")
        
        return {
            "success": True,
            "error": "",
            "output": "\n".join(output_lines),
            "files": files,
            "count": len(files),
            "search_mode": "ripgrep",
        }

    def execute_search_file(
        self,
        *,
        keyword: str,
        directory: str = "",
        pattern: str = "*",
        context_lines: int = 2,
        max_results: int = 50,
        use_regex: bool = False,
        case_sensitive: bool = False,
        exclude_dirs: list[str] | None = None,
        skip_confirmation: bool = False,
    ) -> dict[str, Any]:
        """Search for content across files.
        
        优先使用 ripgrep 进行高性能内容搜索，如果 ripgrep 不可用则回退到 Python 原生实现。
        """
        if not keyword:
            return {
                "success": False,
                "error": "缺少 keyword 参数",
                "output": "缺少 keyword 参数",
                "matches": [],
                "total_matches": 0,
                "files_matched": 0,
            }
        exclude_dirs = exclude_dirs or ["__pycache__", ".git", "node_modules", ".venv", "venv", "dist", "build"]
        try:
            if directory:
                search_path = self.manager.resolve_file_path(directory, use_today=False)
            else:
                search_path = self.base_dir
        except ValueError as exc:
            return {
                "success": False,
                "error": str(exc),
                "output": f"路径错误: {exc}",
                "matches": [],
                "total_matches": 0,
                "files_matched": 0,
            }
        oob = self._check_out_of_bounds(search_path, skip_confirmation)
        if oob:
            return oob
        if not search_path.exists():
            return {
                "success": False,
                "error": f"目录不存在: {search_path}",
                "output": f"目录不存在: {search_path}",
                "matches": [],
                "total_matches": 0,
                "files_matched": 0,
            }
        
        # 尝试使用 ripgrep 进行高性能搜索
        ripgrep_service = self._get_ripgrep_service()
        if ripgrep_service:
            try:
                ripgrep_matches = ripgrep_service.grep(
                    pattern=keyword,
                    cwd=str(search_path),
                    include=pattern if pattern != "*" else None,
                    limit=max_results,
                    context_lines=context_lines,
                    case_sensitive=case_sensitive,
                    use_regex=use_regex,
                    exclude_dirs=exclude_dirs,
                )
                if ripgrep_matches:
                    return self._format_search_result(
                        ripgrep_matches, keyword, search_path, pattern, context_lines
                    )
            except Exception as e:
                logger.warning(f"ripgrep grep 失败，回退到 Python 原生搜索: {e}")
        
        # 回退到 Python 原生实现
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            if use_regex:
                regex = re.compile(keyword, flags)
            else:
                regex = re.compile(re.escape(keyword), flags)
        except re.error as exc:
            return {
                "success": False,
                "error": f"无效的正则表达式: {exc}",
                "output": f"无效的正则表达式: {exc}",
                "matches": [],
                "total_matches": 0,
                "files_matched": 0,
            }
        matches = []
        total_matches = 0
        files_matched = 0

        def should_exclude(path: Path) -> bool:
            for part in path.parts:
                if part in exclude_dirs:
                    return True
            return False

        def match_pattern(path: Path) -> bool:
            if pattern == "*":
                return True
            return fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(str(path), pattern)

        # 优化：使用 os.scandir 递归遍历（比 rglob 快），逐行读取文件（避免大文件内存爆炸）
        exclude_set = set(exclude_dirs)
        max_file_size = 10 * 1024 * 1024  # 跳过大于 10MB 的文件

        def scan_dir(directory: Path) -> Generator[Path, None, None]:
            """使用 os.scandir 递归扫描目录，性能优于 rglob"""
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if entry.name in exclude_set:
                            continue
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                yield from scan_dir(Path(entry.path))
                            elif entry.is_file(follow_symlinks=False):
                                p = Path(entry.path)
                                if pattern == "*" or fnmatch.fnmatch(p.name, pattern):
                                    yield p
                        except OSError:
                            continue
            except OSError:
                return

        for file_path in scan_dir(search_path):
            # 跳过过大文件
            try:
                if file_path.stat().st_size > max_file_size:
                    continue
            except OSError:
                continue

            file_matches = []
            file_lines: list[str] = []  # 缓存行内容用于上下文

            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for line_num, line in enumerate(f, 1):
                        file_lines.append(line.rstrip("\n\r"))
                        if len(file_lines) > context_lines + 2:
                            # 只保留需要的行数，避免内存浪费
                            if context_lines > 0:
                                file_lines = file_lines[-(context_lines + 2):]

                        for match in regex.finditer(line):
                            if total_matches >= max_results:
                                break
                            # 构建上下文（需要重新读取部分行）
                            matched_text = match.group()
                            file_matches.append({
                                "line_number": line_num,
                                "context": [{"line_number": line_num, "content": line.rstrip("\n\r"), "is_match": True}],
                                "matched_text": matched_text,
                            })
                            total_matches += 1
                            break  # 每行只记录第一个匹配，避免过多结果

                        if total_matches >= max_results:
                            break
            except Exception:
                continue

            if file_matches:
                files_matched += 1
                matches.append({
                    "file": str(file_path),
                    "relative_path": str(file_path.relative_to(search_path)),
                    "matches": file_matches,
                    "match_count": len(file_matches),
                })
            if total_matches >= max_results:
                break

        output_lines = [
            f"搜索完成",
            f"关键字: {keyword}",
            f"搜索目录: {search_path}",
            f"文件模式: {pattern}",
            f"找到 {files_matched} 个文件，共 {total_matches} 处匹配",
        ]
        for match_info in matches[:10]:
            output_lines.append(f"\n文件: {match_info['relative_path']} ({match_info['match_count']} 处匹配)")
            output_lines.append("-" * 60)
            for m in match_info["matches"][:3]:
                for ctx in m["context"]:
                    prefix = "> " if ctx["is_match"] else "  "
                    output_lines.append(f"{prefix}{ctx['line_number']:4d}| {ctx['content']}")
                output_lines.append("")
        if len(matches) > 10:
            output_lines.append(f"\n... 还有 {len(matches) - 10} 个文件 ...")
        return {
            "success": True,
            "error": "",
            "output": "\n".join(output_lines),
            "matches": matches,
            "total_matches": total_matches,
            "files_matched": files_matched,
        }

    def _format_search_result(
        self,
        matches: list[dict[str, Any]],
        keyword: str,
        search_path: Path,
        pattern: str,
        context_lines: int,
    ) -> dict[str, Any]:
        """格式化 ripgrep 搜索结果"""
        # 按文件分组
        files_dict: dict[str, list[dict[str, Any]]] = {}
        for match in matches:
            file_path = match.get("file", "")
            if file_path not in files_dict:
                files_dict[file_path] = []
            files_dict[file_path].append(match)
        
        # 格式化输出
        formatted_matches = []
        for file_path, file_matches in files_dict.items():
            rel_path = file_matches[0].get("relative_path", file_path)
            formatted_matches.append({
                "file": file_path,
                "relative_path": rel_path,
                "matches": file_matches,
                "match_count": len(file_matches),
            })
        
        # 生成输出文本
        output_lines = [
            f"搜索完成 (使用 ripgrep 高性能搜索)",
            f"关键字: {keyword}",
            f"搜索目录: {search_path}",
            f"文件模式: {pattern}",
            f"找到 {len(formatted_matches)} 个文件，共 {len(matches)} 处匹配",
        ]
        
        for match_info in formatted_matches[:10]:
            output_lines.append(f"\n文件: {match_info['relative_path']} ({match_info['match_count']} 处匹配)")
            output_lines.append("-" * 60)
            for m in match_info["matches"][:3]:
                line_number = m.get("line_number", 0)
                matched_text = m.get("matched_text", "")
                context = m.get("context", [])
                
                # 显示上下文
                for ctx in context:
                    ctx_line = ctx.get("line_number", 0)
                    ctx_content = ctx.get("content", "")
                    is_match = ctx.get("is_match", False)
                    prefix = "> " if is_match else "  "
                    output_lines.append(f"{prefix}{ctx_line:4d}| {ctx_content}")
                output_lines.append("")
        
        if len(formatted_matches) > 10:
            output_lines.append(f"\n... 还有 {len(formatted_matches) - 10} 个文件 ...")
        
        return {
            "success": True,
            "error": "",
            "output": "\n".join(output_lines),
            "matches": formatted_matches,
            "total_matches": len(matches),
            "files_matched": len(formatted_matches),
            "search_mode": "ripgrep",
        }

    def _check_out_of_bounds(self, target_path: Path, skip_confirmation: bool = False) -> dict[str, Any] | None:
        """检查路径是否超出工作目录；超出时返回危险确认响应，未超出返回 None。"""
        if skip_confirmation or not self.manager.is_outside_work_dir(target_path):
            return None

        # 检查黑白名单权限
        from db.path_permissions import check_path_permission
        perm_result = check_path_permission(str(target_path))
        if perm_result:
            if perm_result.get("allowed"):
                # 白名单命中，直接放行
                return None
            else:
                # 黑名单命中，直接拒绝
                return {
                    "success": False,
                    "error": "Path blocked",
                    "output": (
                        f"路径已被禁止访问\n"
                        f"目标路径: {target_path}\n"
                        f"原因: {perm_result.get('reason', '黑名单限制')}\n"
                        f"用户已将该路径加入黑名单，禁止 AI 访问。"
                    ),
                    "file_path": str(target_path),
                    "working_dir": str(self.base_dir),
                    "requires_confirmation": False,
                    "danger_types": ["路径在黑名单中"],
                    "danger_info": perm_result.get("reason", "黑名单限制"),
                }

        # approval_mode 兜底：'full' 全部跳过；'review' 仅高风险才弹确认
        from utils.app_setting import should_skip_confirmation
        if should_skip_confirmation(["文件操作超出工作目录"]):
            return None

        return {
            "success": False,
            "error": "Confirmation required",
            "output": (
                f"文件操作超出工作目录范围，需要确认\n"
                f"目标路径: {target_path}\n"
                f"工作目录: {self.base_dir}\n"
                f"原因: 文件操作超出当前工作目录\n请由用户手动确认后再继续执行。"
            ),
            "file_path": str(target_path),
            "working_dir": str(self.base_dir),
            "requires_confirmation": True,
            "danger_types": ["文件操作超出工作目录"],
            "danger_info": "文件操作超出工作目录",
        }

    def _error_response(self, error: str, file_path: str) -> dict[str, Any]:
        return {
            "success": False,
            "error": error,
            "output": error,
            "file_path": file_path,
            "working_dir": str(self.base_dir),
        }

    def _format_size(self, size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def _find_similar_files(self, file_path: str) -> str | None:
        import difflib
        try:
            target = Path(file_path).name
            all_files = list(self.base_dir.rglob("*"))
            file_names = [f.name for f in all_files if f.is_file()]
            matches = difflib.get_close_matches(target, file_names, n=1, cutoff=0.6)
            if matches:
                return matches[0]
        except Exception:
            pass
        return None
