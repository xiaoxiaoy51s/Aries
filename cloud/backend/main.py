"""Cloud 后端入口。启动前清理占用 8000 的旧进程，然后在本端口启动。"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import uvicorn

PORT = 8000


def kill_port(port: int) -> None:
    """结束占用指定端口的进程树（Windows: taskkill /F /T）。"""
    me = os.getpid()
    pids: set[int] = set()

    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as e:
        print(f"[startup] netstat 失败: {e}")
        return

    for line in result.stdout.splitlines():
        line = line.strip()
        if "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local = parts[1]
        if local.rsplit(":", 1)[-1] != str(port):
            continue
        pid_str = parts[-1]
        if pid_str.isdigit():
            pid = int(pid_str)
            if pid > 0 and pid != me:
                pids.add(pid)

    for pid in sorted(pids):
        if sys.platform == "win32":
            r = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                text=True,
                check=False,
            )
            if r.returncode == 0:
                print(f"[startup] 已结束占用 {port} 的进程树 PID={pid}")
            else:
                print(f"[startup] 结束 PID={pid} 失败（可能已退出）")
        else:
            try:
                os.kill(pid, signal.SIGKILL)
                print(f"[startup] 已结束占用 {port} 的进程 PID={pid}")
            except OSError:
                pass

    # 等端口释放
    for _ in range(15):
        still = False
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in result.stdout.splitlines():
                if "LISTENING" not in line:
                    continue
                parts = line.split()
                if len(parts) >= 5 and parts[1].rsplit(":", 1)[-1] == str(port):
                    still = True
                    break
        except Exception:
            break
        if not still:
            return
        time.sleep(0.1)


if __name__ == "__main__":
    kill_port(PORT)
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=False)
