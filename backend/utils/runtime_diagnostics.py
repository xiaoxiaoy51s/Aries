"""运行时诊断：观测随时间增长的资源，定位"用久了变卡"问题。

用法：
- GET /debug/health 随时查看当前快照
- 后台每 60s 打印一行趋势日志（start_periodic_diagnostics）

排查思路：
- 服务变卡但无报错，通常是进程内资源随时间累积（Windows SelectorEventLoop
  下 select() 的 socket 数量越多越慢，或线程/句柄/asyncio 任务泄漏）。
- 观察哪一项随使用时间单调增长，即可锁定泄漏源。
"""
from __future__ import annotations

import asyncio
import gc
import logging
import os
import threading

logger = logging.getLogger("diagnostics")

try:
    import psutil  # type: ignore
    _PROC = psutil.Process(os.getpid())
except Exception:  # pragma: no cover
    psutil = None
    _PROC = None


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _registry_sizes() -> dict[str, int]:
    """内存注册表大小：这些应随会话结束回落，只增不减即为泄漏。"""
    sizes: dict[str, int] = {}
    try:
        from services import chat_stream_manager as csm
        sizes["chat_streams"] = len(csm._streams)
        sizes["bg_sessions"] = len(csm._bg_sessions)
    except Exception:
        pass
    try:
        from engine.subagent_runtime import list_running_subagents
        sizes["running_subagents"] = len(list(list_running_subagents()))
    except Exception:
        pass
    try:
        from aries_mcp.runtime import get_mcp_pool
        pool = get_mcp_pool()
        sizes["mcp_connections"] = len(getattr(pool, "_connections", {}) or {})
    except Exception:
        pass
    try:
        from services.terminal_manager import TerminalManager
        sizes["terminal_invocations"] = len(getattr(TerminalManager, "_invocation_sessions", {}) or {})
    except Exception:
        pass
    return sizes


def collect_snapshot() -> dict:
    """采集一次运行时快照。所有字段失败时降级为 None，不抛异常。"""
    snap: dict = {
        "threads": threading.active_count(),
        "gc_objects": _safe(lambda: len(gc.get_objects())),
        "registries": _registry_sizes(),
    }

    # asyncio 任务数（仅当前事件循环）
    try:
        snap["asyncio_tasks"] = len(asyncio.all_tasks())
    except Exception:
        snap["asyncio_tasks"] = None

    if _PROC is not None:
        snap["rss_mb"] = _safe(lambda: round(_PROC.memory_info().rss / 1024 / 1024, 1))
        snap["num_handles"] = _safe(lambda: _PROC.num_handles())  # Windows: 句柄总数
        snap["open_files"] = _safe(lambda: len(_PROC.open_files()))
        snap["connections"] = _safe(lambda: len(_PROC.connections(kind="inet")))
        snap["threads_os"] = _safe(lambda: _PROC.num_threads())
    else:
        snap["psutil"] = "unavailable"

    return snap


# 启动基线（第一帧快照），用于计算增量 Δ，突出"只涨不回"的泄漏项
_BASELINE: dict | None = None

# 关键上限告警阈值（Windows select() FD_SETSIZE=512；句柄接近内核软限提前预警）
_WARN_CONNS = 400
_WARN_HANDLES = 8000


def _flat_metrics(snap: dict) -> dict[str, float]:
    reg = snap.get("registries", {})
    out: dict[str, float] = {}
    for k in ("threads", "asyncio_tasks", "num_handles", "connections",
              "open_files", "rss_mb", "gc_objects"):
        v = snap.get(k)
        if isinstance(v, (int, float)):
            out[k] = v
    for k in ("chat_streams", "bg_sessions", "running_subagents",
              "mcp_connections", "terminal_invocations"):
        v = reg.get(k)
        if isinstance(v, (int, float)):
            out[k] = v
    return out


def _fmt(cur, base) -> str:
    """当前值 + 相对基线增量，如 316(+12)。"""
    if cur is None:
        return "?"
    if base is None or not isinstance(cur, (int, float)) or not isinstance(base, (int, float)):
        return f"{cur}"
    delta = cur - base
    if delta == 0:
        return f"{cur}"
    sign = "+" if delta > 0 else ""
    if isinstance(cur, float):
        return f"{cur}({sign}{round(delta, 1)})"
    return f"{cur}({sign}{delta})"


def format_line(snap: dict, baseline: dict | None = None) -> str:
    reg = snap.get("registries", {})
    b = baseline or {}
    breg = b.get("registries", {}) if baseline else {}
    return (
        f"threads={_fmt(snap.get('threads'), b.get('threads'))} "
        f"tasks={_fmt(snap.get('asyncio_tasks'), b.get('asyncio_tasks'))} "
        f"handles={_fmt(snap.get('num_handles'), b.get('num_handles'))} "
        f"conns={_fmt(snap.get('connections'), b.get('connections'))} "
        f"openfiles={_fmt(snap.get('open_files'), b.get('open_files'))} "
        f"rss={_fmt(snap.get('rss_mb'), b.get('rss_mb'))}MB "
        f"gc={_fmt(snap.get('gc_objects'), b.get('gc_objects'))} "
        f"streams={_fmt(reg.get('chat_streams'), breg.get('chat_streams'))} "
        f"bg={_fmt(reg.get('bg_sessions'), breg.get('bg_sessions'))} "
        f"subagents={_fmt(reg.get('running_subagents'), breg.get('running_subagents'))} "
        f"mcp={_fmt(reg.get('mcp_connections'), breg.get('mcp_connections'))} "
        f"term={_fmt(reg.get('terminal_invocations'), breg.get('terminal_invocations'))}"
    )


def _check_warnings(snap: dict) -> list[str]:
    warns: list[str] = []
    conns = snap.get("connections")
    handles = snap.get("num_handles")
    if isinstance(conns, (int, float)) and conns >= _WARN_CONNS:
        warns.append(f"inet 连接数={conns} 逼近 Windows select() 512 上限，可能是 socket 泄漏")
    if isinstance(handles, (int, float)) and handles >= _WARN_HANDLES:
        warns.append(f"句柄数={handles} 偏高，可能有句柄泄漏")
    return warns


async def _periodic_loop(interval_seconds: int) -> None:
    global _BASELINE
    logger.info("[Diagnostics] 已启动，每 %ss 打印一次运行时快照（数字后括号=相对启动基线的增量）", interval_seconds)
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            snap = collect_snapshot()
            if _BASELINE is None:
                _BASELINE = snap
            logger.info("[Diagnostics] %s", format_line(snap, _BASELINE))
            for w in _check_warnings(snap):
                logger.warning("[Diagnostics] ⚠ %s", w)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.debug("[Diagnostics] 采集失败: %s", exc)


def start_periodic_diagnostics(interval_seconds: int = 60) -> asyncio.Task:
    """在当前事件循环启动周期性诊断日志任务。返回 Task 以便关闭。"""
    return asyncio.create_task(_periodic_loop(interval_seconds))
