"""
多策略编辑工具（#4）与编辑冲突解决（Rebase）（#5）。

借鉴 VS Code Copilot 的多编辑工具设计，提供两种精准编辑方式：
- multi_replace_string: 批量替换（一次调用多处修改，事务性）
- apply_patch: unified diff 格式补丁（大范围修改）

单处精确替换请使用 edit_file 的 search_replace 模式。
所有工具都委托给 UserFileManager 做路径解析和越界检查。

编辑冲突解决（Rebase）：
当 AI 生成的编辑建议与用户手动编辑冲突时，自动调整建议以适应用户的实际修改。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from engine.file_manager import FileManagerTool


# =========================================================================
# Part 1: Edit Rebase（冲突解决）
# =========================================================================

class RebaseResult(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    CONFLICT = "conflict"
    NOT_FOUND = "not_found"


@dataclass
class RebasedEdit:
    """Rebase 后的编辑结果。"""
    result: RebaseResult
    old_text: str = ""
    new_text: str = ""
    message: str = ""
    conflict_detail: str = ""

    @property
    def success(self) -> bool:
        return self.result in (RebaseResult.SUCCESS, RebaseResult.PARTIAL)


# auto-close pairs：编辑器自动补全的字符对
_AUTO_CLOSE_PAIRS = {
    "()", "[]", "{}", "<>", '""', "''", "``",
}


def try_rebase_edit(
    original_content: str,
    old_text: str,
    new_text: str,
    current_content: str,
) -> RebasedEdit:
    """尝试将 (old_text → new_text) 的编辑 rebase 到当前文件内容上。

    Args:
        original_content: AI 生成编辑时的文件原始内容
        old_text: AI 要替换的原始文本
        new_text: AI 替换后的文本
        current_content: 文件当前的实际内容（可能被用户修改过）

    Returns:
        RebasedEdit: rebase 结果
    """
    # 情况 1：精确匹配
    if old_text in current_content:
        count = current_content.count(old_text)
        if count == 1:
            return RebasedEdit(
                result=RebaseResult.SUCCESS,
                old_text=old_text, new_text=new_text,
                message="精确匹配成功",
            )
        else:
            return RebasedEdit(
                result=RebaseResult.CONFLICT,
                message=f"old_text 在当前文件中出现 {count} 次，无法唯一定位",
                conflict_detail="文件可能已被修改，请重新 read_file 确认",
            )

    # 情况 2：文件被修改了，尝试 rebase
    user_edits = _diff_texts(original_content, current_content)
    if not user_edits:
        return RebasedEdit(
            result=RebaseResult.NOT_FOUND,
            message="old_text 在文件中未找到，且文件未被修改。请重新 read_file 确认文件内容。",
        )

    for edit in user_edits:
        if _ranges_overlap(edit["start"], edit["end"], _find_range(original_content, old_text)):
            adjusted = _adjust_for_user_edit(original_content, old_text, new_text, current_content, edit)
            if adjusted:
                return adjusted

    # 策略 3：规范化空白后匹配
    if _normalize_whitespace(old_text) in _normalize_whitespace(current_content):
        return RebasedEdit(
            result=RebaseResult.PARTIAL,
            old_text=old_text, new_text=new_text,
            message="空白规范化后匹配。建议重新 read_file 获取准确内容后再编辑。",
        )

    # 策略 4：前缀匹配
    prefix_len = _longest_common_prefix(old_text, current_content)
    if prefix_len > len(old_text) * 0.5:
        return RebasedEdit(
            result=RebaseResult.PARTIAL,
            old_text=old_text, new_text=new_text,
            message=f"前缀匹配（{prefix_len}/{len(old_text)} 字符）。文件可能已被修改，建议重新 read_file。",
        )

    # 策略 5：auto-close pair 吸收
    for pair in _AUTO_CLOSE_PAIRS:
        if pair[0] in old_text and pair[1] in old_text:
            stripped = current_content.replace(original_content, "", 1).strip()
            if stripped == pair or stripped in pair:
                return RebasedEdit(
                    result=RebaseResult.SUCCESS,
                    old_text=old_text, new_text=new_text,
                    message=f"检测到用户输入了 auto-close pair {pair}，已吸收",
                )

    return RebasedEdit(
        result=RebaseResult.CONFLICT,
        message="old_text 与当前文件内容不匹配，文件可能已被用户修改。",
        conflict_detail=(
            f"原始内容长度: {len(original_content)}, 当前内容长度: {len(current_content)}, "
            f"old_text 长度: {len(old_text)}。请重新 read_file 确认文件当前内容。"
        ),
    )


def try_rebase_multi_edit(
    original_content: str,
    replacements: list[dict[str, str]],
    current_content: str,
) -> list[RebasedEdit]:
    """批量 rebase 多条编辑。"""
    results: list[RebasedEdit] = []
    for rep in replacements:
        result = try_rebase_edit(**rep, original_content=original_content, current_content=current_content)
        results.append(result)
    return results


# ---- Rebase 辅助函数 ----

def _diff_texts(original: str, current: str) -> list[dict[str, Any]]:
    if original == current:
        return []
    prefix_len = 0
    min_len = min(len(original), len(current))
    while prefix_len < min_len and original[prefix_len] == current[prefix_len]:
        prefix_len += 1
    suffix_len = 0
    while (suffix_len < min_len - prefix_len and
           original[len(original) - 1 - suffix_len] == current[len(current) - 1 - suffix_len]):
        suffix_len += 1
    orig_start, orig_end = prefix_len, len(original) - suffix_len
    curr_start, curr_end = prefix_len, len(current) - suffix_len
    if orig_start < orig_end and curr_start < curr_end:
        edit_type = "replace"
    elif orig_start < orig_end:
        edit_type = "delete"
    elif curr_start < curr_end:
        edit_type = "insert"
    else:
        return []
    return [{
        "start": curr_start, "end": curr_end,
        "orig_start": orig_start, "orig_end": orig_end,
        "type": edit_type,
        "original": original[orig_start:orig_end],
        "current": current[curr_start:curr_end],
    }]


def _ranges_overlap(start1: int, end1: int, range2: tuple[int, int] | None) -> bool:
    if range2 is None:
        return False
    start2, end2 = range2
    return start1 < end2 and start2 < end1


def _find_range(content: str, substring: str) -> tuple[int, int] | None:
    idx = content.find(substring)
    if idx == -1:
        return None
    return (idx, idx + len(substring))


def _adjust_for_user_edit(original: str, old_text: str, new_text: str, current: str, user_edit: dict[str, Any]) -> RebasedEdit | None:
    offset = len(user_edit["current"]) - len(user_edit["original"])
    if old_text in current:
        return RebasedEdit(result=RebaseResult.SUCCESS, old_text=old_text, new_text=old_text,
                           message=f"用户修改在 old_text 范围外，偏移 {offset} 字符后匹配成功")
    orig_idx = original.find(old_text)
    if orig_idx == -1:
        return None
    orig_end = orig_idx + len(old_text)
    if (user_edit["orig_start"] >= orig_idx and user_edit["orig_end"] <= orig_end):
        unchanged_before = old_text[:user_edit["orig_start"] - orig_idx]
        unchanged_after = old_text[user_edit["orig_end"] - orig_idx:]
        search_pattern = unchanged_before
        if search_pattern and search_pattern in current:
            pos = current.index(search_pattern)
            after_search_start = pos + len(search_pattern) + len(user_edit["current"])
            if (unchanged_after and after_search_start + len(unchanged_after) <= len(current) and
                    current[after_search_start:after_search_start + len(unchanged_after)] == unchanged_after):
                new_old_text = current[pos:after_search_start + len(unchanged_after)]
                return RebasedEdit(result=RebaseResult.PARTIAL, old_text=new_old_text, new_text=new_text,
                                   message="用户修改了 old_text 内部区域，已自动调整")
    return None


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _longest_common_prefix(s1: str, s2: str) -> int:
    min_len = min(len(s1), len(s2))
    for i in range(min_len):
        if s1[i] != s2[i]:
            return i
    return min_len


def _longest_common_suffix(s1: str, s2: str) -> int:
    min_len = min(len(s1), len(s2))
    for i in range(1, min_len + 1):
        if s1[-i] != s2[-i]:
            return i - 1
    return min_len


# =========================================================================
# Part 2: EditTools — 多策略编辑工具
# =========================================================================

class EditTools:
    """多策略编辑工具集合：批量替换 + unified diff 补丁。"""

    def __init__(self, work_dir: str | None = None) -> None:
        self._fm = FileManagerTool(work_dir=work_dir)
        self._work_dir = work_dir or ""

    # ------------------------------------------------------------------
    # 批量替换
    # ------------------------------------------------------------------

    def execute_multi_replace_string(self, *, file_path: str, replacements: list[dict[str, str]],
                                      skip_confirmation: bool = False) -> dict[str, Any]:
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
            content = target.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return self._error(f"读取失败: {exc}", normalized_path)

        applied: list[tuple[int, str, str]] = []
        for idx, rep in enumerate(replacements):
            old_text = rep.get("old_text", "")
            new_text = rep.get("new_text", "")
            if not old_text:
                return self._error(f"第 {idx + 1} 条 replacement 的 old_text 为空", normalized_path)
            if old_text not in content:
                return self._error(f"第 {idx + 1} 条 replacement 的 old_text 在文件中未找到。请重新 read_file 确认。", normalized_path)
            count = content.count(old_text)
            if count > 1:
                return self._error(f"第 {idx + 1} 条 replacement 的 old_text 出现 {count} 次，无法唯一定位。", normalized_path)
            pos = content.index(old_text)
            applied.append((pos, old_text, new_text))

        applied.sort(key=lambda x: x[0])
        for i in range(1, len(applied)):
            prev_end = applied[i - 1][0] + len(applied[i - 1][1])
            if applied[i][0] < prev_end:
                return self._error(f"第 {i} 条和第 {i + 1} 条 replacement 的 old_text 区域重叠。", normalized_path)

        new_content = content
        for pos, old_text, new_text in reversed(applied):
            new_content = new_content[:pos] + new_text + new_content[pos + len(old_text):]

        try:
            target.write_text(new_content, encoding="utf-8")
        except Exception as exc:
            return self._error(f"写入失败: {exc}", normalized_path)

        return {
            "success": True, "error": "", "output": f"成功批量替换文件内容\n{target}\n共完成 {len(applied)} 处替换",
            "file_path": str(target), "working_dir": str(self._fm.base_dir),
            "replacement_count": len(applied),
            "file_change": {"file_path": str(target), "operation": "modify", "previous_content": content, "new_content": new_content},
        }

    # ------------------------------------------------------------------
    # Unified Diff 补丁
    # ------------------------------------------------------------------

    def execute_apply_patch(self, *, file_path: str, patch: str,
                             skip_confirmation: bool = False) -> dict[str, Any]:
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
            original = target.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return self._error(f"读取失败: {exc}", normalized_path)

        try:
            new_content = _apply_unified_diff(original, patch)
        except PatchError as exc:
            return self._error(f"补丁应用失败: {exc}", normalized_path)
        except Exception as exc:
            return self._error(f"补丁解析失败: {exc}", normalized_path)

        if new_content == original:
            return self._error("补丁未产生任何修改，请检查 patch 内容。", normalized_path)
        try:
            target.write_text(new_content, encoding="utf-8")
        except Exception as exc:
            return self._error(f"写入失败: {exc}", normalized_path)

        return {
            "success": True, "error": "", "output": f"成功应用补丁\n{target}",
            "file_path": str(target), "working_dir": str(self._fm.base_dir),
            "file_change": {"file_path": str(target), "operation": "modify", "previous_content": original, "new_content": new_content},
        }

    # ------------------------------------------------------------------
    # 统一调用入口
    # ------------------------------------------------------------------

    def execute(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "multi_replace_string":
            return self.execute_multi_replace_string(**args)
        elif tool_name == "apply_patch":
            return self.execute_apply_patch(**args)
        else:
            return self._error(f"未知工具: {tool_name}", "")

    def _error(self, msg: str, path: str) -> dict[str, Any]:
        return {"success": False, "error": msg, "output": msg, "file_path": path, "working_dir": str(self._fm.base_dir)}


# ---------------------------------------------------------------------------
# Unified Diff 解析
# ---------------------------------------------------------------------------

class PatchError(Exception):
    pass


def _apply_unified_diff(original: str, patch: str) -> str:
    """应用 unified diff 格式的补丁。"""
    original_lines = original.splitlines(keepends=True)
    patch_lines = patch.splitlines()

    hunk_start = 0
    for i, line in enumerate(patch_lines):
        if line.startswith("@@"):
            hunk_start = i
            break
        elif line.startswith("---") or line.startswith("+++"):
            continue

    if hunk_start >= len(patch_lines):
        raise PatchError("补丁中没有找到 hunk（@@ ... @@）")

    result_lines: list[str] = []
    orig_idx = 0
    i = hunk_start

    while i < len(patch_lines):
        line = patch_lines[i]
        if line.startswith("@@"):
            match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if not match:
                raise PatchError(f"无效的 hunk 头: {line}")
            old_start = int(match.group(1))
            target_idx = old_start - 1
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
            if orig_idx < len(original_lines):
                orig_line = original_lines[orig_idx].rstrip("\n\r")
                if orig_line != content_part and orig_line.strip() != content_part.strip():
                    raise PatchError(f"上下文行不匹配（第 {orig_idx + 1} 行）: 期望 {content_part!r}, 实际 {orig_line!r}")
                result_lines.append(original_lines[orig_idx])
                orig_idx += 1
            i += 1
        elif prefix == "-":
            if orig_idx < len(original_lines):
                orig_line = original_lines[orig_idx].rstrip("\n\r")
                if orig_line != content_part and orig_line.strip() != content_part.strip():
                    raise PatchError(f"删除行不匹配（第 {orig_idx + 1} 行）: 期望 {content_part!r}, 实际 {orig_line!r}")
                orig_idx += 1
            i += 1
        elif prefix == "+":
            result_lines.append(content_part + "\n")
            i += 1
        elif prefix == "\\":
            i += 1
        else:
            i += 1

    while orig_idx < len(original_lines):
        result_lines.append(original_lines[orig_idx])
        orig_idx += 1
    return "".join(result_lines)


__all__ = [
    "EditTools",
    "PatchError",
    "RebaseResult",
    "RebasedEdit",
    "try_rebase_edit",
    "try_rebase_multi_edit",
]
