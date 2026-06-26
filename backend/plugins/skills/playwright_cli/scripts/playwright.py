#!/usr/bin/env python3
"""
Playwright 浏览器自动化脚本 — 独立可运行，不依赖 MIMOClaw。

自动管理会话 aries + profile ~/.Aries/browser_profile，复用登录态。

用法:
  python playwright.py open "https://example.com" --headed
  python playwright.py snapshot
  python playwright.py click e26
  python playwright.py eval "document.title"
  python playwright.py scrape --selector ".content"
  python playwright.py screenshot --output shot.png
  python playwright.py pdf --output page.pdf
  python playwright.py dismiss-dialog
  python playwright.py close
  python playwright.py status
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# --- 配置 ---
DEFAULT_SESSION = os.environ.get("ARIES_PLAYWRIGHT_SESSION", "aries")
_session_name = DEFAULT_SESSION
PROFILE_DIR = Path(os.environ.get("PLAYWRIGHT_PROFILE_DIR", str(Path.home() / ".Aries" / "browser_profile")))
TEMP_DIR = Path.home() / ".Aries" / "tmp"
OUTPUT_DIR = TEMP_DIR
TIMEOUT_DEFAULT = 60


def _win_quote(value: str) -> str:
    if re.search(r'[ &|<>^()]', value):
        return f'"{value}"'
    return value


def _run_cli(args: list[str], *, session: str | None = None, timeout: int = TIMEOUT_DEFAULT) -> tuple[int, str, str]:
    if session is None:
        session = _session_name
    quoted = [_win_quote(str(a)) for a in args]
    prefix = f"-s={session} " if session else ""
    cmd = f"playwright-cli {prefix}{' '.join(quoted)}"
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        cmd,
        cwd=str(TEMP_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=True,
    )
    return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()


def _list_sessions() -> dict[str, dict[str, str]]:
    code, out, _ = _run_cli(["list"], session=None, timeout=15)
    if code != 0:
        return {}
    sessions: dict[str, dict[str, str]] = {}
    current: str | None = None
    for line in out.splitlines():
        header = re.match(r"^\s*-\s+([^:]+):\s*$", line.strip())
        if header:
            current = header.group(1).strip()
            sessions[current] = {}
            continue
        if current and ":" in line:
            key, value = line.strip().split(":", 1)
            key = key.strip()
            if key.startswith("- "):
                key = key[2:].strip()
            sessions[current][key] = value.strip()
    return sessions


def _resolve_active_session() -> str | None:
    sessions = _list_sessions()
    if _session_name in sessions and sessions[_session_name].get("status") == "open":
        return _session_name
    target = str(PROFILE_DIR.resolve()).lower()
    for name, info in sessions.items():
        if info.get("status") != "open":
            continue
        if info.get("user-data-dir", "").lower() == target:
            return name
    return None


def _close_conflicting() -> None:
    target = str(PROFILE_DIR.resolve()).lower()
    for name, info in _list_sessions().items():
        if name == _session_name:
            continue
        if info.get("status") != "open":
            continue
        if info.get("user-data-dir", "").lower() == target:
            _run_cli(["close"], session=name, timeout=30)


def _get_current_url(session: str) -> str | None:
    code, out, _ = _run_cli(["--raw", "eval", "location.href"], session=session, timeout=20)
    return out.strip() or None if code == 0 else None


def _urls_equivalent(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    pa, pb = urlparse(a), urlparse(b)
    return (pa.netloc.lower() == pb.netloc.lower() and
            pa.path.rstrip("/") == pb.path.rstrip("/") and
            pa.query == pb.query)


def _dismiss_dialogs(session: str) -> bool:
    dismissed = False
    for _ in range(3):
        code, out, err = _run_cli(["dialog-dismiss"], session=session, timeout=8)
        blob = f"{out}\n{err}".lower()
        if code == 0 and "no dialog" not in blob and "there is no" not in blob:
            dismissed = True
            continue
        code2, out2, err2 = _run_cli(["dialog-accept"], session=session, timeout=8)
        blob2 = f"{out2}\n{err2}".lower()
        if code2 == 0 and "no dialog" not in blob2 and "there is no" not in blob2:
            dismissed = True
            continue
        break
    return dismissed


def _is_modal_error(text: str) -> bool:
    lowered = (text or "").lower()
    return "modal state" in lowered or ("browser_evaluate" in lowered and "dialog" in lowered)


def _run_page_cmd(args: list[str], *, session: str, timeout: int = 30) -> tuple[int, str, str]:
    _dismiss_dialogs(session)
    code, out, err = _run_cli(args, session=session, timeout=timeout)
    if code != 0 and _is_modal_error(f"{out}\n{err}"):
        _dismiss_dialogs(session)
        code, out, err = _run_cli(args, session=session, timeout=timeout)
    return code, out, err


def _normalize_js(js: str) -> str:
    code = (js or "").strip()
    if not code:
        return code
    if code.startswith("(") or code.startswith("function") or "=>" in code:
        return code
    if re.match(r"^\s*(var|let|const|for|while|if|try|switch)\b", code) or ";" in code:
        body = code
        if "return" not in code and ";" in code:
            parts = [p.strip() for p in code.split(";") if p.strip()]
            if parts and not parts[-1].startswith("return"):
                parts[-1] = f"return ({parts[-1]})"
                body = "; ".join(parts)
        return f"(() => {{ {body} }})()"
    return code


def _ensure_browser(url: str | None, *, headed: bool, reuse: bool = True, navigate: bool = True) -> tuple[int, str, str | None, str]:
    active = _resolve_active_session()
    target_url = (url or "").strip()

    if reuse and active:
        if not navigate or not target_url:
            return 0, "", None, active
        current = _get_current_url(active)
        if current and _urls_equivalent(target_url, current):
            return 0, "", current, active
        code, out, err = _run_cli(["goto", target_url], session=active, timeout=90)
        return code, out, None, active

    if not target_url:
        return 1, "", "没有打开的浏览器会话，且未提供 url", _session_name

    if active:
        _run_cli(["close"], session=active, timeout=30)

    # 先杀掉所有 daemon 进程，确保浏览器完全退出
    _run_cli(["kill-all"], session=None, timeout=15)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    _close_conflicting()
    args = ["open", target_url, "--persistent", "--profile", str(PROFILE_DIR)]
    if headed:
        args.append("--headed")
    code, out, err = _run_cli(args, session=_session_name, timeout=90)
    return code, out, None, _session_name


def _prepare(url: str | None, *, wait_ms: int, headless: bool, reuse: bool, navigate: bool) -> tuple[int, str, str | None, str]:
    code, _, err, session = _ensure_browser(url, headed=not headless, reuse=reuse, navigate=navigate)
    if code != 0:
        return code, err or "打开/导航页面失败", None, session
    if wait_ms > 0:
        time.sleep(wait_ms / 1000)
    if session and _resolve_active_session():
        _dismiss_dialogs(session)
    current = _get_current_url(session) if session else None
    return 0, "", current, session


# --- 命令处理 ---

def cmd_open(args):
    headed = not args.headless
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    _close_conflicting()
    cli_args = ["open", args.url, "--persistent", "--profile", str(PROFILE_DIR)]
    if headed:
        cli_args.append("--headed")
    code, out, err = _run_cli(cli_args, session=_session_name, timeout=90)
    if code != 0:
        print(f"打开失败: {err or out}", file=sys.stderr)
        return 1
    if args.wait_ms > 0:
        time.sleep(args.wait_ms / 1000)
    print(f"已打开: {args.url}")
    return 0


def cmd_snapshot(args):
    code, err, current, session = _prepare(None, wait_ms=args.wait_ms, headless=True, reuse=True, navigate=False)
    if code != 0:
        print(f"错误: {err}", file=sys.stderr)
        return 1
    code, out, err = _run_page_cmd(["--raw", "snapshot"], session=session, timeout=30)
    if code != 0:
        print(f"快照失败: {err}", file=sys.stderr)
        return 1
    print(out or "(页面无元素快照)")
    return 0


def cmd_click(args):
    if not args.target:
        print("错误: 需要指定 target (ref 或 CSS 选择器)", file=sys.stderr)
        return 1
    code, err, _, session = _prepare(None, wait_ms=args.wait_ms, headless=not args.headed, reuse=True, navigate=False)
    if code != 0:
        print(f"错误: {err}", file=sys.stderr)
        return 1
    code, out, err = _run_page_cmd(["click", args.target], session=session, timeout=30)
    if code != 0:
        print(f"点击失败: {err or out}", file=sys.stderr)
        return 1
    print(out or f"已点击: {args.target}")
    return 0


def cmd_eval(args):
    if not args.js_code:
        print("错误: 需要指定 js_code", file=sys.stderr)
        return 1
    code, err, _, session = _prepare(None, wait_ms=args.wait_ms, headless=True, reuse=True, navigate=False)
    if code != 0:
        print(f"错误: {err}", file=sys.stderr)
        return 1
    normalized = _normalize_js(args.js_code)
    code, out, err = _run_page_cmd(["--raw", "eval", normalized], session=session, timeout=30)
    if code != 0:
        if _is_modal_error(f"{out}\n{err}"):
            print(f"JS 执行失败(页面有弹窗阻塞): {err or out}\n请先运行: python playwright.py dismiss-dialog", file=sys.stderr)
        else:
            print(f"JS 执行失败: {err or out}", file=sys.stderr)
        return 1
    print(out or "(JS 执行无返回值)")
    return 0


def cmd_scrape(args):
    code, err, current, session = _prepare(None, wait_ms=args.wait_ms, headless=True, reuse=True, navigate=False)
    if code != 0:
        print(f"错误: {err}", file=sys.stderr)
        return 1
    if args.selector:
        js = f"(() => {{ const el = document.querySelector({json.dumps(args.selector)}); return el ? el.innerText : ''; }})()"
    else:
        js = "document.body.innerText"
    code, out, err = _run_page_cmd(["--raw", "eval", js], session=session, timeout=30)
    if code != 0:
        print(f"提取失败: {err}", file=sys.stderr)
        return 1
    print(out or "(页面内容为空)")
    return 0


def cmd_screenshot(args):
    code, err, _, session = _prepare(None, wait_ms=args.wait_ms, headless=True, reuse=True, navigate=False)
    if code != 0:
        print(f"错误: {err}", file=sys.stderr)
        return 1
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = str(OUTPUT_DIR / f"screenshot_{ts}.png")
    cli_args = ["screenshot"]
    if args.selector:
        cli_args.append(args.selector)
    cli_args += ["--filename", filepath]
    code, _, err = _run_cli(cli_args, session=session, timeout=30)
    if code != 0:
        print(f"截图失败: {err}", file=sys.stderr)
        return 1
    print(f"截图已保存: {filepath}")
    return 0


def cmd_pdf(args):
    code, err, _, session = _prepare(None, wait_ms=args.wait_ms, headless=True, reuse=True, navigate=False)
    if code != 0:
        print(f"错误: {err}", file=sys.stderr)
        return 1
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = str(OUTPUT_DIR / f"page_{ts}.pdf")
    code, _, err = _run_cli(["pdf", "--filename", filepath], session=session, timeout=60)
    if code != 0:
        print(f"PDF 导出失败: {err}", file=sys.stderr)
        return 1
    print(f"PDF 已保存: {filepath}")
    return 0


def cmd_dismiss_dialog(args):
    active = _resolve_active_session()
    if not active:
        print("没有打开的浏览器会话")
        return 1
    changed = _dismiss_dialogs(active)
    print("已尝试关闭阻塞对话框" if changed else "当前没有需要关闭的弹窗")
    return 0


def cmd_close(args):
    active = _resolve_active_session()
    if not active:
        print("当前没有运行中的浏览器会话")
        return 0
    code, out, err = _run_cli(["close"], session=active, timeout=30)
    if code != 0:
        print(f"关闭失败: {err or out}", file=sys.stderr)
        return 1
    print(f"已关闭浏览器会话 {active}。登录态保存在 profile 目录。")
    return 0


def cmd_status(args):
    sessions = _list_sessions()
    if not sessions:
        print("没有浏览器会话")
        return 0
    active = _resolve_active_session()
    for name, info in sessions.items():
        status = info.get("status", "unknown")
        marker = " (active)" if name == active else ""
        print(f"  {name}: {status}{marker}")
        if info.get("user-data-dir"):
            print(f"    profile: {info['user-data-dir']}")
    print(f"\nProfile 目录: {PROFILE_DIR}")
    print(f"Profile 存在: {'是' if PROFILE_DIR.exists() else '否'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Playwright 浏览器自动化脚本")
    parser.add_argument("--session", default=DEFAULT_SESSION, help=f"会话名 (默认: {DEFAULT_SESSION})")
    sub = parser.add_subparsers(dest="command", required=True)

    # open
    p_open = sub.add_parser("open", help="打开浏览器并导航到 URL")
    p_open.add_argument("url", help="目标 URL")
    p_open.add_argument("--headless", action="store_true", help="无头模式（默认 headed）")
    p_open.add_argument("--wait-ms", type=int, default=5000, help="等待毫秒 (默认 5000)")

    # snapshot
    p_snap = sub.add_parser("snapshot", help="获取页面 DOM 快照（含元素 ref）")
    p_snap.add_argument("--wait-ms", type=int, default=500, help="等待毫秒")

    # click
    p_click = sub.add_parser("click", help="点击元素")
    p_click.add_argument("target", help="snapshot 中的 ref (如 e26) 或 CSS 选择器")
    p_click.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    p_click.add_argument("--wait-ms", type=int, default=300, help="等待毫秒")

    # eval
    p_eval = sub.add_parser("eval", help="执行 JavaScript")
    p_eval.add_argument("js_code", help="JS 表达式或 () => { ... }")
    p_eval.add_argument("--wait-ms", type=int, default=0, help="等待毫秒")

    # scrape
    p_scrape = sub.add_parser("scrape", help="提取页面文本")
    p_scrape.add_argument("--selector", help="CSS 选择器（默认提取 body）")
    p_scrape.add_argument("--wait-ms", type=int, default=0, help="等待毫秒")

    # screenshot
    p_shot = sub.add_parser("screenshot", help="截图")
    p_shot.add_argument("--selector", help="截取指定元素")
    p_shot.add_argument("--wait-ms", type=int, default=0, help="等待毫秒")

    # pdf
    p_pdf = sub.add_parser("pdf", help="导出 PDF")
    p_pdf.add_argument("--wait-ms", type=int, default=0, help="等待毫秒")

    # dismiss-dialog
    sub.add_parser("dismiss-dialog", help="关闭页面弹窗")

    # close
    sub.add_parser("close", help="关闭浏览器")

    # status
    sub.add_parser("status", help="查看会话状态")

    args = parser.parse_args()

    global _session_name
    _session_name = args.session

    handlers = {
        "open": cmd_open,
        "snapshot": cmd_snapshot,
        "click": cmd_click,
        "eval": cmd_eval,
        "scrape": cmd_scrape,
        "screenshot": cmd_screenshot,
        "pdf": cmd_pdf,
        "dismiss-dialog": cmd_dismiss_dialog,
        "close": cmd_close,
        "status": cmd_status,
    }
    handler = handlers.get(args.command)
    if not handler:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
