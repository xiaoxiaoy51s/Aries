"""聊天流管理器

负责：
1. cancel_event 管理（用户点停止时中断任务）
2. session 级别事件队列管理（SSE 断开后后台任务继续推事件，前端切回时恢复）
"""
import asyncio

# session_id -> cancel_event
_streams: dict[str, asyncio.Event] = {}

# session_id -> 后台任务上下文（queue + task + 状态）
# SSE 断开后，后台任务继续运行，事件推入 queue
# 前端切回对话时通过 resume 端点从 queue 中继续读取
_bg_sessions: dict[str, dict] = {}


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
