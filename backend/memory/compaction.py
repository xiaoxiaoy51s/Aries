"""会话记忆压缩。

借鉴 Claude Code 的 CompactBoundary 思路和 OpenCode 的结构化摘要模板：
- 将旧消息压缩为一条 session memory，不再固定加载最近 14 轮；
- 保留最近窗口，避免 tool_call / tool_result 被硬切断；
- 压缩摘要调用 LLM 生成结构化记忆，失败时回退到确定性规则。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx

from utils.token_counter import estimate_tokens, estimate_message_tokens
from utils.url_utils import normalize_base_url
from utils.network_manager import get_httpx_proxy_for_url

logger = logging.getLogger(__name__)

MAX_TOOL_RESULT_CHARS = 2_000
MAX_MESSAGE_CHARS = 4_000
MAX_SUMMARY_CHARS = 12_000
MAX_LLM_INPUT_CHARS = 60_000  # 送给摘要 LLM 的历史文本上限
DEFAULT_KEEP_TOKENS = 10_000
DEFAULT_MAX_HISTORY_TOKENS = 180_000


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated]"


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") == "image_url":
                    parts.append("[image]")
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(p for p in parts if p)
    return str(content)


def _format_message(message: dict[str, Any]) -> str:
    role = message.get("role", "unknown")
    content = _message_text(message)
    if role == "tool":
        content = _truncate(content, MAX_TOOL_RESULT_CHARS)
    else:
        content = _truncate(content, MAX_MESSAGE_CHARS)
    return f"[{role}] {content}".strip()


def _extract_file_mentions(text: str) -> list[str]:
    import re

    # 匹配文件路径：包含斜杠/反斜杠的路径，或明确的文件名（xxx.py / xxx.ts 等）
    # 排除变量访问（item.price）、缩写（e.g）等
    file_ext_pattern = r'(?:[A-Za-z]:\\[^\s`\'"]+|[/~][^\s`\'"]+|(?:src|backend|frontend|tests?|docs?|config|api|utils|components?|engine|db|memory|prompt|plugins?)[/\\][^\s`\'"]+|[\w-]+\.(?:py|ts|js|vue|json|md|yaml|yml|toml|css|scss|html|sql|sh|bat|ps1|tsx|jsx))'
    candidates = re.findall(file_ext_pattern, text)
    result: list[str] = []
    for item in candidates:
        cleaned = item.rstrip(".,;:)")
        # 排除太短的误匹配
        if len(cleaned) < 4:
            continue
        if cleaned not in result:
            result.append(cleaned)
        if len(result) >= 12:
            break
    return result


def _format_history_for_llm(messages: list[dict[str, Any]]) -> str:
    """将消息列表格式化为 LLM 可读的对话文本，控制总长度。"""
    lines: list[str] = []
    total_chars = 0
    for msg in messages:
        role = msg.get("role", "unknown")
        content = _message_text(msg)
        if not content or not content.strip():
            continue
        # 工具结果截断到更短
        if role == "tool":
            content = _truncate(content, 800)
        else:
            content = _truncate(content, 2000)
        line = f"[{role}] {content}".strip()
        if total_chars + len(line) > MAX_LLM_INPUT_CHARS:
            remaining = MAX_LLM_INPUT_CHARS - total_chars
            if remaining > 200:
                lines.append(line[:remaining] + "\n[...截断...]")
            break
        lines.append(line)
        total_chars += len(line) + 1
    return "\n".join(lines)


SUMMARY_SYSTEM_PROMPT = """你是一个对话摘要助手。请将以下用户与 AI 助手的对话历史压缩为简洁的中文摘要。

要求：
1. 用几百字概述对话中实际做了什么，不要用模板套话
2. 如果没有对应内容，直接省略该部分，不要写 "(none)"
3. 涉及的文件路径只列出真正被编辑或读取的文件，不要列变量名或缩写
4. 保持简洁，总长度控制在 500 字以内

格式：
## 目标
（用户想做什么）

## 已完成
（实际做了哪些工作）

## 关键决策
（如有重要技术选择或决策）

## 下一步
（根据对话推断的后续方向）

## 相关文件
（列出真正涉及到的文件路径，没有则省略此节）"""


async def build_session_summary_with_llm(
    messages: list[dict[str, Any]],
    base_url: str,
    api_key: str,
    model: str,
) -> str | None:
    """调用 LLM 生成结构化摘要。失败返回 None。"""
    if not base_url or not api_key or not model:
        return None

    history_text = _format_history_for_llm(messages)
    if not history_text.strip():
        return None

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": f"以下是待压缩的对话历史：\n\n{history_text}"},
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, proxy=get_httpx_proxy_for_url(base_url)) as client:
            resp = await client.post(
                f"{normalize_base_url(base_url)}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code != 200:
                logger.warning("[Compactor] LLM 摘要请求失败 %d: %s", resp.status_code, resp.text[:200])
                return None
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                return None
            content = choices[0].get("message", {}).get("content", "") or ""
            content = content.strip()
            if not content:
                return None
            return _truncate(content, MAX_SUMMARY_CHARS)
    except Exception as exc:
        logger.warning("[Compactor] LLM 摘要异常: %s", exc)
        return None


def build_session_summary(messages: list[dict[str, Any]]) -> str:
    """确定性规则回退摘要（LLM 不可用时使用）。"""
    user_messages = [m for m in messages if m.get("role") == "user"]
    assistant_messages = [m for m in messages if m.get("role") == "assistant"]
    tool_messages = [m for m in messages if m.get("role") == "tool"]

    first_user = _message_text(user_messages[0]) if user_messages else ""
    last_user = _message_text(user_messages[-1]) if user_messages else ""
    recent_assistant = [_message_text(m) for m in assistant_messages[-5:]]
    recent_tools = [_message_text(m) for m in tool_messages[-8:]]

    all_text = "\n".join(_message_text(m) for m in messages)
    files = _extract_file_mentions(all_text)

    parts: list[str] = []

    if first_user:
        parts.append(f"## 目标\n- {_truncate(first_user.replace(chr(10), ' '), 800)}")

    done_lines = []
    for text in recent_assistant:
        text = text.strip()
        if text:
            done_lines.append(f"- {_truncate(text.replace(chr(10), ' '), 300)}")
    if done_lines:
        parts.append("## 已完成\n" + "\n".join(done_lines))

    if last_user:
        parts.append(f"## 下一步\n- {_truncate(last_user.replace(chr(10), ' '), 800)}")

    if files:
        parts.append("## 相关文件\n" + "\n".join(f"- {f}" for f in files))

    return _truncate("\n\n".join(parts), MAX_SUMMARY_CHARS)


def split_messages_for_compaction(
    messages: list[dict[str, Any]],
    keep_tokens: int = DEFAULT_KEEP_TOKENS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """返回 (to_compact, to_keep)。从尾部保留约 keep_tokens 的近期消息。"""
    if not messages:
        return [], []

    total = 0
    keep_start = len(messages)
    for idx in range(len(messages) - 1, -1, -1):
        total += estimate_message_tokens(messages[idx])
        keep_start = idx
        if total >= keep_tokens:
            break

    # 避免把 tool 结果留在窗口开头而丢失对应 assistant tool_call。
    while keep_start > 0 and messages[keep_start].get("role") == "tool":
        keep_start -= 1

    return messages[:keep_start], messages[keep_start:]


def should_compact(messages: list[dict[str, Any]], max_history_tokens: int = DEFAULT_MAX_HISTORY_TOKENS) -> bool:
    """判断历史是否需要压缩。"""
    total = sum(estimate_message_tokens(m) for m in messages)
    return total > max_history_tokens or len(messages) > 80


def make_memory_record(
    session_id: str,
    messages: list[dict[str, Any]],
    summary_override: str = "",
) -> dict[str, Any]:
    """生成可存储的 session memory 记录。"""
    summary = summary_override.strip() if summary_override and summary_override.strip() else build_session_summary(messages)
    return {
        "session_id": session_id,
        "summary": summary,
        "source_message_count": len(messages),
        "source_token_estimate": sum(estimate_message_tokens(m) for m in messages),
        "summary_token_estimate": estimate_tokens(summary),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


# ===========================================================================
# 后台异步压缩（#6）
# ===========================================================================

import asyncio
import logging
import random
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class CompactionState(Enum):
    """压缩状态机。"""
    IDLE = "idle"           # 无压缩任务
    IN_PROGRESS = "in_progress"  # 正在压缩
    COMPLETED = "completed"  # 压缩完成，摘要可用
    FAILED = "failed"        # 压缩失败


# 阈值常量（借鉴 VS Code backgroundSummarizer.ts）
WARM_JITTER_MIN = 0.78       # 暖缓存下限
WARM_JITTER_SPAN = 0.04      # 暖缓存范围宽度 → [0.78, 0.82)
EMERGENCY_RATIO = 0.90       # 紧急阈值：即使冷缓存也要压缩
APPLY_MIN_RATIO = 0.65       # 低于此比例不应用已完成的摘要
MIN_MESSAGES_FOR_COMPACT = 20  # 消息数不足时不压缩


@dataclass
class CompactionResult:
    """一次压缩的结果。"""
    state: CompactionState
    summary: str = ""
    summary_tokens: int = 0
    source_messages: int = 0
    source_tokens: int = 0
    error: str = ""
    created_at: str = ""


@dataclass
class SessionCompactionTracker:
    """单个会话的压缩状态追踪。"""
    session_id: str
    state: CompactionState = CompactionState.IDLE
    pending_result: CompactionResult | None = None
    last_compact_message_count: int = 0
    last_compact_at: str = ""
    _task: asyncio.Task | None = field(default=None, repr=False)

    def is_warm(self) -> bool:
        """是否处于暖缓存状态（最近刚完成过一次工具调用轮次）。"""
        return self.state == CompactionState.COMPLETED and bool(self.pending_result)

    def can_apply(self, current_ratio: float) -> bool:
        """是否可以应用已完成的摘要。"""
        if not self.pending_result or self.state != CompactionState.COMPLETED:
            return False
        return current_ratio >= APPLY_MIN_RATIO


class BackgroundCompactor:
    """后台对话压缩管理器。

    借鉴 VS Code Copilot 的 backgroundSummarizer.ts：
    - 在 Agent 回复完成后检查是否需要触发后台压缩
    - 暖缓存（刚完成工具调用）在 ~80% 触发
    - 冷缓存在 90% 紧急触发，避免下次请求时阻塞
    - 压缩异步执行，不阻塞主流程
    - 下次请求时如果压缩已完成则应用，否则继续用原始历史

    用法：
        compactor = BackgroundCompactor()
        # 每轮 Agent 回复后检查
        compactor.maybe_trigger_compaction(session_id, messages, context_window=200000)
        # 下次请求前检查是否有已完成的压缩
        result = compactor.get_pending_result(session_id)
        if result and result.state == CompactionState.COMPLETED:
            # 应用摘要，替换旧消息
            ...
    """

    def __init__(self) -> None:
        self._trackers: dict[str, SessionCompactionTracker] = {}

    def get_tracker(self, session_id: str) -> SessionCompactionTracker:
        if session_id not in self._trackers:
            self._trackers[session_id] = SessionCompactionTracker(session_id=session_id)
        return self._trackers[session_id]

    def compute_context_ratio(
        self,
        messages: list[dict[str, Any]],
        context_window: int = 200_000,
    ) -> float:
        """计算当前上下文占用比例。"""
        if context_window <= 0:
            return 0.0
        total_tokens = sum(estimate_message_tokens(m) for m in messages)
        return total_tokens / context_window

    def should_trigger(
        self,
        messages: list[dict[str, Any]],
        context_window: int = 200_000,
        is_warm: bool = False,
    ) -> bool:
        """判断是否应该触发后台压缩。

        Args:
            messages: 当前会话消息列表
            context_window: 模型上下文窗口大小
            is_warm: 是否处于暖缓存状态（刚完成工具调用轮次）
        """
        if len(messages) < MIN_MESSAGES_FOR_COMPACT:
            return False

        ratio = self.compute_context_ratio(messages, context_window)

        # 紧急阈值：无论冷热都要压缩
        if ratio >= EMERGENCY_RATIO:
            return True

        # 暖缓存阈值：带 jitter
        if is_warm:
            threshold = WARM_JITTER_MIN + random.uniform(0, WARM_JITTER_SPAN)
            if ratio >= threshold:
                return True

        # 消息数过多也触发
        if len(messages) > 40:
            return True

        return False

    def maybe_trigger_compaction(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        context_window: int = 200_000,
        is_warm: bool = False,
    ) -> bool:
        """如果需要，触发后台压缩。返回是否触发了压缩。"""
        tracker = self.get_tracker(session_id)

        # 已有压缩在进行中，不重复触发
        if tracker.state == CompactionState.IN_PROGRESS:
            return False

        if not self.should_trigger(messages, context_window, is_warm):
            return False

        # 触发后台压缩
        self._start_compaction(session_id, messages)
        return True

    def _start_compaction(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        """启动异步压缩任务。"""
        tracker = self.get_tracker(session_id)
        tracker.state = CompactionState.IN_PROGRESS

        # 取快照，避免压缩过程中消息被修改
        messages_snapshot = [dict(m) for m in messages]

        async def _compact():
            try:
                to_compact, _ = split_messages_for_compaction(messages_snapshot)
                if not to_compact:
                    tracker.state = CompactionState.IDLE
                    return

                # 优先用 LLM 生成摘要，失败时回退到确定性规则
                summary = None
                try:
                    from models.model_manager import resolve_active_model_config
                    base_url, api_key, model = resolve_active_model_config()
                    if base_url and api_key and model:
                        summary = await build_session_summary_with_llm(
                            to_compact, base_url, api_key, model,
                        )
                except Exception as exc:
                    logger.warning("[Compactor] LLM 摘要初始化失败: %s", exc)

                if not summary:
                    summary = build_session_summary(to_compact)

                result = CompactionResult(
                    state=CompactionState.COMPLETED,
                    summary=summary,
                    summary_tokens=estimate_tokens(summary),
                    source_messages=len(to_compact),
                    source_tokens=sum(estimate_message_tokens(m) for m in to_compact),
                    created_at=datetime.now().isoformat(timespec="seconds"),
                )
                tracker.pending_result = result
                tracker.state = CompactionState.COMPLETED
                tracker.last_compact_message_count = len(messages_snapshot)
                tracker.last_compact_at = result.created_at
                logger.info(
                    "[Compactor] 会话 %s 后台压缩完成: %d 消息 → %d tokens 摘要",
                    session_id, result.source_messages, result.summary_tokens,
                )
            except Exception as exc:
                tracker.state = CompactionState.FAILED
                tracker.pending_result = CompactionResult(
                    state=CompactionState.FAILED,
                    error=str(exc),
                )
                logger.warning("[Compactor] 会话 %s 后台压缩失败: %s", session_id, exc)

        # 尝试获取事件循环
        try:
            loop = asyncio.get_event_loop()
            tracker._task = loop.create_task(_compact())
        except RuntimeError:
            # 没有事件循环，同步执行
            tracker._task = None
            asyncio.run(_compact())

    def get_pending_result(self, session_id: str) -> CompactionResult | None:
        """获取已完成的压缩结果（不阻塞）。"""
        tracker = self.get_tracker(session_id)
        if tracker.state == CompactionState.COMPLETED and tracker.pending_result:
            return tracker.pending_result
        return None

    def consume_result(self, session_id: str) -> CompactionResult | None:
        """获取并消费压缩结果（取出后清除）。"""
        tracker = self.get_tracker(session_id)
        result = tracker.pending_result
        tracker.pending_result = None
        tracker.state = CompactionState.IDLE
        return result

    def cancel(self, session_id: str) -> None:
        """取消会话的后台压缩。"""
        tracker = self.get_tracker(session_id)
        if tracker._task and not tracker._task.done():
            tracker._task.cancel()
        tracker.state = CompactionState.IDLE
        tracker.pending_result = None


# 全局单例
_compactor: BackgroundCompactor | None = None


def get_compactor() -> BackgroundCompactor:
    """获取全局 BackgroundCompactor 实例。"""
    global _compactor
    if _compactor is None:
        _compactor = BackgroundCompactor()
    return _compactor


# ---------------------------------------------------------------------------
# 增强的压缩判断（替换原有 should_compact）
# ---------------------------------------------------------------------------

def should_compact_enhanced(
    messages: list[dict[str, Any]],
    context_window: int = 200_000,
    is_warm: bool = False,
    max_history_tokens: int = DEFAULT_MAX_HISTORY_TOKENS,
) -> bool:
    """增强的压缩判断（带阈值策略）。

    比 should_compact 更精细：
    - 支持暖/冷缓存区分
    - 支持上下文窗口比例判断
    - 保留消息数判断作为兜底
    """
    compactor = get_compactor()
    return compactor.should_trigger(
        messages=messages,
        context_window=context_window,
        is_warm=is_warm,
    ) or should_compact(messages, max_history_tokens)
