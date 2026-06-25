"""聊天流管理器

负责：
1. cancel_event 管理（用户点停止时中断任务）
2. session 级别事件队列管理（SSE 断开后后台任务继续推事件，前端切回时恢复）

持久化策略：
- 后台任务的事件以 JSONL 文件存入 ~/.Aries/bg_events/{session_id}.jsonl
- 不写 SQLite（避免 IO 开销导致卡顿）
- 前端 resume 时先从文件重播历史，再从内存 queue 读新事件
- 文件在任务结束后延迟清理
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Any

# session_id -> cancel_event
_streams: dict[str, asyncio.Event] = {}

# session_id -> 后台任务上下文（queue + task + 状态）
_bg_sessions: dict[str, dict] = {}


def _bg_event_dir() -> Path:
    p = Path.home() / ".Aries" / "bg_events"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _bg_event_path(session_id: str) -> Path:
    return _bg_event_dir() / f"{session_id}.jsonl"


def register(session_id: str, cancel_event: asyncio.Event | None = None) -> asyncio.Event:
    """注册一个会话的 cancel_event，若未传入则自动创建。返回 cancel_event。"""
    if cancel_event is None:
        cancel_event = asyncio.Event()
    _streams[session_id] = cancel_event
    return cancel_event


def unregister(session_id: str):
    _streams.pop(session_id, None)


def request_cancel(session_id: str) -> bool:
    cancel_event = _streams.get(session_id)
    if cancel_event:
        cancel_event.set()
        return True
    return False


# ---------- 后台任务 session queue 管理 ----------

def register_bg_session(session_id: str) -> asyncio.Queue:
    """注册一个后台 session，返回事件队列。如果已存在则复用现有队列。"""
    if session_id not in _bg_sessions:
        _bg_sessions[session_id] = {
            "queue": asyncio.Queue(),
            "task": None,
            "done": False,
        }
    return _bg_sessions[session_id]["queue"]


def get_bg_queue(session_id: str) -> asyncio.Queue | None:
    """获取后台 session 的队列（不存在返回 None）。"""
    entry = _bg_sessions.get(session_id)
    return entry["queue"] if entry else None


def append_bg_history(session_id: str, event: str) -> None:
    """将已发送事件追到 JSONL 文件（供 resume 时重播）。

    文件持久化而非纯内存，确保浏览器关闭后重新打开仍能恢复事件。
    """
    file_path = _bg_event_path(session_id)
    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(event.rstrip("\n") + "\n")
    except OSError:
        pass  # 写入失败时静默忽略，不影响主流程


def get_bg_history(session_id: str) -> list[str] | None:
    """从 JSONL 文件读取后台 session 的历史事件列表。

    返回原始 SSE 字符串列表（含 data: 前缀），用于 resume 端点重播。
    """
    file_path = _bg_event_path(session_id)
    if not file_path.exists():
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return [line.rstrip("\n") + "\n" for line in f if line.strip()]
    except OSError:
        return None


def get_bg_history_events(session_id: str) -> list[dict[str, Any]]:
    """从 JSONL 文件解析后台事件为 dict 列表（供消息快照恢复）。

    每行是一个 SSE 事件字符串（data: {...}\n\n），解析后返回 JSON 对象列表。
    """
    file_path = _bg_event_path(session_id)
    if not file_path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("data: "):
                    line = line[len("data: "):].strip()
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return events


def has_bg_event_file(session_id: str) -> bool:
    """检查是否有后台事件文件（可用于在内存态丢失时确认是否有残留事件）。"""
    return _bg_event_path(session_id).exists()


def _cleanup_bg_event_file(session_id: str) -> None:
    """清理后台事件文件。"""
    file_path = _bg_event_path(session_id)
    try:
        if file_path.exists():
            os.remove(file_path)
    except OSError:
        pass


def set_bg_task(session_id: str, task: asyncio.Task) -> None:
    """绑定后台 asyncio.Task。"""
    entry = _bg_sessions.get(session_id)
    if entry:
        entry["task"] = task


def mark_bg_done(session_id: str) -> None:
    """标记后台任务已完成，在 queue 中放入 sentinel。"""
    entry = _bg_sessions.get(session_id)
    if entry:
        entry["done"] = True
        try:
            entry["queue"].put_nowait(None)
        except asyncio.QueueFull:
            pass


def is_bg_running(session_id: str) -> bool:
    """检查该 session 是否有正在运行的后台任务。"""
    entry = _bg_sessions.get(session_id)
    if not entry:
        return False
    if entry["done"]:
        return False
    task = entry.get("task")
    if task is None:
        return False
    return not task.done()


def cleanup_bg_session(session_id: str) -> None:
    """清理已完成的后台 session。"""
    entry = _bg_sessions.get(session_id)
    if entry and entry.get("done"):
        _bg_sessions.pop(session_id, None)
        _cleanup_bg_event_file(session_id)
