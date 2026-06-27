"""Computer Use 技能 — 让 AI 控制鼠标、键盘、截图、窗口管理、页面脚本。

工具列表（对应参考项目的 MCP 工具层）：
  - computer_screenshot : 截屏（全屏 / 指定区域 / 指定显示器）
  - computer_mouse      : 鼠标操作（移动 / 点击 / 双击 / 右键 / 滚轮 / 拖拽 / 获取位置）
  - computer_keyboard   : 键盘操作（输入文本 / 按键 / 组合键）
  - computer_window     : 窗口管理（列表 / 聚焦 / 关闭 / 最小化 / 最大化 / 启动应用）
  - computer_page_script: 页面脚本（一次截图确定的多个坐标，按顺序批量执行点击/输入）

实现委托给 win_backend（ctypes 直接调用 Win32 API，零额外依赖）。
"""
from __future__ import annotations

import json
import time
from typing import Any

import sys as _sys
from pathlib import Path as _Path

# 将本技能目录加入 sys.path，使 win_backend 可被直接 import
_skill_dir = _Path(__file__).resolve().parent
if str(_skill_dir) not in _sys.path:
    _sys.path.insert(0, str(_skill_dir))

import platform as _platform

if _platform.system() != "Windows":
    _win = None
    _BACKEND_ERROR = f"computer_use 仅支持 Windows，当前系统: {_platform.system()}"
else:
    try:
        import win_backend as _win
        _BACKEND_ERROR = ""
    except Exception as _e:
        _win = None
        _BACKEND_ERROR = f"win_backend 加载失败: {_e}"


# ═══════════════════════════════════════════════════════════════════
#  工具定义（OpenAI function calling schema）
# ═══════════════════════════════════════════════════════════════════

def get_tool_definitions() -> list[dict[str, Any]]:
    return [_TOOL_SCREENSHOT, _TOOL_MOUSE, _TOOL_KEYBOARD, _TOOL_WINDOW, _TOOL_PAGE_SCRIPT]


_TOOL_SCREENSHOT: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "computer_screenshot",
        "description": (
            "截取屏幕截图。这是兜底工具，仅在 CLI/Playwright/窗口命令都无法完成时使用。"
            "截图后你可以看到画面内容并估算归一化坐标 (0~1) 用于 computer_mouse 点击。"
            "不要每一步都截图，只在需要定位坐标或验证结果时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "monitor": {
                    "type": "integer",
                    "description": "显示器编号。0=所有显示器合并截图（默认），1=主显示器，2+=副显示器",
                    "default": 0,
                },
                "region": {
                    "type": "object",
                    "description": "指定截图区域（物理像素坐标）。不传则截取整个显示器。",
                    "properties": {
                        "x": {"type": "integer", "description": "区域左上角 X 坐标"},
                        "y": {"type": "integer", "description": "区域左上角 Y 坐标"},
                        "width": {"type": "integer", "description": "区域宽度"},
                        "height": {"type": "integer", "description": "区域高度"},
                    },
                },
            },
        },
    },
}

_TOOL_MOUSE: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "computer_mouse",
        "description": (
            "控制鼠标：移动、点击、双击、右键点击、中键点击、滚轮滚动、拖拽、获取当前位置。"
            "调用前必须先调用 computer_screenshot()。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["move", "click", "double_click", "right_click", "middle_click", "scroll", "drag", "position"],
                    "description": "鼠标操作类型",
                },
                "x": {"type": "number", "description": "目标 X 坐标。normalized=True 时为 0~1 归一化（推荐），否则为物理像素。必须来自最新 computer_screenshot。"},
                "y": {"type": "number", "description": "目标 Y 坐标。normalized=True 时为 0~1 归一化（推荐），否则为物理像素。必须来自最新 computer_screenshot。"},
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "description": "鼠标按键（click 动作时使用，默认 left）",
                    "default": "left",
                },
                "scroll_direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "滚轮方向（scroll 动作时使用）",
                    "default": "down",
                },
                "scroll_amount": {
                    "type": "integer",
                    "description": "滚轮滚动格数（scroll 动作时使用，默认 3）",
                    "default": 3,
                },
                "end_x": {"type": "number", "description": "拖拽终点 X 坐标（drag 动作时使用）"},
                "end_y": {"type": "number", "description": "拖拽终点 Y 坐标（drag 动作时使用）"},
                "normalized": {
                    "type": "boolean",
                    "description": "为 true 时 x/y 为 0~1 归一化坐标（推荐，不受分辨率影响，借鉴 UI-TARS）。为 false 时为物理像素坐标（默认）",
                    "default": False,
                },
            },
            "required": ["action"],
        },
    },
}

_TOOL_KEYBOARD: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "computer_keyboard",
        "description": (
            "控制键盘：输入文本（支持中文）、按下单个键、按下组合键（快捷键）。"
            "这是（窗口命令）：能直接输入文本或按快捷键完成的，不要截图。"
            "type 动作默认用 SendInput Unicode 直接发送字符（最可靠），method=sendinput 推荐用于豆包/微信等应用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["type", "press", "hotkey"],
                    "description": "键盘操作类型：type=输入文本, press=按键或组合键, hotkey=组合键（与 press 传多个键时效果相同）",
                },
                "text": {
                    "type": "string",
                    "description": "要输入的文本（type 动作时使用，支持中文等 Unicode 字符）",
                },
                "method": {
                    "type": "string",
                    "enum": ["auto", "sendinput", "clipboard"],
                    "description": "文本输入方式（仅 type 动作）。auto=自动选择（推荐），sendinput=直接发送 Unicode 按键，clipboard=剪贴板+Ctrl+V。默认 auto。",
                    "default": "auto",
                },
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "键名列表（press/hotkey 动作时使用）。"
                        "传 1 个键 = 单键按下再松开，如 [\"enter\"]；"
                        "传多个键 = 同时按下组合键，如 [\"win\",\"d\"] 或 [\"ctrl\",\"c\"]。"
                        "支持：a-z, 0-9, f1-f24, ctrl, alt, shift, win, enter, tab, escape, "
                        "backspace, delete, insert, home, end, pageup, pagedown, space, "
                        "up, down, left, right, capslock 等"
                    ),
                },
            },
            "required": ["action"],
        },
    },
}

_TOOL_WINDOW: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "computer_window",
        "description": (
            "窗口管理：列出所有窗口、聚焦窗口、关闭窗口、最小化/最大化/还原窗口、启动应用。"
            "命令优先工具：打开/聚焦应用时应优先使用本工具，不要先截图找图标。"
            "打开桌面应用前，建议先用 list_files 工具检查 ~/Desktop 是否存在对应快捷方式（如 微信.lnk / WeChat.lnk）；"
            "如果桌面没有，本工具会依次尝试 os.startfile、搜索桌面快捷方式、Windows 搜索（Win+输入名称）启动，最多 6 秒。"
            "窗口标题为模糊匹配（不区分大小写）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "focus", "close", "minimize", "maximize", "restore", "open"],
                    "description": "窗口操作类型",
                },
                "title": {
                    "type": "string",
                    "description": "窗口标题（模糊匹配，focus/close/minimize/maximize/restore 动作时使用）",
                },
                "app": {
                    "type": "string",
                    "description": "应用名称或路径（open 动作时使用，如 notepad, calc, explorer）",
                },
            },
            "required": ["action"],
        },
    },
}

_TOOL_PAGE_SCRIPT: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "computer_page_script",
        "description": (
            "页面脚本：基于一次截图确定的多个位置，按顺序依次执行操作。"
            "适合如：在输入框输入文字 → 点击发送按钮等连续操作。"
            "用法：先 computer_screenshot 获得一张完整截图，AI 在图中识别出所有交互位置，"
            "然后一次性提交本工具，指定每个步骤的坐标、操作类型（click/type）和文本。"
            "本工具会按顺序自动执行，无需每步都重新截图。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "description": "操作步骤列表，按顺序执行",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["click", "double_click", "right_click", "type"],
                                "description": "操作类型：click=单击, double_click=双击, right_click=右键, type=输入文本",
                            },
                            "x": {
                                "type": "number",
                                "description": "目标 X 坐标。normalized=True 时为 0~1 归一化，否则为物理像素。必须来自最新 computer_screenshot。",
                            },
                            "y": {
                                "type": "number",
                                "description": "目标 Y 坐标。normalized=True 时为 0~1 归一化，否则为物理像素。必须来自最新 computer_screenshot。",
                            },
                            "text": {
                                "type": "string",
                                "description": "要输入的文本（action=type 时必填，支持中文等 Unicode 字符）",
                            },
                            "normalized": {
                                "type": "boolean",
                                "description": "为 true 时 x/y 为 0~1 归一化坐标（推荐，不受分辨率影响）。为 false 时为物理像素坐标（默认）",
                                "default": False,
                            },
                        },
                        "required": ["action", "x", "y"],
                    },
                }
            },
            "required": ["steps"],
        },
    },
}


# ═══════════════════════════════════════════════════════════════════
#  执行分发器
# ═══════════════════════════════════════════════════════════════════

def execute(tool: str = "", **kwargs) -> dict[str, Any]:
    """工具执行入口。由 plugin_manager.execute_plugin_skill_tool 调用。"""
    if _win is None:
        return {"success": False, "error": _BACKEND_ERROR, "output": _BACKEND_ERROR}
    try:
        if tool == "computer_screenshot":
            return _exec_screenshot(**kwargs)
        if tool == "computer_mouse":
            return _exec_mouse(**kwargs)
        if tool == "computer_keyboard":
            return _exec_keyboard(**kwargs)
        if tool == "computer_window":
            return _exec_window(**kwargs)
        if tool == "computer_page_script":
            return _exec_page_script(**kwargs)
        return {"success": False, "error": f"未知工具: {tool}", "output": f"未知工具: {tool}"}
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "output": f"computer_use 工具执行异常: {e}\n{traceback.format_exc()}",
        }


def _exec_screenshot(**kwargs) -> dict:
    monitor = int(kwargs.get("monitor") or 0)
    region = kwargs.get("region")
    if region and isinstance(region, str):
        region = json.loads(region)
    return _win.screenshot(monitor=monitor, region=region)


def _exec_mouse(**kwargs) -> dict:
    action = (kwargs.get("action") or "").strip()
    x = kwargs.get("x")
    y = kwargs.get("y")
    normalized = bool(kwargs.get("normalized") or False)

    if action == "move":
        if x is None or y is None:
            return {"success": False, "error": "move 需要 x, y 参数", "output": "缺少坐标参数"}
        _win.mouse_move(x, y, normalized=normalized)
        return {"success": True, "output": f"鼠标已移动到 ({x}, {y}){' 归一化' if normalized else ''}"}

    if action in ("click", "double_click", "right_click", "middle_click"):
        button = "left"
        double = False
        if action == "right_click":
            button = "right"
        elif action == "middle_click":
            button = "middle"
        elif action == "double_click":
            double = True
        _win.mouse_click(
            x=x if x is not None else None,
            y=y if y is not None else None,
            button=button, double=double,
            normalized=normalized,
        )
        label = f"{'双击' if double else '点击'}({button})"
        pos = f" ({x}, {y}){' 归一化' if normalized else ''}" if x is not None else ""
        return {"success": True, "output": f"鼠标{label}{pos}"}

    if action == "scroll":
        direction = kwargs.get("scroll_direction") or "down"
        amount = int(kwargs.get("scroll_amount") or 3)
        _win.mouse_scroll(
            direction=direction, amount=amount,
            x=x if x is not None else None,
            y=y if y is not None else None,
            normalized=normalized,
        )
        return {"success": True, "output": f"滚轮{direction}滚动 {amount} 格"}

    if action == "drag":
        end_x = kwargs.get("end_x")
        end_y = kwargs.get("end_y")
        if x is None or y is None or end_x is None or end_y is None:
            return {"success": False, "error": "drag 需要 x, y, end_x, end_y 参数", "output": "缺少拖拽坐标"}
        _win.mouse_drag(x, y, end_x, end_y, normalized=normalized)
        return {"success": True, "output": f"已从 ({x},{y}) 拖拽到 ({end_x},{end_y}){' 归一化' if normalized else ''}"}

    if action == "position":
        px, py = _win.mouse_position()
        return {"success": True, "output": f"当前鼠标位置: ({px}, {py})", "x": px, "y": py}

    return {"success": False, "error": f"未知鼠标操作: {action}", "output": f"未知鼠标操作: {action}"}


def _exec_keyboard(**kwargs) -> dict:
    action = (kwargs.get("action") or "").strip()

    if action == "type":
        text = kwargs.get("text") or ""
        if not text:
            return {"success": False, "error": "type 需要 text 参数", "output": "缺少文本参数"}
        method = str(kwargs.get("method") or "auto").lower()
        _win.key_type(text, method=method)
        preview = text[:50] + ("..." if len(text) > 50 else "")
        return {"success": True, "output": f"已输入文本: {preview}"}

    if action == "press":
        keys = kwargs.get("keys") or []
        if isinstance(keys, str):
            keys = json.loads(keys) if keys.startswith("[") else [keys]
        if not keys:
            return {"success": False, "error": "press 需要 keys 参数", "output": "缺少按键参数"}
        # 多个键 → 组合键
        if len(keys) > 1:
            ok = _win.key_hotkey(keys)
            if not ok:
                unknown = [k for k in keys if _win._resolve_vk(k) is None]
                return {"success": False, "error": f"无法识别按键: {unknown}", "output": f"未知按键: {unknown}"}
            combo = "+".join(keys)
            return {"success": True, "output": f"已按下组合键: {combo}"}
        # 单个键 → 按下再松开
        key = keys[0]
        ok = _win.key_press(key)
        if not ok:
            return {"success": False, "error": f"无法识别按键: {key}", "output": f"未知按键: {key}"}
        return {"success": True, "output": f"已按键: {key}"}

    if action == "hotkey":
        keys = kwargs.get("keys") or []
        if isinstance(keys, str):
            keys = json.loads(keys) if keys.startswith("[") else [keys]
        if not keys or len(keys) < 2:
            return {"success": False, "error": "hotkey 需要至少 2 个键", "output": "组合键需要至少 2 个键"}
        ok = _win.key_hotkey(keys)
        if not ok:
            unknown = [k for k in keys if _win._resolve_vk(k) is None]
            return {"success": False, "error": f"无法识别按键: {unknown}", "output": f"未知按键: {unknown}"}
        combo = "+".join(keys)
        return {"success": True, "output": f"已按下组合键: {combo}"}

    return {"success": False, "error": f"未知键盘操作: {action}", "output": f"未知键盘操作: {action}"}


def _exec_window(**kwargs) -> dict:
    action = (kwargs.get("action") or "").strip()

    if action == "list":
        windows = _win.window_list()
        # 简化输出：只保留标题
        titles = [w["title"] for w in windows]
        return {
            "success": True,
            "output": f"当前有 {len(windows)} 个可见窗口:\n" + "\n".join(f"  - {t}" for t in titles),
            "windows": windows,
        }

    if action == "focus":
        title = kwargs.get("title") or ""
        return _win.window_focus(title)

    if action == "close":
        title = kwargs.get("title") or ""
        return _win.window_close(title)

    if action == "minimize":
        title = kwargs.get("title") or ""
        return _win.window_minimize(title)

    if action == "maximize":
        title = kwargs.get("title") or ""
        return _win.window_maximize(title)

    if action == "restore":
        title = kwargs.get("title") or ""
        return _win.window_restore(title)

    if action == "open":
        app = kwargs.get("app") or ""
        return _win.app_open(app)

    return {"success": False, "error": f"未知窗口操作: {action}", "output": f"未知窗口操作: {action}"}


def _exec_page_script(**kwargs) -> dict:
    """执行页面脚本：按顺序执行一系列操作（点击/输入），基于一次截图确定的坐标。"""
    steps = kwargs.get("steps") or []
    if not steps or not isinstance(steps, list):
        return {"success": False, "error": "steps 参数为空或格式错误", "output": "请提供 steps 列表"}

    total = len(steps)
    results: list[str] = []

    for i, step in enumerate(steps):
        action = (step.get("action") or "").strip()
        x = step.get("x")
        y = step.get("y")
        text = step.get("text") or ""
        normalized = bool(step.get("normalized") or False)

        if x is None or y is None:
            return {"success": False, "error": f"步骤 {i+1} 缺少坐标", "output": f"步骤 {i+1}/{total} 失败：缺少坐标"}

        label = f"步骤 {i+1}/{total}"

        if action == "type":
            if not text:
                return {"success": False, "error": f"步骤 {i+1} type 操作缺少 text", "output": f"{label} 失败：缺少 text"}
            # 先点击定位输入框
            _win.mouse_click(x, y, button="left", normalized=normalized)
            time.sleep(0.1)  # 100ms 等待光标定位
            _win.key_type(text, method="sendinput")
            results.append(f"{label}: 在 ({x},{y}) 输入「{text}」")
        elif action == "click":
            _win.mouse_click(x, y, button="left", normalized=normalized)
            results.append(f"{label}: 单击 ({x},{y})")
        elif action == "double_click":
            _win.mouse_click(x, y, button="left", double=True, normalized=normalized)
            results.append(f"{label}: 双击 ({x},{y})")
        elif action == "right_click":
            _win.mouse_click(x, y, button="right", normalized=normalized)
            results.append(f"{label}: 右键 ({x},{y})")
        else:
            return {"success": False, "error": f"步骤 {i+1} 未知操作: {action}", "output": f"{label} 失败：未知操作 {action}"}

        # 步骤间短停顿，确保前一步生效
        time.sleep(0.15)

    return {
        "success": True,
        "output": f"页面脚本执行完成，共 {total} 步:\n" + "\n".join(results),
        "steps_completed": total,
    }
