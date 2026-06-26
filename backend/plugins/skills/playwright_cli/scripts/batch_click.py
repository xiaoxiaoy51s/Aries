#!/usr/bin/env python3
"""
批量点击脚本 — 传入 ref 列表，逐个点击。

用法:
  python batch_click.py e26 e45 e76
  python batch_click.py e26,e45,e76
  python batch_click.py e26 e45 e76 --delay 500
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
import os

SESSION = os.environ.get("ARIES_PLAYWRIGHT_SESSION", "aries")
DEFAULT_DELAY_MS = 300


def _run_click(ref: str, session: str) -> tuple[int, str, str]:
    cmd = f"playwright-cli -s={session} click {ref}"
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, shell=True)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="批量点击 playwright 元素")
    parser.add_argument("refs", nargs="+", help="要点击的 ref 列表，如 e26 e45 e76 或 e26,e45,e76")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY_MS, help=f"每次点击间隔毫秒 (默认 {DEFAULT_DELAY_MS})")
    parser.add_argument("--session", default=SESSION, help=f"playwright 会话名 (默认 {SESSION})")
    args = parser.parse_args()

    # 支持逗号分隔
    refs: list[str] = []
    for r in args.refs:
        for part in r.split(","):
            part = part.strip()
            if part:
                refs.append(part)

    if not refs:
        print("错误: 未提供任何 ref", file=sys.stderr)
        return 1

    total = len(refs)
    success = 0
    failed: list[str] = []

    for i, ref in enumerate(refs, 1):
        print(f"[{i}/{total}] 点击 {ref}...", end=" ", flush=True)
        code, out, err = _run_click(ref, args.session)
        if code == 0:
            print("OK")
            success += 1
        else:
            print(f"失败: {err or out}")
            failed.append(ref)
        if i < total and args.delay > 0:
            time.sleep(args.delay / 1000)

    print(f"\n完成: {success}/{total} 成功")
    if failed:
        print(f"失败: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
