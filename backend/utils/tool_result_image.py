"""从工具结果（含 cli_executor 脚本 stdout）提取截图并注入视觉模型。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from utils.terminal_output import sanitize_terminal_output_for_ai

_SCREENSHOT_PATH_KEYS = ("screenshot_path", "path")


def _try_parse_embedded_json(text: str) -> dict[str, Any] | None:
    """从终端 output 中提取 JSON 对象（兼容 PowerShell 提示符前缀/后缀）。"""
    if not text or not isinstance(text, str):
        return None
    cleaned = sanitize_terminal_output_for_ai(text)
    if not cleaned:
        return None

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    for line in reversed(cleaned.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue

    start = cleaned.find("{")
    if start < 0:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(cleaned[start:])
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return None


def _load_image_base64_from_path(path: str) -> str:
    if not path:
        return ""
    p = Path(path).expanduser()
    if not p.is_file():
        return ""
    try:
        from utils.computer_use_lifecycle import _ensure_computer_use_import_paths
        if not _ensure_computer_use_import_paths():
            raise ImportError("computer_use skill 未找到")
        import win_backend as wb

        return wb._image_to_base64(str(p)) or ""
    except Exception:
        try:
            import base64
            import io

            from PIL import Image

            img = Image.open(p)
            if img.mode != "RGB":
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            return ""


def _screenshot_path_from_dict(data: dict[str, Any]) -> str:
    for key in _SCREENSHOT_PATH_KEYS:
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _extract_base64_from_data_url(url: str) -> str:
    if not isinstance(url, str) or "base64," not in url:
        return ""
    return url.split("base64,", 1)[1].strip()


def _strip_screenshot_urls(data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Extract screenshot base64 and remove data URLs from tool result dict."""
    merged = dict(data)
    image_b64 = str(merged.pop("image_base64", "") or "")

    shots = merged.get("screenshots")
    if isinstance(shots, list):
        clean_shots: list[dict[str, Any]] = []
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            url = shot.get("url", "")
            if not image_b64:
                image_b64 = _extract_base64_from_data_url(url)
            clean = {k: v for k, v in shot.items() if k != "url"}
            if url:
                clean["has_image"] = True
            clean_shots.append(clean)
        merged["screenshots"] = clean_shots

    state = merged.get("state")
    if isinstance(state, dict):
        _, state = _strip_screenshot_urls(state)
        merged["state"] = state

    return image_b64, merged


def prepare_screenshot_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    """规范化工具结果：从嵌套 stdout / 截图文件加载 image_base64，并缩短 output 文本。"""
    if not isinstance(result, dict):
        return result

    payload = {k: v for k, v in result.items() if k != "captured_output"}
    output = payload.get("output")
    embedded: dict[str, Any] | None = None

    if isinstance(output, str):
        payload["output"] = sanitize_terminal_output_for_ai(output)
        embedded = _try_parse_embedded_json(output)

    merged = dict(payload)
    if embedded:
        for key, val in embedded.items():
            if key == "output":
                continue
            if key not in merged or merged.get(key) in (None, ""):
                merged[key] = val
        if embedded.get("output"):
            merged["_script_output"] = embedded["output"]

    image_b64 = str(merged.get("image_base64") or "")
    if not image_b64:
        path = _screenshot_path_from_dict(merged)
        if not path and embedded:
            path = _screenshot_path_from_dict(embedded)
        if path:
            merged["screenshot_path"] = path
            image_b64 = _load_image_base64_from_path(path)

    if image_b64:
        merged["image_base64"] = image_b64
        w, h = merged.get("width"), merged.get("height")
        script_out = merged.pop("_script_output", None)
        if isinstance(script_out, str) and script_out and len(script_out) < 800:
            merged["output"] = script_out
        elif w and h:
            merged["output"] = f"截图已保存 ({w}x{h})，路径: {merged.get('screenshot_path', '')}"
        else:
            merged["output"] = "截图已完成，画面已通过视觉通道注入。"

    merged.pop("_script_output", None)

    # 剥离 screenshots/state 中的 data URL，避免 base64 进入模型上下文
    extracted, merged = _strip_screenshot_urls(merged)
    final_b64 = image_b64 or extracted
    if final_b64:
        merged["image_base64"] = final_b64
        shots = merged.get("screenshots") or []
        if shots and isinstance(shots[0], dict):
            s0 = shots[0]
            out = merged.get("output")
            if not isinstance(out, str) or len(out) > 500 or "base64" in out:
                merged["output"] = (
                    f"窗口截图已捕获 ({s0.get('width', '?')}x{s0.get('height', '?')})，"
                    f"id={s0.get('id', '?')}。画面已通过视觉通道注入。"
                )
        elif not merged.get("output"):
            merged["output"] = "截图已完成，画面已通过视觉通道注入。"

    return merged


def split_tool_result_image(content: str) -> tuple[str, str]:
    """剥离 tool 消息 JSON 中的 image_base64 / screenshots.url，返回 (瘦身后 content, base64)。"""
    if not content or not isinstance(content, str):
        return content, ""
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content, ""

    if not isinstance(parsed, dict):
        return content, ""

    prepared = prepare_screenshot_tool_result(parsed)
    image_b64 = str(prepared.pop("image_base64", "") or "")
    return json.dumps(prepared, ensure_ascii=False), image_b64


def format_tool_result_for_model(result: dict) -> str:
    """构建发给 LLM 的工具结果 JSON（含 image_base64 供后续 strip 注入视觉）。"""
    prepared = prepare_screenshot_tool_result(result) if isinstance(result, dict) else result
    if not isinstance(prepared, dict):
        return str(prepared)
    return json.dumps(prepared, ensure_ascii=False)


def tool_result_for_logging(result: dict) -> dict:
    """写入 JSONL / 前端展示用的工具结果（不含 image_base64 / data URL）。"""
    prepared = prepare_screenshot_tool_result(result) if isinstance(result, dict) else {}
    if not isinstance(prepared, dict):
        return {"output": str(result)}
    log = dict(prepared)
    preview_b64 = str(log.pop("image_base64", "") or "")
    if preview_b64:
        log["screenshot_preview"] = f"data:image/jpeg;base64,{preview_b64}"
    out = log.get("output")
    if isinstance(out, str) and len(out) > 2000:
        if "image_base64" in out or re.search(r'"[A-Za-z0-9+/]{500,}"', out):
            w, h = log.get("width"), log.get("height")
            log["output"] = f"截图已保存 ({w}x{h})" if w and h else "截图已完成"
    return log
