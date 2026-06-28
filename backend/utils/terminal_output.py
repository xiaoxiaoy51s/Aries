"""终端输出清理：去除 ANSI/VT 转义序列，供 AI 阅读。"""
from __future__ import annotations

import re

# CSI：\x1b[...] 或 C1 \x9b...，以及 ESC 丢失后的残留 [?9001h 等
_ANSI_CSI = re.compile(
    r"(?:\x9b|\x1b\[)[\0-\?]*[ -/]*[@-~]"
    r"|\[[\?]?[0-9;]*[ -/]*[@-~]"
)
# OSC：窗口标题等（\x1b]0;...\x07 或 C1 \x9d...）
_ANSI_OSC = re.compile(
    r"(?:\x9d|\x1b\])[^\x07\x1b\[\n]*(?:\x07|\x1b\\)"
    r"|\]0;[^\[\x07\x1b\n]+"
)
# 其他 ESC 两字符序列
_ANSI_OTHER = re.compile(r"\x1b[=>78MNcD]")
# 控制字符（保留 \t \n）
_CTRL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1a\x7f-\x9a\x9c\x9e-\x9f]")


def sanitize_terminal_output_for_ai(raw: str) -> str:
    """去除 ANSI 转义与控制字符，保留可读文本。"""
    if not raw:
        return raw
    cleaned = raw
    for pattern in (_ANSI_OSC, _ANSI_CSI, _ANSI_OTHER, _CTRL_CHARS):
        cleaned = pattern.sub("", cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def format_tool_result_for_model(result: dict) -> str:
    """构建发给 LLM 的工具结果 JSON，去掉前端专用字段并清理 output。"""
    import json

    payload = {k: v for k, v in result.items() if k != "captured_output"}
    output = payload.get("output")
    if isinstance(output, str):
        payload["output"] = sanitize_terminal_output_for_ai(output)
    return json.dumps(payload, ensure_ascii=False)
