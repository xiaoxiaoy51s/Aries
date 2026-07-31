"""QQ / 微信 / 飞书 Bot 生命周期管理（适配 cloud 后端）。

配置路径：~/.Aries/{user_email}/config.json（用户级）。
云端多租户：每个启用了平台的用户各自对应一个 bot 子进程。
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

_log = logging.getLogger(__name__)

ARIESCLAW_HOME = Path.home() / ".Aries"
_BACKEND_DIR = Path(__file__).resolve().parents[2]

# 子进程内：当前 bot 用户邮箱（每个 bot_process 进程各自一份）
_bot_user_email: str | None = None
_config_lock = threading.Lock()

# 主进程：email -> Popen
_bot_processes: dict[str, subprocess.Popen] = {}
_process_lock = threading.Lock()


def _bot_config_path(email: str | None = None) -> Path:
    """返回 ~/.Aries/{email}/config.json"""
    e = email or _bot_user_email
    if not e:
        return ARIESCLAW_HOME / "bot_config.json"  # fallback
    return ARIESCLAW_HOME / e / "config.json"


def _load_bot_config(email: str | None = None) -> dict:
    path = _bot_config_path(email)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def persist_recipient(platform: str, **fields) -> None:
    """把收件人字段持久化到 ~/.Aries/{email}/config.json（读-改-写，线程安全）。

    使用 _bot_user_email（由 start_all_bots 设置）确定路径。
    """
    email = _bot_user_email
    if not email:
        _log.warning("[BotManager] persist_recipient 跳过：未设置 bot 用户邮箱")
        return
    cleaned = {k: str(v).strip() for k, v in fields.items() if v is not None}
    if not cleaned:
        return
    with _config_lock:
        config = _load_bot_config(email)
        pconf = config.setdefault(platform, {})
        changed = False
        for k, v in cleaned.items():
            if v and pconf.get(k) != v:
                pconf[k] = v
                changed = True
        if not changed:
            return
        try:
            path = _bot_config_path(email)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            _log.debug("[BotManager] 已持久化 %s 收件人字段: %s", platform, list(cleaned.keys()))
        except Exception as e:
            _log.warning("[BotManager] 持久化 %s 收件人字段失败: %s", platform, e)


def is_platform_enabled(platform: str, email: str | None = None) -> bool:
    config = _load_bot_config(email)
    return config.get(platform, {}).get("enabled", False)


PLATFORM_NAMES = {"qq": "QQ", "feishu": "飞书", "wechat": "微信"}


def is_platform_bound(platform: str, email: str | None = None) -> bool:
    """检查平台是否已绑定且启用（有凭据且 enabled=true）。"""
    config = _load_bot_config(email)
    pconf = config.get(platform, {})
    if not pconf.get("enabled", False):
        return False
    if platform == "feishu":
        return bool(
            (pconf.get("app_id") or "").strip()
            and (pconf.get("app_secret") or "").strip()
        )
    if platform == "qq":
        return bool(
            (pconf.get("app_id") or "").strip()
            and (pconf.get("app_secret") or "").strip()
        )
    if platform == "wechat":
        return bool((pconf.get("bot_token") or "").strip())
    return False


def platform_unbound_message(platform: str) -> str:
    name = PLATFORM_NAMES.get(platform, platform)
    return f"用户暂未绑定{name}平台，无法发送。请停止发送并告知用户前往设置中绑定{name}。"


def get_bot_user_email() -> str | None:
    """返回当前进程内 bot 绑定用户邮箱（bot 子进程内有效）。"""
    return _bot_user_email


def _any_platform_enabled(email: str) -> bool:
    return any(is_platform_enabled(p, email) for p in ("qq", "wechat", "feishu"))


def _kill_process_tree(pid: int) -> None:
    """强制结束进程及其全部子进程（Windows 用 taskkill /T）。"""
    if pid <= 0:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        try:
            os.killpg(os.getpgid(pid), 9)
        except Exception:
            try:
                os.kill(pid, 9)
            except OSError:
                pass


def _kill_stray_bot_processes(*, keep_pids: set[int] | None = None) -> None:
    """清理残留 bot_process 孤儿；keep_pids 内的进程保留。"""
    keep = keep_pids or set()
    me = os.getpid()
    if sys.platform != "win32":
        # 非 Windows：逐个匹配更安全，避免误杀 keep 中的进程
        try:
            result = subprocess.run(
                ["pgrep", "-f", "app.services.bot_process"],
                capture_output=True, text=True, check=False,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    pid = int(line)
                    if pid > 0 and pid != me and pid not in keep:
                        _log.info("[BotManager] 清理残留 bot 进程 pid=%s", pid)
                        _kill_process_tree(pid)
        except Exception as e:
            _log.warning("[BotManager] 清理残留 bot 进程失败: %s", e)
        return

    ps_cmd = (
        "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
        "Where-Object { $_.CommandLine -match 'app\\.services\\.bot_process' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, check=False, timeout=15,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                pid = int(line)
                if pid > 0 and pid != me and pid not in keep:
                    _log.info("[BotManager] 清理残留 bot 进程 pid=%s", pid)
                    _kill_process_tree(pid)
    except Exception as e:
        _log.warning("[BotManager] 清理残留 bot 进程失败: %s", e)


def _stop_one_process(email: str) -> None:
    """停止指定用户的 bot 子进程（不影响其他用户）。"""
    with _process_lock:
        proc = _bot_processes.pop(email, None)
    if proc is None:
        return
    if proc.poll() is None:
        _log.info("[BotManager] 结束 bot 进程 user=%s pid=%s", email, proc.pid)
        _kill_process_tree(proc.pid)
        try:
            proc.wait(timeout=3)
        except Exception:
            pass


def stop_bot_process(email: str | None = None) -> None:
    """终止 bot 子进程。

    - email 指定：只停该用户
    - email 为空：停掉全部托管进程，并清理孤儿
    """
    if email:
        _stop_one_process(email)
        return

    with _process_lock:
        items = list(_bot_processes.items())
        _bot_processes.clear()
    for user_email, proc in items:
        if proc.poll() is None:
            _log.info("[BotManager] 结束 bot 进程 user=%s pid=%s", user_email, proc.pid)
            _kill_process_tree(proc.pid)
            try:
                proc.wait(timeout=3)
            except Exception:
                pass
    _kill_stray_bot_processes()


def warn_duplicate_platform_credentials(emails: list[str]) -> None:
    """检测多用户共用同一 QQ/飞书 app_id 或微信 token（会导致重复回复）。"""
    seen: dict[tuple[str, str], list[str]] = {}
    for email in emails:
        config = _load_bot_config(email)
        for plat, key in (
            ("qq", "app_id"),
            ("feishu", "app_id"),
            ("wechat", "bot_token"),
        ):
            pconf = config.get(plat) or {}
            if not pconf.get("enabled"):
                continue
            cred = (pconf.get(key) or "").strip()
            if not cred:
                continue
            seen.setdefault((plat, cred), []).append(email)
    for (plat, _cred), users in seen.items():
        if len(users) > 1:
            _log.warning(
                "[BotManager] 多个用户共用同一%s凭据（%s），"
                "平台会重复推送/回复。每位用户应使用自己的应用凭据。",
                PLATFORM_NAMES.get(plat, plat),
                users,
            )


def spawn_bot_process(email: str) -> bool:
    """为指定用户启动独立 bot 子进程（不影响其他用户的进程）。"""
    if not email:
        return False
    if not _any_platform_enabled(email):
        _stop_one_process(email)
        return False

    _stop_one_process(email)

    cmd = [sys.executable, "-m", "app.services.bot_process", email]
    popen_kwargs: dict = {"cwd": str(_BACKEND_DIR)}
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    with _process_lock:
        _log.info("[BotManager] 启动 bot 子进程 user=%s", email)
        proc = subprocess.Popen(cmd, **popen_kwargs)
        _bot_processes[email] = proc
    return True


def spawn_all_bot_processes(emails: list[str]) -> list[str]:
    """为多个用户分别启动 bot 子进程。返回成功启动的邮箱列表。"""
    # 启动前清一次孤儿，但不要在逐个 spawn 时互杀
    stop_bot_process()
    warn_duplicate_platform_credentials(emails)
    started: list[str] = []
    for email in emails:
        if spawn_bot_process(email):
            started.append(email)
    return started


def restart_bot_process(email: str) -> None:
    spawn_bot_process(email)


def restart_platform(platform: str, email: str) -> None:
    """配置变更后重启该用户的 bot 子进程。"""
    _log.info("[BotManager] 重启平台 %s user=%s", platform, email)
    restart_bot_process(email)


def stop_platform(platform: str, email: str | None = None) -> None:
    """停止平台：若该用户无任何启用平台则终止其子进程，否则重启子进程。"""
    user_email = email or _bot_user_email
    if not user_email:
        return
    if _any_platform_enabled(user_email):
        restart_bot_process(user_email)
    else:
        _stop_one_process(user_email)


def start_all_bots(email: str):
    """在 bot 子进程内启动已启用平台的 bot 连接。

    Args:
        email: 用户的邮箱，用于读取 ~/.Aries/{email}/config.json 中的 bot 配置。
    """
    global _bot_user_email
    _bot_user_email = email

    started = {"qq": 0, "wechat": 0, "feishu": 0}
    if is_platform_enabled("qq", email):
        try:
            from app.services.qq_bot import start_qq_bot
            if start_qq_bot(email):
                started["qq"] += 1
        except Exception as e:
            _log.warning("[BotManager] QQ 启动失败: %s", e)
    if is_platform_enabled("wechat", email):
        try:
            from app.services.wechat_bot import start_wechat_bot
            if start_wechat_bot(email):
                started["wechat"] += 1
        except Exception as e:
            _log.warning("[BotManager] 微信启动失败: %s", e)
    if is_platform_enabled("feishu", email):
        try:
            from app.services.feishu_bot import start_feishu_bot
            if start_feishu_bot(email):
                started["feishu"] += 1
        except Exception as e:
            _log.warning("[BotManager] 飞书启动失败: %s", e)
    _log.info("[BotManager] 启动完成 (%s): %s", email, started)
    return started


def stop_all_bots():
    """标记关闭状态，然后停止所有机器人（bot 子进程内调用）。"""
    from app.services.platform_chat import mark_shutting_down
    mark_shutting_down()

    from app.services.feishu_bot import stop_feishu_bot
    from app.services.qq_bot import stop_qq_bot
    from app.services.wechat_bot import stop_wechat_bot

    for name, stop_fn in [("QQ", stop_qq_bot), ("微信", stop_wechat_bot), ("飞书", stop_feishu_bot)]:
        try:
            stop_fn()
            _log.info("[BotManager] %s 已停止", name)
        except Exception as e:
            _log.warning("[BotManager] 停止 %s 异常: %s", name, e)
