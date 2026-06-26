#!/usr/bin/env python3
"""
批量填入脚本 — 传入 ref:内容 列表，逐个填入输入框。

用法:
  python batch_fill.py e45:答案1 e60:答案2
  python batch_fill.py e45:答案1,e60:答案2
  python batch_fill.py e45:"hello world" --delay 200
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

SESSION = os.environ.get("ARIES_PLAYWRIGHT_SESSION", "aries")
DEFAULT_DELAY_MS = 300


def _run(action: str, *args: str, session: str) -> tuple[int, str, str]:
    quoted = []
    for a in args:
        a = str(a)
        if any(c in a for c in ' &|<>^()"'):
            quoted.append(json.dumps(a))
        else:
            quoted.append(a)
    cmd = f"playwright-cli -s={session} {action} {' '.join(quoted)}"
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, shell=True)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def _fill(ref: str, value: str, session: str) -> tuple[int, str, str]:
    # 先点击聚焦，让 document.activeElement 指向目标输入框
    code, out, err = _run("click", ref, session=session)
    if code != 0:
        return code, out, err
    # ensure_ascii=False 保留中文原始字符，避免被转义为 \uXXXX
    js_value = json.dumps(value, ensure_ascii=False)
    # 自动判断元素类型：INPUT/TEXTAREA 用 value；富文本编辑器(contenteditable/body)用 innerHTML
    js = (
        f"(() => {{ "
        f"const el = document.activeElement; "
        f"if (!el) return 'no active element'; "
        f"const tag = el.tagName; "
        f"if (tag === 'INPUT' || tag === 'TEXTAREA') {{ "
        f"  el.value = {js_value}; "
        f"  el.dispatchEvent(new Event('input', {{ bubbles: true }})); "
        f"  el.dispatchEvent(new Event('change', {{ bubbles: true }})); "
        f"  return 'ok'; "
        f"}} "
        f"if (el.isContentEditable || tag === 'BODY') {{ "
        f"  el.innerHTML = '<p>' + {js_value} + '</p>'; "
        f"  el.dispatchEvent(new Event('input', {{ bubbles: true }})); "
        f"  return 'ok'; "
        f"}} "
        f"return 'unsupported element: ' + tag; "
        f"}})()"
    )
    return _run("eval", js, session=session)


def main() -> int:
    parser = argparse.ArgumentParser(description="批量填入 playwright 输入框")
    parser.add_argument("items", nargs="+", help="ref:内容 列表，如 e45:答案1 e60:答案2 或 e45:答案1,e60:答案2")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY_MS, help=f"每次填入间隔毫秒 (默认 {DEFAULT_DELAY_MS})")
    parser.add_argument("--session", default=SESSION, help=f"playwright 会话名 (默认 {SESSION})")
    args = parser.parse_args()

    # 支持逗号分隔
    items: list[str] = []
    for item in args.items:
        for part in item.split(","):
            part = part.strip()
            if part:
                items.append(part)

    parsed: list[tuple[str, str]] = []
    for item in items:
        if ":" not in item:
            print(f"错误: 格式必须是 ref:内容，但得到: {item}", file=sys.stderr)
            return 1
        ref, value = item.split(":", 1)
        ref = ref.strip()
        value = value.strip()
        if not ref:
            print(f"错误: ref 不能为空: {item}", file=sys.stderr)
            return 1
        parsed.append((ref, value))

    if not parsed:
        print("错误: 未提供任何填入项", file=sys.stderr)
        return 1

    total = len(parsed)
    success = 0
    failed: list[str] = []

    for i, (ref, value) in enumerate(parsed, 1):
        display = value if len(value) <= 30 else value[:27] + "..."
        print(f"[{i}/{total}] 填入 {ref}: {display}...", end=" ", flush=True)
        code, out, err = _fill(ref, value, session=args.session)
        if code == 0:
            print("OK")
            success += 1
        else:
            print(f"失败: {err or out}")
            failed.append(f"{ref}:{value}")
        if i < total and args.delay > 0:
            time.sleep(args.delay / 1000)

    print(f"\n完成: {success}/{total} 成功")
    if failed:
        print(f"失败: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
