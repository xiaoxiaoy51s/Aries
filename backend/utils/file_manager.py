"""
File Manager - 基础文件管理工具
被 agent_tools.py 直接引用，作为核心后端功能
"""
from __future__ import annotations

import fnmatch
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FileManagerTool:
    """Unified file management tool with all file operations."""

    def __init__(self, user_email: str | None = None, work_dir: str | None = None) -> None:
        from utils.user_file_manager import UserFileManager
        self.manager = UserFileManager(work_dir=work_dir)
        self._work_dir = work_dir or ""

    @property
    def base_dir(self) -> Path:
        return self.manager.get_user_dir()

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return all tool definitions for file operations."""
        return [
            self._get_read_file_definition(),
            self._get_write_file_definition(),
            self._get_edit_file_definition(),
            self._get_list_files_definition(),
            self._get_search_file_definition(),
        ]

    def _get_read_file_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": (
                    "读取本地文本文件内容。"
                    "支持相对路径（默认在用户工作目录）或电脑任意位置的绝对路径。"
                    "支持模糊匹配文件名。"
                    "\n\n【读取方式】"
                    "- 完整读取：默认行为"
                    "- 区间读取：指定 start_line 和 end_line，只读取特定行（适合大文件）"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要读取的文件路径。支持相对路径或电脑任意位置的绝对路径。支持模糊匹配文件名。",
                        },
                        "encoding": {
                            "type": "string",
                            "description": "文本编码，默认 utf-8。",
                            "default": "utf-8",
                        },
                        "max_chars": {
                            "type": "integer",
                            "description": "最多返回的字符数上限，防止一次性载入过大文件。默认 20000。",
                            "default": 20000,
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "起始行号（从 1 开始）。与 end_line 配合使用，只读取特定行范围。",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "结束行号（包含）。与 start_line 配合使用，只读取特定行范围。",
                        },
                        "fuzzy_search": {
                            "type": "boolean",
                            "description": "是否启用模糊匹配。当文件路径不完全匹配时，搜索相似文件名。默认 true。",
                            "default": True,
                        },
                        "use_today": {
                            "type": "boolean",
                            "description": "是否在今天的日期目录中查找文件。默认 true（与 write_file 一致）。",
                            "default": True,
                        },
                    },
                    "required": ["file_path"],
                    "additionalProperties": False,
                },
            },
        }

    def _get_write_file_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": (
                    "将内容写入本地文件。"
                    "支持相对路径（默认保存到用户工作目录）或电脑任意位置的绝对路径。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "目标文件路径。支持相对路径或电脑任意位置的绝对路径。",
                        },
                        "content": {
                            "type": "string",
                            "description": "要写入的完整文本内容。",
                        },
                        "append": {
                            "type": "boolean",
                            "description": "是否以追加模式写入。默认 false（覆盖写入）。",
                            "default": False,
                        },
                        "create_dirs": {
                            "type": "boolean",
                            "description": "目标目录不存在时是否自动创建。默认 true。",
                            "default": True,
                        },
                        "encoding": {
                            "type": "string",
                            "description": "文本编码，默认 utf-8。",
                            "default": "utf-8",
                        },
                        "use_today": {
                            "type": "boolean",
                            "description": "是否使用今天的日期目录。默认 true。",
                            "default": True,
                        },
                    },
                    "required": ["file_path", "content"],
                    "additionalProperties": False,
                },
            },
        }

    def _get_edit_file_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "edit_file",
                "description": (
                    "编辑本地文件的特定部分。"
                    "适合修改代码文件、配置文件等文本文件。"
                    "支持按行号范围编辑或关键词替换，避免重复读取整个文件。"
                    "\n\n【使用场景】"
                    "- 修改代码的特定行（如修复 bug、调整逻辑）"
                    "- 替换特定文本（如修改变量名、更新配置）"
                    "- 插入/删除代码块"
                    "\n\n【编辑方式】"
                    "- line_range: 指定行号范围 [start, end]，替换这些行的内容"
                    "- search_replace: 搜索特定文本并替换"
                    "- insert_line: 在指定行号前插入内容"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "要编辑的文件路径。支持相对路径（默认相对于用户邮箱目录）或绝对路径。",
                        },
                        "edit_type": {
                            "type": "string",
                            "description": "编辑方式：line_range（按行号范围替换）, search_replace（搜索替换）, insert_line（插入行）。",
                            "enum": ["line_range", "search_replace", "insert_line"],
                        },
                        "new_content": {
                            "type": "string",
                            "description": "新的内容或替换内容。",
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "起始行号（从 1 开始）。用于 line_range 或 insert_line。",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "结束行号（包含）。仅用于 line_range。",
                        },
                        "search_text": {
                            "type": "string",
                            "description": "要搜索的文本。用于 search_replace。",
                        },
                        "use_regex": {
                            "type": "boolean",
                            "description": "是否将 search_text 作为正则表达式。默认 false。",
                            "default": False,
                        },
                        "occurrence": {
                            "type": "integer",
                            "description": "替换第几次出现（1=第一次，-1=最后一次）。默认 -1（替换所有）。",
                            "default": -1,
                        },
                        "encoding": {
                            "type": "string",
                            "description": "文本编码，默认 utf-8。",
                            "default": "utf-8",
                        },
                        "use_today": {
                            "type": "boolean",
                            "description": "是否在今天的日期目录中查找文件。默认 true（与 write_file 一致）。",
                            "default": True,
                        },
                    },
                    "required": ["file_path", "edit_type", "new_content"],
                    "additionalProperties": False,
                },
            },
        }

    def _get_list_files_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": (
                    "列出目录下的文件和子目录。"
                    "支持相对路径或电脑任意位置的绝对路径，可按文件名模式过滤。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subdir": {
                            "type": "string",
                            "description": "要列出的目录路径（可选）。支持相对路径或绝对路径，默认列出用户工作目录。",
                            "default": "",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "文件名匹配模式（如 *.md、*.py）。默认 *（所有文件）。注意拼写是 pattern，不是 pattenrn。",
                            "default": "*",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }

    def _get_search_file_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_file",
                "description": (
                    "在指定目录或整个代码库中搜索文件内容。"
                    "支持关键字搜索，返回匹配的文件路径、行号和内容。"
                    "适合查找函数定义、变量使用、特定代码模式等。"
                    "\n\n【搜索范围】"
                    "- 可以搜索单个文件"
                    "- 可以搜索整个目录（递归）"
                    "- 可以按文件类型过滤（如 *.py, *.js）"
                    "\n\n【返回结果】"
                    "- 匹配的文件路径"
                    "- 匹配的行号"
                    "- 匹配行及上下文内容"
                    "- 总匹配数统计"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "要搜索的关键字或正则表达式。",
                        },
                        "directory": {
                            "type": "string",
                            "description": "搜索的目录路径。默认为用户邮箱目录（搜索整个代码库）。支持相对路径或绝对路径。",
                            "default": "",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "文件匹配模式，如 *.py, *.js, **/*.ts 等。默认为 *（所有文件）。",
                            "default": "*",
                        },
                        "context_lines": {
                            "type": "integer",
                            "description": "返回匹配行前后各多少行作为上下文。默认 2。",
                            "default": 2,
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "最多返回多少处匹配。默认 50。",
                            "default": 50,
                        },
                        "use_regex": {
                            "type": "boolean",
                            "description": "是否将 keyword 作为正则表达式。默认 false。",
                            "default": False,
                        },
                        "case_sensitive": {
                            "type": "boolean",
                            "description": "是否区分大小写。默认 false。",
                            "default": False,
                        },
                        "exclude_dirs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "要排除的目录名列表，如 ['__pycache__', '.git', 'node_modules']。默认排除常见目录。",
                            "default": ["__pycache__", ".git", "node_modules", ".venv", "venv", "dist", "build"],
                        },
                    },
                    "required": ["keyword"],
                    "additionalProperties": False,
                },
            },
        }

    def execute_read_file(
        self,
        *,
        file_path: str,
        encoding: str = "utf-8",
        max_chars: int = 40000,
        start_line: int | None = None,
        end_line: int | None = None,
        fuzzy_search: bool = True,
        use_today: bool = True,
    ) -> dict[str, Any]:
        """Read file content with optional line range."""
        normalized_path = str(file_path or "").strip()
        if not normalized_path:
            return self._error_response("缺少 file_path 参数", "")
        try:
            target = self.manager.resolve_file_path(normalized_path, use_today=use_today)
        except ValueError as exc:
            return self._error_response(str(exc), normalized_path)
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
        use_today: bool = True,
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
        parent = target.parent
        if not parent.exists():
            if not create_dirs:
                return self._error_response(f"目录不存在: {parent}", normalized_path)
            parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        try:
            with open(target, mode, encoding=encoding) as f:
                f.write(text)
        except Exception as exc:
            return self._error_response(f"写入失败: {exc}", normalized_path)
        action = "追加到" if append else "写入"
        return {
            "success": True,
            "error": "",
            "output": f"成功{action}文件\n{target}",
            "file_path": str(target),
            "working_dir": str(self.base_dir),
        }

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
        use_today: bool = True,
    ) -> dict[str, Any]:
        """Edit specific parts of a file."""
        normalized_path = str(file_path or "").strip()
        if not normalized_path:
            return self._error_response("缺少 file_path 参数", "")
        try:
            target = self.manager.resolve_file_path(normalized_path, use_today=use_today)
        except ValueError as exc:
            return self._error_response(str(exc), normalized_path)
        if not target.exists():
            return self._error_response("文件不存在", normalized_path)
        try:
            with open(target, "r", encoding=encoding) as f:
                lines = f.readlines()
        except Exception as exc:
            return self._error_response(f"读取失败: {exc}", normalized_path)
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
        try:
            with open(target, "w", encoding=encoding) as f:
                f.write(new_content_str)
        except Exception as exc:
            return self._error_response(f"写入失败: {exc}", normalized_path)
        return {
            "success": True,
            "error": "",
            "output": f"成功编辑文件\n{target}\n修改类型: {edit_type}",
            "file_path": str(target),
            "working_dir": str(self.base_dir),
        }

    def execute_list_files(
        self,
        *,
        subdir: str = "",
        pattern: str = "*",
        **extra: Any,
    ) -> dict[str, Any]:
        """List files in directory."""
        if "pattenrn" in extra and pattern == "*":
            pattern = str(extra.pop("pattenrn") or "*")
        if "patern" in extra and pattern == "*":
            pattern = str(extra.pop("patern") or "*")
        extra.pop("pattenrn", None)
        extra.pop("patern", None)
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
    ) -> dict[str, Any]:
        """Search for content across files."""
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
        if not search_path.exists():
            return {
                "success": False,
                "error": f"目录不存在: {search_path}",
                "output": f"目录不存在: {search_path}",
                "matches": [],
                "total_matches": 0,
                "files_matched": 0,
            }
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

        for file_path in search_path.rglob("*"):
            if file_path.is_dir():
                continue
            if should_exclude(file_path):
                continue
            if not match_pattern(file_path):
                continue
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue
            file_matches = []
            for match in regex.finditer(content):
                if total_matches >= max_results:
                    break
                line_start = content.rfind("\n", 0, match.start()) + 1
                line_num = content[:line_start].count("\n") + 1
                lines = content.split("\n")
                context_start = max(0, line_num - context_lines - 1)
                context_end = min(len(lines), line_num + context_lines)
                context = []
                for i in range(context_start, context_end):
                    context.append({
                        "line_number": i + 1,
                        "content": lines[i],
                        "is_match": i == line_num - 1,
                    })
                file_matches.append({
                    "line_number": line_num,
                    "context": context,
                    "matched_text": match.group(),
                })
                total_matches += 1
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
