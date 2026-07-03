"""Fixed Agent mode detection and context building — Ask / Explore / Plan.

Mirrors the pattern used by code_review.py:
  1. Regex extracts the leading marker (@ask / @explore / @plan) from user text
  2. Returns (agent_name, cleaned_text)
  3. build_agent_mode_context(agent_name) produces the extra system prompt segment

The marker is consumed so the LLM never sees it; the mode rules are injected
directly into the system prompt instead.
"""
import re
from typing import Optional, Tuple

from prompt.agent_prompts import AGENT_MODES, get_agent_mode


def _match_marker(regex: re.Pattern, text: str, default: Optional[str] = None, lower: bool = False) -> Tuple[Optional[str], str]:
    """Extract a leading regex marker from text.

    Returns (group_value, cleaned_text). If no match, returns (None, original).
    ``default`` is used when the captured group is None (optional group in regex).
    ``lower`` controls whether the result is lowercased.
    """
    match = regex.match(text or "")
    if not match:
        return None, text
    value = match.group(1) if match.group(1) is not None else default
    if lower and value is not None:
        value = value.lower()
    cleaned = (text[match.end():] or "").lstrip()
    return value, cleaned


AGENT_MARKER_RE = re.compile(
    r"^@(ask|explore|plan)(?=\s|\n|$)",
    re.IGNORECASE,
)

# @subagent:<name> 模式 — 让子 Agent 直接作为当前响应的主体
SUBAGENT_MARKER_RE = re.compile(
    r"^@subagent:(\S+)(?:\s|\n|$)",
    re.IGNORECASE,
)


def extract_agent_marker(text: str) -> Tuple[Optional[str], str]:
    """Extract a leading fixed-agent marker from user text.

    Returns (agent_name, cleaned_text). If no marker is found, returns
    (None, original_text).

    Supported markers: @ask, @explore, @plan
    """
    return _match_marker(AGENT_MARKER_RE, text, lower=True)


def extract_subagent_marker(text: str) -> Tuple[Optional[str], str]:
    """Extract a leading @subagent:<name> marker from user text.

    Returns (subagent_name, cleaned_text). If no marker is found, returns
    (None, original_text).

    Supported markers: @subagent:<name>
    """
    return _match_marker(SUBAGENT_MARKER_RE, text)


def build_agent_mode_context(agent_name: str) -> str:
    """Build the extra system prompt segment for a fixed agent mode.

    Returns an empty string if the agent_name is unknown.
    """
    mode = get_agent_mode(agent_name)
    if not mode:
        return ""
    label = mode["label"]
    marker = mode["marker"]
    prompt = mode["prompt"]
    return (
        "\n"
        f"# 固定 Agent 模式：{label}\n"
        f"用户消息以 `{marker}` 开头，本轮必须严格按照「{label}」模式的规则执行。\n\n"
        f"{prompt}\n"
    )
