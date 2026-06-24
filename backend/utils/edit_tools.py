"""
多策略编辑工具（#4）。

借鉴 VS Code Copilot 的多编辑工具设计，提供三种精准编辑方式：
- replace_string: 精确字符串替换（含上下文行定位）
- multi_replace_string: 批量替换（一次调用多处修改，事务性）
- apply_patch: unified diff 格式补丁（大范围修改）

这些工具与现有 edit_file 互补，不替换它。
所有工具都委托给 UserFileManager 做路径解析和越界检查。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from utils.file_manager import FileManagerTool


class EditTools:
    """多策略编辑工具集合。

    复用 FileManagerTool 的路径解析和越界检查逻辑，
    但提供更精准的编辑方式。
    """

    def __init__(self, work_dir: str | None = None) -> None:
        self._fm = FileManagerTool(work_dir=work_dir)
        self._work_dir = work_dir or ""

    # ------------------------------------------------------------------
    # 执行逻辑
    # ------------------------------------------------------------------

    def execute_replace_string(
        self,
        *,
        file_path: str,
        old_text: str,
        new_text: str,
        encoding: str = "utf-8",
        skip_confirmation: bool = False,
    ) -> dict[str, Any]:
        """精确替换文件中的文本片段。"""
        normalized_path = str(file_path or "").strip()
        if not normalized_path:
            return self._error("缺少 file_path 参数", "")

        try:
            target = self._fm.manager.resolve_file_path(normalized_path)
        except ValueError as exc:
            return self._error(str(exc), normalized_path)

        oob = self._fm._check_out_of_bounds(target, skip_confirmation)
        if oob:
            return oob

        if not target.exists():
            return self._error("文件不存在", normalized_path)

        try:
            content = target.read_text(encoding=encoding, errors="replace")
        except Exception as exc:
            return self._error(f"读取失败: {exc}", normalized_path)

        # 检查 old_text 是否存在
        if old_text not in content:
            # 尝试规范化空白后匹配
            if _fuzzy_match(old_text, content):
                return self._error(
                    "old_text 与文件内容不完全匹配（空白/缩进差异）。"
                    "请先 read_file 确认文件实际内容，确保 old_text 完全一致。",
                    normalized_path,
                )
            return self._error(
                "old_text 在文件中未找到。可能文件已被修改，请重新 read_file 确认当前内容。",
                normalized_path,
            )

        # 检查唯一性
        count = content.count(old_text)
        if count > 1:
            return self._error(
                f"old_text 在文件中出现 {count} 次，无法唯一定位。"
                "请在 old_text 中增加前后上下文行使其唯一。",
                normalized_path,
            )

        # 执行替换
        new_content = content.replace(old_text, new_text, 1)
        try:
            target.write_text(new_content, encoding=encoding)
        except Exception as exc:
            return self._error(f"写入失败: {exc}", normalized_path)

        return {
            "success": True,
            "error": "",
            "output": f"成功替换文件内容\n{target}\n替换位置: 第 {_get_line_number(content, old_text)} 行附近",
            "file_path": str(target),
            "working_dir": str(self._fm.base_dir),
            "file_change": {
                "file_path": str(target),
                "operation": "modify",
                "previous_content": content,
                "new_content": new_content,
            },
        }

    def execute_multi_replace_string(
        self,
        *,
        file_path: str,
        replacements: list[dict[str, str]],
        encoding: str = "utf-8",
        skip_confirmation: bool = False,
    ) -> dict[str, Any]:
        """批量替换同一文件中的多处文本（事务性）。"""
        normalized_path = str(file_path or "").strip()
        if not normalized_path:
            return self._error("缺少 file_path 参数", "")

        if not replacements or not isinstance(replacements, list):
            return self._error("replacements 不能为空", normalized_path)

        try:
            target = self._fm.manager.resolve_file_path(normalized_path)
        except ValueError as exc:
            return self._error(str(exc), normalized_path)

        oob = self._fm._check_out_of_bounds(target, skip_confirmation)
        if oob:
            return oob

        if not target.exists():
            return self._error("文件不存在", normalized_path)

        try:
            content = target.read_text(encoding=encoding, errors="replace")
        except Exception as exc:
            return self._error(f"读取失败: {exc}", normalized_path)

        # 预检查所有 replacement
        applied: list[tuple[int, str, str]] = []  # (position, old_text, new_text)
        for idx, rep in enumerate(replacements):
            old_text = rep.get("old_text", "")
            new_text = rep.get("new_text", "")
            if not old_text:
                return self._error(f"第 {idx + 1} 条 replacement 的 old_text 为空", normalized_path)

            if old_text not in content:
                return self._error(
                    f"第 {idx + 1} 条 replacement 的 old_text 在文件中未找到。"
                    "请重新 read_file 确认文件内容。事务已回滚，未做任何修改。",
                    normalized_path,
                )

            count = content.count(old_text)
            if count > 1:
                return self._error(
                    f"第 {idx + 1} 条 replacement 的 old_text 出现 {count} 次，无法唯一定位。"
                    "请增加上下文行。事务已回滚，未做任何修改。",
                    normalized_path,
                )

            pos = content.index(old_text)
            applied.append((pos, old_text, new_text))

        # 检查重叠
        applied.sort(key=lambda x: x[0])
        for i in range(1, len(applied)):
            prev_end = applied[i - 1][0] + len(applied[i - 1][1])
            curr_start = applied[i][0]
            if curr_start < prev_end:
                return self._error(
                    f"第 {i} 条和第 {i + 1} 条 replacement 的 old_text 区域重叠。"
                    "事务已回滚，未做任何修改。",
                    normalized_path,
                )

        # 从后往前替换，避免位置偏移
        new_content = content
        for pos, old_text, new_text in reversed(applied):
            new_content = new_content[:pos] + new_text + new_content[pos + len(old_text):]

        try:
            target.write_text(new_content, encoding=encoding)
        except Exception as exc:
            return self._error(f"写入失败: {exc}", normalized_path)

        return {
            "success": True,
            "error": "",
            "output": f"成功批量替换文件内容\n{target}\n共完成 {len(applied)} 处替换",
            "file_path": str(target),
            "working_dir": str(self._fm.base_dir),
            "replacement_count": len(applied),
            "file_change": {
                "file_path": str(target),
                "operation": "modify",
                "previous_content": content,
                "new_content": new_content,
            },
        }

    def execute_apply_patch(
        self,
        *,
        file_path: str,
        patch: str,
        encoding: str = "utf-8",
        skip_confirmation: bool = False,
    ) -> dict[str, Any]:
        """应用 unified diff 格式的补丁。"""
        normalized_path = str(file_path or "").strip()
        if not normalized_path:
            return self._error("缺少 file_path 参数", "")

        if not patch or not patch.strip():
            return self._error("patch 内容为空", normalized_path)

        try:
            target = self._fm.manager.resolve_file_path(normalized_path)
        except ValueError as exc:
            return self._error(str(exc), normalized_path)

        oob = self._fm._check_out_of_bounds(target, skip_confirmation)
        if oob:
            return oob

        if not target.exists():
            return self._error("文件不存在", normalized_path)

        try:
            original = target.read_text(encoding=encoding, errors="replace")
        except Exception as exc:
            return self._error(f"读取失败: {exc}", normalized_path)

        # 解析 patch 并应用
        try:
            new_content = _apply_unified_diff(original, patch)
        except PatchError as exc:
            return self._error(f"补丁应用失败: {exc}", normalized_path)
        except Exception as exc:
            return self._error(f"补丁解析失败: {exc}", normalized_path)

        if new_content == original:
            return self._error("补丁未产生任何修改，请检查 patch 内容。", normalized_path)

        try:
            target.write_text(new_content, encoding=encoding)
        except Exception as exc:
            return self._error(f"写入失败: {exc}", normalized_path)

        return {
            "success": True,
            "error": "",
            "output": f"成功应用补丁\n{target}",
            "file_path": str(target),
            "working_dir": str(self._fm.base_dir),
            "file_change": {
                "file_path": str(target),
                "operation": "modify",
                "previous_content": original,
                "new_content": new_content,
            },
        }

    # ------------------------------------------------------------------
    # 工具调用入口
    # ------------------------------------------------------------------

    def execute(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """统一调用入口，供 skills_manager 分发。"""
        if tool_name == "replace_string":
            return self.execute_replace_string(**args)
        elif tool_name == "multi_replace_string":
            return self.execute_multi_replace_string(**args)
        elif tool_name == "apply_patch":
            return self.execute_apply_patch(**args)
        else:
            return self._error(f"未知工具: {tool_name}", "")

    def _error(self, msg: str, path: str) -> dict[str, Any]:
        return {
            "success": False,
            "error": msg,
            "output": msg,
            "file_path": path,
            "working_dir": str(self._fm.base_dir),
        }


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

class PatchError(Exception):
    """补丁应用错误。"""
    pass


def _fuzzy_match(old_text: str, content: str) -> bool:
    """模糊匹配：忽略首尾空白差异后是否匹配。"""
    normalized_old = old_text.strip()
    normalized_content = content.strip()
    return normalized_old in normalized_content


def _get_line_number(content: str, substring: str) -> int:
    """获取 substring 在 content 中首次出现的行号（从 1 开始）。"""
    idx = content.index(substring)
    return content[:idx].count("\n") + 1


def _apply_unified_diff(original: str, patch: str) -> str:
    """应用 unified diff 格式的补丁。

    支持标准 unified diff 格式：
        --- a/file
        +++ b/file
        @@ -start,count +start,count @@
         context line
        -removed line
        +added line
         context line
    """
    original_lines = original.splitlines(keepends=True)
    patch_lines = patch.splitlines()

    # 跳过 --- / +++ 头
    hunk_start = 0
    for i, line in enumerate(patch_lines):
        if line.startswith("@@"):
            hunk_start = i
            break
        elif line.startswith("---") or line.startswith("+++"):
            continue
        else:
            # 非 diff 头也非 hunk，跳过
            continue

    if hunk_start >= len(patch_lines):
        raise PatchError("补丁中没有找到 hunk（@@ ... @@）")

    result_lines: list[str] = []
    orig_idx = 0  # 原始文件的行索引

    i = hunk_start
    while i < len(patch_lines):
        line = patch_lines[i]

        if line.startswith("@@"):
            # 解析 hunk 头
            match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if not match:
                raise PatchError(f"无效的 hunk 头: {line}")

            old_start = int(match.group(1))
            # old_count = int(match.group(2) or 1)

            # 复制 hunk 之前的未修改行
            target_idx = old_start - 1  # 转为 0-based
            while orig_idx < target_idx and orig_idx < len(original_lines):
                result_lines.append(original_lines[orig_idx])
                orig_idx += 1

            i += 1
            continue

        if not line:
            i += 1
            continue

        prefix = line[0]
        content_part = line[1:]

        if prefix == " ":
            # 上下文行：必须匹配原始文件
            if orig_idx < len(original_lines):
                orig_line = original_lines[orig_idx].rstrip("\n\r")
                if orig_line != content_part:
                    # 宽松匹配：忽略首尾空白
                    if orig_line.strip() != content_part.strip():
                        raise PatchError(
                            f"上下文行不匹配（第 {orig_idx + 1} 行）: "
                            f"期望 {content_part!r}, 实际 {orig_line!r}"
                        )
                result_lines.append(original_lines[orig_idx])
                orig_idx += 1
            i += 1

        elif prefix == "-":
            # 删除行：必须匹配原始文件
            if orig_idx < len(original_lines):
                orig_line = original_lines[orig_idx].rstrip("\n\r")
                if orig_line != content_part and orig_line.strip() != content_part.strip():
                    raise PatchError(
                        f"删除行不匹配（第 {orig_idx + 1} 行）: "
                        f"期望 {content_part!r}, 实际 {orig_line!r}"
                    )
                orig_idx += 1
            i += 1

        elif prefix == "+":
            # 新增行
            result_lines.append(content_part + "\n")
            i += 1

        elif prefix == "\\":
            # \ No newline at end of file 等标记，跳过
            i += 1

        else:
            # 未知前缀，跳过
            i += 1

    # 复制剩余的原始行
    while orig_idx < len(original_lines):
        result_lines.append(original_lines[orig_idx])
        orig_idx += 1

    return "".join(result_lines)


__all__ = [
    "EditTools",
    "PatchError",
]
