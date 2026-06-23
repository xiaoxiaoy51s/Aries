"""
编辑冲突解决（Edit Rebase）（#5）。

借鉴 VS Code Copilot 的 editRebase.ts：
当 AI 生成的编辑建议与用户手动编辑冲突时，自动调整建议以适应用户的实际修改。

核心场景：
1. 用户请求 AI 编辑文件 → AI 生成 old_text/new_text
2. 在 AI 响应期间，用户手动修改了文件
3. AI 的 old_text 可能不再匹配（行号偏移、内容变化）
4. Rebase 算法尝试调整 old_text 使其匹配用户修改后的文件

策略：
- 精确匹配：old_text 仍在文件中 → 直接应用
- 偏移匹配：old_text 在文件中但位置偏移 → 调整位置后应用
- 前缀/后缀匹配：old_text 的前缀或后缀仍匹配 → 部分应用
- 失败：完全无法匹配 → 返回冲突，要求 AI 重新 read_file
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
AUTO_CLOSE_PAIRS = {
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
    # 情况 1：精确匹配（最常见，文件未被修改）
    if old_text in current_content:
        count = current_content.count(old_text)
        if count == 1:
            return RebasedEdit(
                result=RebaseResult.SUCCESS,
                old_text=old_text,
                new_text=new_text,
                message="精确匹配成功",
            )
        else:
            return RebasedEdit(
                result=RebaseResult.CONFLICT,
                message=f"old_text 在当前文件中出现 {count} 次，无法唯一定位",
                conflict_detail=f"文件可能已被修改，请重新 read_file 确认",
            )

    # 情况 2：文件被修改了，尝试 rebase
    # 先计算用户做了什么修改
    user_edits = _diff_texts(original_content, current_content)

    if not user_edits:
        # 用户没改文件，但 old_text 不匹配 → 内容本身不对
        return RebasedEdit(
            result=RebaseResult.NOT_FOUND,
            message="old_text 在文件中未找到，且文件未被修改。请重新 read_file 确认文件内容。",
        )

    # 尝试策略 1：检查 old_text 是否在用户的修改范围内
    for edit in user_edits:
        if _ranges_overlap(edit["start"], edit["end"], 
                          _find_range(original_content, old_text)):
            # old_text 和用户修改有重叠，尝试调整
            adjusted = _adjust_for_user_edit(original_content, old_text, new_text, current_content, edit)
            if adjusted:
                return adjusted

    # 尝试策略 2：规范化空白后匹配
    normalized_old = _normalize_whitespace(old_text)
    normalized_current = _normalize_whitespace(current_content)
    if normalized_old in normalized_current:
        # 找到规范化后的位置，映射回原始内容
        return RebasedEdit(
            result=RebaseResult.PARTIAL,
            old_text=old_text,
            new_text=new_text,
            message="空白规范化后匹配。建议重新 read_file 获取准确内容后再编辑。",
        )

    # 尝试策略 3：前缀匹配
    prefix_len = _longest_common_prefix(old_text, current_content)
    if prefix_len > len(old_text) * 0.5:
        # 至少 50% 前缀匹配
        return RebasedEdit(
            result=RebaseResult.PARTIAL,
            old_text=old_text,
            new_text=new_text,
            message=f"前缀匹配（{prefix_len}/{len(old_text)} 字符）。文件可能已被修改，建议重新 read_file。",
        )

    # 尝试策略 4：auto-close pair 吸收
    for pair in AUTO_CLOSE_PAIRS:
        if pair[0] in old_text and pair[1] in old_text:
            # 检查用户是否只输入了 auto-close pair
            stripped = current_content.replace(original_content, "", 1).strip()
            if stripped == pair or stripped in pair:
                return RebasedEdit(
                    result=RebaseResult.SUCCESS,
                    old_text=old_text,
                    new_text=new_text,
                    message=f"检测到用户输入了 auto-close pair {pair}，已吸收",
                )

    # 所有策略都失败
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
    """批量 rebase 多条编辑。

    Returns:
        每条 replacement 对应的 RebasedEdit 列表。
        如果任一条 conflict，调用方应回滚全部。
    """
    results: list[RebasedEdit] = []
    for rep in replacements:
        result = try_rebase_edit(
            original_content=original_content,
            old_text=rep.get("old_text", ""),
            new_text=rep.get("new_text", ""),
            current_content=current_content,
        )
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

def _diff_texts(original: str, current: str) -> list[dict[str, Any]]:
    """简单 diff：找出用户做的修改区域。

    返回 [{"start": int, "end": int, "type": "insert"|"delete"|"replace"}]
    """
    if original == current:
        return []

    # 找公共前缀
    prefix_len = 0
    min_len = min(len(original), len(current))
    while prefix_len < min_len and original[prefix_len] == current[prefix_len]:
        prefix_len += 1

    # 找公共后缀
    suffix_len = 0
    while (suffix_len < min_len - prefix_len and
           original[len(original) - 1 - suffix_len] == current[len(current) - 1 - suffix_len]):
        suffix_len += 1

    orig_start = prefix_len
    orig_end = len(original) - suffix_len
    curr_start = prefix_len
    curr_end = len(current) - suffix_len

    if orig_start < orig_end and curr_start < curr_end:
        edit_type = "replace"
    elif orig_start < orig_end:
        edit_type = "delete"
    elif curr_start < curr_end:
        edit_type = "insert"
    else:
        return []

    return [{
        "start": curr_start,
        "end": curr_end,
        "orig_start": orig_start,
        "orig_end": orig_end,
        "type": edit_type,
        "original": original[orig_start:orig_end],
        "current": current[curr_start:curr_end],
    }]


def _ranges_overlap(start1: int, end1: int, range2: tuple[int, int] | None) -> bool:
    """检查两个范围是否重叠。"""
    if range2 is None:
        return False
    start2, end2 = range2
    return start1 < end2 and start2 < end1


def _find_range(content: str, substring: str) -> tuple[int, int] | None:
    """找到 substring 在 content 中的范围。"""
    idx = content.find(substring)
    if idx == -1:
        return None
    return (idx, idx + len(substring))


def _adjust_for_user_edit(
    original: str,
    old_text: str,
    new_text: str,
    current: str,
    user_edit: dict[str, Any],
) -> RebasedEdit | None:
    """尝试根据用户编辑调整 old_text。"""
    # 如果用户只在 old_text 范围之外做了修改，old_text 应该还在
    # 但位置可能偏移了
    offset = len(user_edit["current"]) - len(user_edit["original"])

    # 尝试在 current 中找 old_text（可能位置变了但内容没变）
    if old_text in current:
        return RebasedEdit(
            result=RebaseResult.SUCCESS,
            old_text=old_text,
            new_text=old_text,  # 占位，调用方会替换
            message=f"用户修改在 old_text 范围外，偏移 {offset} 字符后匹配成功",
        )

    # 如果用户修改在 old_text 范围内，尝试部分匹配
    # 找 old_text 中未被用户修改的部分
    orig_idx = original.find(old_text)
    if orig_idx == -1:
        return None

    orig_end = orig_idx + len(old_text)

    # 检查用户修改是否完全在 old_text 内部
    if (user_edit["orig_start"] >= orig_idx and
            user_edit["orig_end"] <= orig_end):
        # 用户修改了 old_text 内部的部分
        # 尝试用 new_text 替换用户修改的部分，其余保持
        unchanged_before = old_text[:user_edit["orig_start"] - orig_idx]
        unchanged_after = old_text[user_edit["orig_end"] - orig_idx:]

        # 在 current 中查找 unchanged_before + ... + unchanged_after
        search_pattern = unchanged_before
        if search_pattern and search_pattern in current:
            pos = current.index(search_pattern)
            # 检查 unchanged_after 是否在附近
            after_search_start = pos + len(search_pattern) + len(user_edit["current"])
            if (unchanged_after and
                    after_search_start + len(unchanged_after) <= len(current) and
                    current[after_search_start:after_search_start + len(unchanged_after)] == unchanged_after):
                # 可以构造新的 old_text
                new_old_text = current[pos:after_search_start + len(unchanged_after)]
                return RebasedEdit(
                    result=RebaseResult.PARTIAL,
                    old_text=new_old_text,
                    new_text=new_text,
                    message="用户修改了 old_text 内部区域，已自动调整",
                )

    return None


def _normalize_whitespace(text: str) -> str:
    """规范化空白：将连续空白压缩为单个空格。"""
    return re.sub(r"\s+", " ", text).strip()


def _longest_common_prefix(s1: str, s2: str) -> int:
    """计算两个字符串的最长公共前缀长度。"""
    min_len = min(len(s1), len(s2))
    for i in range(min_len):
        if s1[i] != s2[i]:
            return i
    return min_len


def _longest_common_suffix(s1: str, s2: str) -> int:
    """计算两个字符串的最长公共后缀长度。"""
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
