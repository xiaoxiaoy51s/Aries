"""
编辑冲突解决（Rebase）（#5）。

当 AI 生成的编辑建议与用户手动编辑冲突时，自动调整建议以适应用户的实际修改。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


# =========================================================================
# Edit Rebase（冲突解决）
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
    """尝试将 (old_text → new_text) 的编辑 rebase 到当前文件内容上。"""
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
        return RebasedEdit(result=RebaseResult.SUCCESS, old_text=old_text, new_text=new_text,
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


__all__ = [
    "RebaseResult",
    "RebasedEdit",
    "try_rebase_edit",
    "try_rebase_multi_edit",
]
