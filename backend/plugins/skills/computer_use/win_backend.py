"""Windows computer-use 后端：基于 ctypes 直接调用 Win32 API，零额外依赖。

分层设计（对应参考项目的 dispatcher + backend 模式）：
  - 鼠标：SetCursorPos + mouse_event
  - 键盘：keybd_event + VkKeyScanW；非 ASCII 文本走剪贴板 + Ctrl+V
  - 截图：PIL.ImageGrab（优先）/ PowerShell Add-Type System.Drawing（降级）
  - 窗口：EnumWindows + SetForegroundWindow + ShowWindow + PostMessage
  - 剪贴板：OpenClipboard / GetClipboardData / SetClipboardData
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as w
import io
import os
import subprocess
import time
from pathlib import Path
from typing import Any

# ── DPI 感知：确保获取物理像素坐标 ──────────────────────────────
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# ── 常量 ──────────────────────────────────────────────────────────
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000

WHEEL_DELTA = 120
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_RESTORE = 9
SW_HIDE = 0
SW_SHOW = 5

WM_CLOSE = 0x0010
WM_PASTE = 0x0302

CF_UNICODETEXT = 13

# ── SendInput 结构体 ──────────────────────────────────────────────

class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", w.LONG), ("dy", w.LONG),
        ("mouseData", w.DWORD), ("dwFlags", w.DWORD),
        ("time", w.DWORD), ("dwExtraInfo", ctypes.c_void_p),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", w.WORD), ("wScan", w.WORD),
        ("dwFlags", w.DWORD), ("time", w.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUT_U(ctypes.Union):
    _fields_ = [
        ("mi", _MOUSEINPUT),
        ("ki", _KEYBDINPUT),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type", w.DWORD),
        ("u", _INPUT_U),
    ]
GMEM_MOVEABLE = 0x0002

# ── 虚拟键码映射 ──────────────────────────────────────────────────
VK_MAP: dict[str, int] = {
    # 修饰键
    "ctrl": 0x11, "control": 0x11,
    "alt": 0x12, "menu": 0x12, "option": 0x12,
    "shift": 0x10,
    "win": 0x5B, "super": 0x5B, "meta": 0x5B, "cmd": 0x5B,
    # 功能键
    **{f"f{i}": 0x6F + i for i in range(1, 25)},
    # 导航 / 编辑
    "enter": 0x0D, "return": 0x0D, "numpad_enter": 0x0D,
    "tab": 0x09,
    "escape": 0x1B, "esc": 0x1B,
    "backspace": 0x08, "back": 0x08,
    "delete": 0x2E, "del": 0x2E,
    "insert": 0x2D, "ins": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21, "page_up": 0x21, "pgup": 0x21,
    "pagedown": 0x22, "page_down": 0x22, "pgdn": 0x22,
    "space": 0x20, "spacebar": 0x20,
    # 方向键
    "up": 0x26, "arrowup": 0x26, "arrow_up": 0x26,
    "down": 0x28, "arrowdown": 0x28, "arrow_down": 0x28,
    "left": 0x25, "arrowleft": 0x25, "arrow_left": 0x25,
    "right": 0x27, "arrowright": 0x27, "arrow_right": 0x27,
    # 锁定键
    "capslock": 0x14, "caps_lock": 0x14,
    "numlock": 0x90, "num_lock": 0x90,
    "scrolllock": 0x91, "scroll_lock": 0x91,
    # 其他
    "printscreen": 0x2C, "print_screen": 0x2C, "prtsc": 0x2C,
    "pause": 0x13, "break": 0x13,
    "menu": 0xA4, "apps": 0xA5,
}

# 数字键 0-9
for _c in "0123456789":
    VK_MAP[_c] = ord(_c)

# 字母 a-z → VK 0x41-0x5A
for _c in "abcdefghijklmnopqrstuvwxyz":
    VK_MAP[_c] = ord(_c.upper())


def _resolve_vk(key: str) -> int | None:
    """将键名解析为虚拟键码。"""
    key = key.strip().lower()
    if key in VK_MAP:
        return VK_MAP[key]
    # 单字符
    if len(key) == 1:
        return VkKeyScanW(key) & 0xFF
    return None


def VkKeyScanW(ch: str) -> int:
    """Unicode 字符 → 虚拟键码 + 修饰键状态。"""
    return user32.VkKeyScanW(ord(ch))


# ═══════════════════════════════════════════════════════════════════
#  屏幕尺寸 & 归一化坐标转换（借鉴 UI-TARS 方案）
# ═══════════════════════════════════════════════════════════════════

def get_screen_size() -> tuple[int, int]:
    """返回主显示器 (宽度, 高度)，物理像素。"""
    user32.SetProcessDPIAware()
    w_ = w.DWORD()
    h_ = w.DWORD()
    user32.GetSystemMetrics(0)  # SM_CXSCREEN
    cx = user32.GetSystemMetrics(0)
    cy = user32.GetSystemMetrics(1)
    return (cx, cy)


def _norm_to_physical(x: float, y: float) -> tuple[int, int]:
    """归一化坐标 (0~1) → 物理像素坐标。"""
    sw, sh = get_screen_size()
    px = int(round(x * sw))
    py = int(round(y * sh))
    return (px, py)


# ═══════════════════════════════════════════════════════════════════
#  鼠标
# ═══════════════════════════════════════════════════════════════════

def mouse_move(x, y, normalized: bool = False) -> None:
    """移动鼠标到绝对坐标 (x, y)。

    normalized=True 时 x,y 为 0~1 归一化坐标（借鉴 UI-TARS）。
    normalized=False 时 x,y 为物理像素坐标。
    """
    if normalized:
        x, y = _norm_to_physical(float(x), float(y))
    user32.SetCursorPos(int(x), int(y))


def _mouse_event(flags: int, data: int = 0) -> None:
    user32.mouse_event(flags, 0, 0, data, 0)


def mouse_click(x=None, y=None,
                button: str = "left", double: bool = False,
                normalized: bool = False) -> None:
    """在 (x, y) 点击鼠标。如省略坐标则在当前位置点击。

    normalized=True 时 x,y 为 0~1 归一化坐标。
    """
    if x is not None and y is not None:
        mouse_move(x, y, normalized=normalized)
        time.sleep(0.02)

    btn = button.lower()
    if btn == "right":
        down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    elif btn == "middle":
        down, up = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
    else:
        down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

    _mouse_event(down)
    time.sleep(0.02)
    _mouse_event(up)

    if double:
        time.sleep(0.05)
        _mouse_event(down)
        time.sleep(0.02)
        _mouse_event(up)


def mouse_scroll(direction: str = "down", amount: int = 3,
                 x=None, y=None, normalized: bool = False) -> None:
    """滚动鼠标滚轮。direction: up/down，amount: 滚动格数。

    normalized=True 时 x,y 为 0~1 归一化坐标。
    """
    if x is not None and y is not None:
        mouse_move(x, y, normalized=normalized)
        time.sleep(0.02)

    delta = WHEEL_DELTA * amount
    if direction.lower() == "up":
        _mouse_event(MOUSEEVENTF_WHEEL, delta)
    else:
        _mouse_event(MOUSEEVENTF_WHEEL, -delta)


def mouse_drag(x1, y1, x2, y2,
               duration: float = 0.3, normalized: bool = False) -> None:
    """从 (x1, y1) 拖拽到 (x2, y2)。

    normalized=True 时坐标为 0~1 归一化。
    """
    if normalized:
        x1, y1 = _norm_to_physical(float(x1), float(y1))
        x2, y2 = _norm_to_physical(float(x2), float(y2))
    mouse_move(x1, y1)
    time.sleep(0.05)
    _mouse_event(MOUSEEVENTF_LEFTDOWN)
    # 平滑移动
    steps = max(1, int(duration / 0.01))
    for i in range(1, steps + 1):
        t = i / steps
        cx = int(x1 + (x2 - x1) * t)
        cy = int(y1 + (y2 - y1) * t)
        mouse_move(cx, cy)
        time.sleep(duration / steps)
    time.sleep(0.05)
    _mouse_event(MOUSEEVENTF_LEFTUP)


def mouse_position() -> tuple[int, int]:
    """获取当前鼠标坐标。"""
    pt = w.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


# ═══════════════════════════════════════════════════════════════════
#  键盘
# ═══════════════════════════════════════════════════════════════════

def _keybd_event(vk: int, scan: int = 0, flags: int = 0) -> None:
    user32.keybd_event(vk, scan, flags, 0)


def key_press(key: str) -> bool:
    """按下并释放单个键。"""
    vk = _resolve_vk(key)
    if vk is None:
        return False
    _keybd_event(vk)
    time.sleep(0.02)
    _keybd_event(vk, flags=KEYEVENTF_KEYUP)
    return True


def key_hotkey(keys: list[str]) -> bool:
    """按下组合键，如 ["ctrl", "c"]。按顺序按下，逆序释放。"""
    vks: list[int] = []
    for k in keys:
        vk = _resolve_vk(k)
        if vk is None:
            return False
        vks.append(vk)
    if not vks:
        return False

    for vk in vks:
        _keybd_event(vk)
        time.sleep(0.02)
    time.sleep(0.05)
    for vk in reversed(vks):
        _keybd_event(vk, flags=KEYEVENTF_KEYUP)
        time.sleep(0.01)
    return True


def _send_input_unicode(text: str) -> None:
    """使用 SendInput + KEYEVENTF_UNICODE 直接发送 Unicode 字符。

    这是最可靠的中文输入方式：不依赖剪贴板，不依赖目标应用是否支持 Ctrl+V，
    直接模拟键盘输入 Unicode 码点。
    """
    inputs = []
    for ch in text:
        code = ord(ch)
        # 按下
        ki_down = _KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE)
        inp_down = _INPUT(type=INPUT_KEYBOARD)
        inp_down.u.ki = ki_down
        inputs.append(inp_down)
        # 释放
        ki_up = _KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
        inp_up = _INPUT(type=INPUT_KEYBOARD)
        inp_up.u.ki = ki_up
        inputs.append(inp_up)

    if not inputs:
        return
    n = len(inputs)
    arr = (_INPUT * n)(*inputs)
    user32.SendInput(n, arr, ctypes.sizeof(_INPUT))
    time.sleep(0.05)


def key_type(text: str, method: str = "auto") -> None:
    """输入文本。

    method:
      - 'auto'（默认）：非 ASCII 字符用 SendInput Unicode，ASCII 用 keybd_event
      - 'sendinput': 全部字符用 SendInput Unicode
      - 'clipboard': 通过剪贴板 + Ctrl+V 粘贴
    """
    if not text:
        return

    method = (method or "auto").lower()

    if method == "clipboard":
        _type_via_clipboard(text)
        return

    if method == "sendinput":
        _send_input_unicode(text)
        return

    # auto：ASCII 可打印字符用 keybd_event，其余用 SendInput Unicode
    if all(ord(c) < 128 and c.isprintable() for c in text):
        for ch in text:
            vk = VkKeyScanW(ch)
            vk_code = vk & 0xFF
            shift = (vk >> 8) & 1
            if shift:
                _keybd_event(0x10)  # Shift down
            _keybd_event(vk_code)
            time.sleep(0.005)
            _keybd_event(vk_code, flags=KEYEVENTF_KEYUP)
            if shift:
                _keybd_event(0x10, flags=KEYEVENTF_KEYUP)
            time.sleep(0.005)
    else:
        _send_input_unicode(text)


def _type_via_clipboard(text: str) -> None:
    """通过剪贴板粘贴文本（支持 Unicode）。保存并恢复原有剪贴板内容。"""
    old = clipboard_get()
    clipboard_set(text)
    time.sleep(0.05)
    key_hotkey(["ctrl", "v"])
    time.sleep(0.2)
    # 恢复
    if old is not None:
        clipboard_set(old)


# ═══════════════════════════════════════════════════════════════════
#  剪贴板
# ═══════════════════════════════════════════════════════════════════

def clipboard_get() -> str | None:
    """读取剪贴板文本。"""
    try:
        user32.OpenClipboard(0)
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            return None
        try:
            text = ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(h)
        return text
    except Exception:
        return None
    finally:
        try:
            user32.CloseClipboard()
        except Exception:
            pass


def clipboard_set(text: str) -> bool:
    """写入剪贴板文本。"""
    try:
        user32.OpenClipboard(0)
        user32.EmptyClipboard()
        data = text + "\0"
        buf = ctypes.create_unicode_buffer(data)
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data) * 2)
        if not h:
            return False
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            return False
        try:
            ctypes.memmove(ptr, buf, len(data) * 2)
        finally:
            kernel32.GlobalUnlock(h)
        user32.SetClipboardData(CF_UNICODETEXT, h)
        return True
    except Exception:
        return False
    finally:
        try:
            user32.CloseClipboard()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════
#  截图
# ═══════════════════════════════════════════════════════════════════

_SCREENSHOT_DIR = Path.home() / ".Aries" / "tmp" / "computer_screenshots"


def screenshot(
    monitor: int = 0,
    region: dict | None = None,
) -> dict[str, Any]:
    """截图。

    monitor: 0=所有显示器, 1=主显示器, 2+=副显示器
    region: {"x": int, "y": int, "width": int, "height": int} 指定区域
    返回: {"path": str, "width": int, "height": int, "image_base64": str}
    """
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = _SCREENSHOT_DIR / f"screenshot_{ts}.png"

    try:
        from PIL import ImageGrab, Image
        use_pil = True
    except ImportError:
        use_pil = False

    if use_pil:
        if region:
            bbox = (
                region["x"], region["y"],
                region["x"] + region["width"],
                region["y"] + region["height"],
            )
            img = ImageGrab.grab(bbox=bbox)
        elif monitor == 0:
            img = ImageGrab.grab(all_screens=True)
        else:
            # 单显示器：PIL 的 grab() 默认抓主屏
            # 多显示器需要手动计算 offset
            screens = _list_monitors()
            idx = min(monitor - 1, len(screens) - 1) if screens else 0
            if screens and idx >= 0:
                s = screens[idx]
                img = ImageGrab.grab(bbox=(s["x"], s["y"], s["x"] + s["width"], s["y"] + s["height"]))
            else:
                img = ImageGrab.grab()
        img.save(str(out_path))
        w_, h_ = img.size
    else:
        # 降级：PowerShell + System.Drawing
        result = _screenshot_powershell(str(out_path), monitor, region)
        if not result["success"]:
            return {"success": False, "error": result["error"], "output": result["error"]}
        w_, h_ = result["width"], result["height"]

    # 生成 base64 图片（不缩放，保持 1:1 像素对应，AI 看到的坐标 = 实际点击坐标）
    b64 = _image_to_base64(str(out_path))

    return {
        "success": True,
        "output": f"截图已保存: {out_path} ({w_}x{h_})。推荐用归一化坐标 (0~1) 点击：computer_mouse(action=\"click\", x=<0~1>, y=<0~1>, normalized=True)。也可用物理像素坐标。",
        "screenshot_path": str(out_path),
        "width": w_,
        "height": h_,
        "image_base64": b64,
    }


def _list_monitors() -> list[dict]:
    """获取所有显示器信息。"""
    monitors: list[dict] = []

    def _callback(hmon: int, hdc: int, rect: Any, data: int) -> int:
        r = rect.contents
        monitors.append({
            "x": r.left, "y": r.top,
            "width": r.right - r.left,
            "height": r.bottom - r.top,
            "handle": hmon,
        })
        return 1

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int, w.HMONITOR, w.HDC, ctypes.POINTER(w.RECT), ctypes.c_void_p
    )
    user32.EnumDisplayMonitors(0, 0, MONITORENUMPROC(_callback), 0)
    return monitors


def _image_to_base64(path: str, quality: int = 75) -> str:
    """将图片转为 JPEG base64，不缩放，保持 1:1 像素对应。

    AI 看到的图片坐标 = 实际屏幕坐标 = SetCursorPos 需要的坐标。
    用 JPEG quality=75 压缩文件大小，同时保持可辨识性。
    """
    try:
        from PIL import Image
        img = Image.open(path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""


def _screenshot_powershell(path: str, monitor: int, region: dict | None) -> dict:
    """降级截图：PowerShell Add-Type System.Drawing。"""
    try:
        if region:
            r = region
            ps_code = f'''
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap({r["width"]},{r["height"]})
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen({r["x"]},{r["y"]},0,0,$bmp.Size)
$bmp.Save("{path}")
$g.Dispose();$bmp.Dispose()
'''
        else:
            ps_code = f'''
Add-Type -AssemblyName System.Drawing
$screens = [System.Windows.Forms.Screen]::AllScreens
$top = ($screens | ForEach-Object {{ $_.Bounds.Top }} | Measure-Object -Minimum).Minimum
$left = ($screens | ForEach-Object {{ $_.Bounds.Left }} | Measure-Object -Minimum).Minimum
$w = ($screens | ForEach-Object {{ $_.Bounds.Right }} | Measure-Object -Maximum).Maximum - $left
$h = ($screens | ForEach-Object {{ $_.Bounds.Bottom }} | Measure-Object -Maximum).Maximum - $top
$bmp = New-Object System.Drawing.Bitmap($w,$h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($left,$top,0,0,$bmp.Size)
$bmp.Save("{path}")
$g.Dispose();$bmp.Dispose()
'''
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_code],
            capture_output=True, timeout=15, text=True,
        )
        from PIL import Image
        img = Image.open(path)
        return {"success": True, "width": img.width, "height": img.height}
    except Exception as e:
        return {"success": False, "error": f"PowerShell 截图失败: {e}"}


# ═══════════════════════════════════════════════════════════════════
#  窗口管理
# ═══════════════════════════════════════════════════════════════════

def _get_window_title(hwnd: int) -> str:
    """获取窗口标题。"""
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _get_window_pid(hwnd: int) -> int:
    """获取窗口对应的进程 ID。"""
    pid = w.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def window_list() -> list[dict]:
    """列出所有可见且有标题的窗口。"""
    results: list[dict] = []

    def _callback(hwnd: int, lparam: int) -> int:
        if not user32.IsWindowVisible(hwnd):
            return 1
        title = _get_window_title(hwnd)
        if not title:
            return 1
        results.append({
            "title": title,
            "hwnd": hwnd,
            "pid": _get_window_pid(hwnd),
        })
        return 1

    WNDENUMPROC = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user32.EnumWindows(WNDENUMPROC(_callback), 0)
    return results


def _find_window_by_title(title: str) -> int | None:
    """匹配窗口标题，返回 hwnd。

    匹配优先级：
    1. 精确匹配（不区分大小写）
    2. 标题以目标字符串开头
    3. 标题包含目标字符串
    """
    title_lower = title.lower().strip()
    if not title_lower:
        return None

    candidates: list[tuple[int, str, int]] = []  # (hwnd, title, score)

    def _callback(hwnd: int, lparam: int) -> int:
        if not user32.IsWindowVisible(hwnd):
            return 1
        wt = _get_window_title(hwnd)
        if not wt:
            return 1
        wt_lower = wt.lower()
        if wt_lower == title_lower:
            candidates.append((hwnd, wt, 0))  # 精确匹配，最高优先级
        elif wt_lower.startswith(title_lower):
            candidates.append((hwnd, wt, 1))
        elif title_lower in wt_lower:
            candidates.append((hwnd, wt, 2))
        return 1

    WNDENUMPROC = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user32.EnumWindows(WNDENUMPROC(_callback), 0)

    if not candidates:
        return None

    # 按优先级排序，同优先级选标题更短的
    candidates.sort(key=lambda x: (x[2], len(x[1])))
    return candidates[0][0]


def window_focus(title: str) -> dict:
    """将指定标题的窗口设为前台。"""
    hwnd = _find_window_by_title(title)
    if hwnd is None:
        return {"success": False, "error": f"未找到标题包含 '{title}' 的窗口"}

    # 恢复最小化的窗口
    user32.ShowWindow(hwnd, SW_RESTORE)

    # 先尝试 SetForegroundWindow
    ok = user32.SetForegroundWindow(hwnd)
    if not ok:
        # Windows 限制：如果调用线程没有输入焦点，SetForegroundWindow 会失败
        # 模拟按下并释放 ALT 键可以绕过这个限制
        user32.keybd_event(0x12, 0, 0, 0)
        time.sleep(0.01)
        user32.keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.01)
        ok = user32.SetForegroundWindow(hwnd)

    # 再尝试 BringWindowToTop 作为兜底
    user32.BringWindowToTop(hwnd)

    wt = _get_window_title(hwnd)
    fg_hwnd = user32.GetForegroundWindow()
    focused = (fg_hwnd == hwnd)
    return {
        "success": True,
        "output": f"已聚焦窗口: {wt} (hwnd={hwnd}, foreground={focused})",
        "focused": focused,
    }


def window_close(title: str) -> dict:
    """关闭指定标题的窗口。"""
    hwnd = _find_window_by_title(title)
    if hwnd is None:
        return {"success": False, "error": f"未找到标题包含 '{title}' 的窗口"}
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    return {"success": True, "output": f"已发送关闭消息到窗口: {_get_window_title(hwnd)}"}


def window_minimize(title: str) -> dict:
    hwnd = _find_window_by_title(title)
    if hwnd is None:
        return {"success": False, "error": f"未找到标题包含 '{title}' 的窗口"}
    user32.ShowWindow(hwnd, SW_MINIMIZE)
    return {"success": True, "output": f"已最小化窗口: {_get_window_title(hwnd)}"}


def window_maximize(title: str) -> dict:
    hwnd = _find_window_by_title(title)
    if hwnd is None:
        return {"success": False, "error": f"未找到标题包含 '{title}' 的窗口"}
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    return {"success": True, "output": f"已最大化窗口: {_get_window_title(hwnd)}"}


def window_restore(title: str) -> dict:
    hwnd = _find_window_by_title(title)
    if hwnd is None:
        return {"success": False, "error": f"未找到标题包含 '{title}' 的窗口"}
    user32.ShowWindow(hwnd, SW_RESTORE)
    return {"success": True, "output": f"已还原窗口: {_get_window_title(hwnd)}"}


def _get_app_paths_exe(name: str) -> str | None:
    """从 Windows 注册表 App Paths 查询可执行文件路径。"""
    try:
        import winreg
    except ImportError:
        return None

    candidates = [name]
    lower = name.lower()
    if not lower.endswith(".exe"):
        candidates.append(f"{lower}.exe")

    for hkey in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for exe_name in candidates:
            try:
                key_path = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\" + exe_name
                with winreg.OpenKey(hkey, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, None)
                    if value and os.path.isfile(value):
                        return value
            except FileNotFoundError:
                continue
            except Exception:
                continue
    return None


def _search_limited(root: Path, stem_name: str, max_depth: int = 3,
                    deadline: float | None = None) -> tuple[str | None, str | None]:
    """限制深度搜索 .lnk / .exe，找到精确匹配立即返回。

    返回 (exact_match, fuzzy_match)。
    """
    exact: str | None = None
    fuzzy: str | None = None
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            # 限制深度
            depth = dirpath.count(os.sep) - str(root).count(os.sep)
            if depth > max_depth:
                del dirnames[:]
                continue

            if deadline and time.time() > deadline:
                break

            for filename in filenames:
                if not filename.lower().endswith((".lnk", ".exe")):
                    continue
                file_stem = Path(filename).stem.lower()
                full = os.path.join(dirpath, filename)
                if file_stem == stem_name:
                    return full, fuzzy
                if fuzzy is None and (stem_name in file_stem or file_stem in stem_name):
                    fuzzy = full
    except PermissionError:
        pass
    except Exception:
        pass
    return exact, fuzzy


def _search_app(name: str, timeout: float = 2.0) -> str | None:
    """搜索应用路径。

    只搜索桌面（Path.home()/Desktop 和 Path.home()/桌面），不扫描其他目录。
    查找顺序：
    1. 完整路径
    2. PATH 环境变量
    3. Windows 注册表 App Paths（毫秒级）
    4. 桌面快捷方式 / 可执行文件（限制深度 2）
    未找到返回 None。
    """
    import shutil
    from pathlib import Path

    app = name.strip()
    lower_app = app.lower()
    stem_name = lower_app.removesuffix(".exe").strip()
    if not stem_name:
        return None

    # 1. 完整路径
    if os.path.isfile(app):
        return app

    # 2. PATH
    exe_in_path = shutil.which(app) or shutil.which(f"{stem_name}.exe")
    if exe_in_path:
        return exe_in_path

    # 3. 注册表 App Paths（毫秒级）
    reg_path = _get_app_paths_exe(app) or _get_app_paths_exe(stem_name)
    if reg_path:
        return reg_path

    # 4. 桌面（只搜索桌面，固定位置）
    home = Path.home()
    desktop_roots: list[Path] = [
        home / "Desktop",
        home / "桌面",
    ]

    deadline = time.time() + timeout
    for root in desktop_roots:
        exact, fuzzy = _search_limited(root, stem_name, max_depth=2, deadline=deadline)
        if exact:
            return exact

    for root in desktop_roots:
        _, fuzzy = _search_limited(root, stem_name, max_depth=2)
        if fuzzy:
            return fuzzy

    return None


def app_open(app: str, timeout: float = 6.0) -> dict:
    """启动应用程序，并等待窗口出现（最多 6 秒）。

    维护绝对截止时间，任何步骤超时都不会卡住。

    app 可以是：
    - 应用名（如 notepad, calc, explorer, 微信, 豆包）
    - 完整路径（如 C:\\Windows\\notepad.exe）
    - 带参数的命令（如 notepad file.txt）
    """
    app = app.strip()
    if not app:
        return {"success": False, "error": "app 参数为空"}

    absolute_deadline = time.time() + timeout
    existing_hwnds = {w["hwnd"] for w in window_list()}

    def _remaining() -> float:
        return max(0.0, absolute_deadline - time.time())

    def _wait_for_window(title_keyword: str, max_wait: float,
                         existing_hwnds: set[int] | None = None) -> dict:
        """等待包含 title_keyword 的新窗口出现。

        existing_hwnds: 启动前已存在的窗口 hwnd 集合，避免误匹配已有窗口。
        """
        wait_until = min(absolute_deadline, time.time() + max_wait)
        title_kw = title_keyword.lower()
        while time.time() < wait_until:
            windows = window_list()
            candidates = [
                w for w in windows
                if (existing_hwnds is None or w["hwnd"] not in existing_hwnds)
                and (
                    title_kw in w["title"].lower()
                    or w["title"].lower() in title_kw
                    or w["title"].lower().startswith(title_kw)
                )
            ]
            # 优先选标题开头匹配的
            matches = sorted(
                candidates,
                key=lambda w: (
                    0 if w["title"].lower().startswith(title_kw) else 1,
                    -len(w["title"]),
                ),
            )
            if matches:
                return {
                    "success": True,
                    "output": f"应用已启动并检测到窗口: {matches[0]['title']} (hwnd={matches[0]['hwnd']})",
                    "window": matches[0],
                }
            time.sleep(0.2)
        return {
            "success": True,
            "output": f"已启动应用: {title_keyword}（未在 {_remaining():.1f}s 内检测到窗口，可能仍在加载）",
        }

    # 1. 尝试 os.startfile（最快，处理 .lnk、注册应用名）
    try:
        os.startfile(app)  # type: ignore
        return _wait_for_window(app, _remaining(), existing_hwnds)
    except Exception:
        pass

    if _remaining() <= 0:
        return {"success": False, "error": "打开超时", "output": "os.startfile 阶段已超时"}

    # 2. 搜索桌面快捷方式（只搜索桌面，固定位置）
    target = _search_app(app, timeout=min(1.0, _remaining() - 0.5))
    if target:
        try:
            if target.lower().endswith(".lnk"):
                os.startfile(target)
            else:
                subprocess.Popen([target], shell=False)
            title_kw = Path(target).stem
            return _wait_for_window(title_kw, _remaining(), existing_hwnds)
        except Exception as e:
            return {"success": False, "error": f"找到应用但启动失败: {e}", "output": f"路径: {target}"}

    if _remaining() <= 0:
        return {"success": False, "error": "打开超时", "output": "搜索桌面阶段已超时"}

    # 3. 使用 Windows 搜索（Win 键 → 输入名称 → Enter）
    # 避免使用 cmd /c start（找不到应用时会弹出阻塞对话框）
    try:
        key_hotkey(["win"])
        time.sleep(0.5)
        key_type(app, method="sendinput")
        time.sleep(0.8)
        key_press("enter")
        return _wait_for_window(app, _remaining(), existing_hwnds)
    except Exception as e:
        return {"success": False, "error": f"Windows 搜索启动失败: {e}", "output": f"找不到应用: {app}，请提供完整路径"}


def get_foreground_window() -> dict:
    """获取当前前台窗口信息。"""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return {"title": "", "hwnd": 0, "pid": 0}
    return {
        "title": _get_window_title(hwnd),
        "hwnd": hwnd,
        "pid": _get_window_pid(hwnd),
    }


# ═══════════════════════════════════════════════════════════════════
#  ESC 热键监听 — 按下 ESC 强制中断 AI 执行
# ═══════════════════════════════════════════════════════════════════

import threading

VK_ESCAPE = 0x1B
_ESC_POLL_INTERVAL = 0.05  # 50ms 轮询

# 全局 ESC 监听状态
_esc_thread: threading.Thread | None = None
_esc_stop_flag = threading.Event()
_esc_callback = None
_esc_active = False  # 是否正在监听（computer-use 期间为 True）


def start_esc_listener(callback) -> None:
    """启动 ESC 热键监听。

    callback: ESC 按下时调用的函数（无参数）。
    通常传入 lambda: request_cancel(session_id) 来中断 AI 流。
    """
    global _esc_thread, _esc_stop_flag, _esc_callback, _esc_active

    # 如果已有监听在运行，只更新 callback
    if _esc_active:
        _esc_callback = callback
        return

    _esc_callback = callback
    _esc_stop_flag.clear()
    _esc_active = True

    def _poll_esc():
        """后台线程：轮询 ESC 键状态。"""
        was_pressed = False
        while not _esc_stop_flag.is_set():
            # GetAsyncKeyState 返回值最高位为 1 表示当前按下
            state = user32.GetAsyncKeyState(VK_ESCAPE)
            if state & 0x8000:
                if not was_pressed:
                    was_pressed = True
                    # 触发回调
                    cb = _esc_callback
                    if cb:
                        try:
                            cb()
                        except Exception:
                            pass
            else:
                was_pressed = False
            time.sleep(_ESC_POLL_INTERVAL)

    _esc_thread = threading.Thread(target=_poll_esc, daemon=True, name="esc-listener")
    _esc_thread.start()


def stop_esc_listener() -> None:
    """停止 ESC 热键监听。"""
    global _esc_thread, _esc_stop_flag, _esc_callback, _esc_active
    _esc_stop_flag.set()
    _esc_active = False
    _esc_callback = None
    if _esc_thread and _esc_thread.is_alive():
        _esc_thread.join(timeout=1.0)
    _esc_thread = None


def is_esc_listener_active() -> bool:
    """ESC 监听是否正在运行。"""
    return _esc_active
