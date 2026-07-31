"""定时任务业务逻辑层。

参照 backend/db/scheduled_task.py 的业务逻辑（常量、平台推断、下次时间计算、
创建规范、循环任务插入等），适配 cloud 后端的 Service + Repository 分层。
"""
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.model.scheduled_task import ScheduledTask
from app.repository.scheduled_task_repository import ScheduledTaskRepository
from app.utils.time_utils import (
    local_now,
    local_now_iso,
    normalize_local_iso,
    parse_local_iso,
)

# ============ 常量 ============

SCHEDULE_ONCE = "once"
SCHEDULE_DAILY = "daily"
SCHEDULE_INTERVAL = "interval"
SCHEDULE_TYPES = (SCHEDULE_ONCE, SCHEDULE_DAILY, SCHEDULE_INTERVAL)

PLATFORM_SESSION_MAP = {
    "__wechat__": "wechat",
    "__qq__": "qq",
    "__feishu__": "feishu",
}

# AI / 旧版可能填入的平台会话简写，统一归一到平台名
PLATFORM_SESSION_ALIASES = {
    **PLATFORM_SESSION_MAP,
    "_wechat_": "wechat",
    "_weixin_": "wechat",
    "wechat": "wechat",
    "微信": "wechat",
    "_qq_": "qq",
    "qq": "qq",
    "QQ": "qq",
    "_feishu_": "feishu",
    "feishu": "feishu",
    "飞书": "feishu",
}

_PLATFORM_SUFFIXES = (
    ("__wechat__", "wechat"),
    ("__qq__", "qq"),
    ("__feishu__", "feishu"),
)


# ============ 平台推断 ============

def session_id_for(platform: str, email: str = "") -> str:
    """生成用户级平台会话 ID：{email}__qq__ / {email}__wechat__ / {email}__feishu__。"""
    plat = (platform or "").strip().lower()
    if plat not in ("qq", "wechat", "feishu"):
        raise ValueError(f"未知平台: {platform}")
    email = (email or "").strip()
    if email:
        return f"{email}__{plat}__"
    return f"__{plat}__"


def infer_platform(session_id: str | None) -> str | None:
    """从会话 ID 推断平台。兼容旧版 __qq__ 与新版 email__qq__。"""
    sid = (session_id or "").strip()
    if not sid:
        return None
    if sid in PLATFORM_SESSION_MAP:
        return PLATFORM_SESSION_MAP[sid]
    alias = PLATFORM_SESSION_ALIASES.get(sid)
    if alias:
        return alias
    for suffix, platform in _PLATFORM_SUFFIXES:
        if sid.endswith(suffix) and len(sid) > len(suffix):
            return platform
    return None


def resolve_platform_session_id(session_id: str | None, email: str | None = None) -> str | None:
    """将平台简写/旧版会话 ID 解析为当前用户的 email__platform__。

    网页 UUID 等非平台会话原样返回。
    """
    sid = (session_id or "").strip() or None
    if not sid:
        return None
    email = (email or "").strip() or None

    # 已是当前用户的平台会话
    plat = infer_platform(sid)
    if plat and email and sid == session_id_for(plat, email):
        return sid
    # 简写 / 旧版 / 其他用户前缀的平台会话 → 改写到当前用户
    if plat and email:
        return session_id_for(plat, email)
    if plat:
        return session_id_for(plat)
    return sid


def infer_notify_type(session_id: str | None, legacy_notify: str | None = None) -> str:
    platform = infer_platform(session_id)
    if platform:
        return platform
    legacy = (legacy_notify or "none").strip()
    if legacy in ("wechat", "qq", "feishu"):
        return legacy
    return "none"


def is_recurring(schedule_type: str | None) -> bool:
    st = (schedule_type or SCHEDULE_ONCE).strip()
    return st in (SCHEDULE_DAILY, SCHEDULE_INTERVAL)


# ============ 下次执行时间计算 ============

def compute_next_scheduled_at(task: dict, *, base_time=None) -> str:
    """基于实际完成时刻计算下次 scheduled_at（本地时间 ISO 字符串）。"""
    now = base_time if base_time is not None else local_now()
    if isinstance(now, str):
        now = parse_local_iso(now)

    schedule_type = (task.get("schedule_type") or SCHEDULE_ONCE).strip()

    if schedule_type == SCHEDULE_INTERVAL:
        minutes = int(task.get("interval_minutes") or 0)
        if minutes <= 0:
            raise ValueError("间隔任务缺少 interval_minutes")
        return normalize_local_iso((now + timedelta(minutes=minutes)).isoformat())

    if schedule_type == SCHEDULE_DAILY:
        ref_raw = task.get("scheduled_at") or ""
        try:
            ref = parse_local_iso(ref_raw)
            hour, minute = ref.hour, ref.minute
        except (ValueError, TypeError):
            hour, minute = 9, 0
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        return normalize_local_iso(next_run.isoformat())

    raise ValueError("一次性任务无需计算下次执行时间")


# ============ 创建规范 ============

def normalize_create_payload(
    *,
    title: str = "",
    task_content: str = "",
    scheduled_at: str | None = None,
    session_id: str | None = None,
    session_mode: str | None = None,
    schedule_type: str = SCHEDULE_ONCE,
    interval_minutes: int | None = None,
    notify_type: str | None = None,
    auto_delete: bool = False,
    default_session_id: str | None = None,
    user_email: str | None = None,
) -> dict:
    """规范化创建定时任务的字段，供 API 与 agent 工具共用。"""
    schedule_type = (schedule_type or SCHEDULE_ONCE).strip()
    if schedule_type == "recurring":
        schedule_type = SCHEDULE_INTERVAL
    if schedule_type not in SCHEDULE_TYPES:
        raise ValueError(f"schedule_type 必须是 {SCHEDULE_TYPES} 之一")

    session_id = (session_id or "").strip() or None
    if session_mode == "new":
        session_id = None

    notify = (notify_type or "none").strip()
    if notify in ("wechat", "qq", "feishu") and not session_id:
        session_id = session_id_for(notify, user_email or "")
    elif not session_id and default_session_id:
        session_id = (default_session_id or "").strip() or None

    # 平台简写 / 旧版 __qq__ → 用户级 email__qq__
    session_id = resolve_platform_session_id(session_id, user_email)

    task_content = (task_content or "").strip()
    if not task_content:
        raise ValueError("要求说明不能为空")

    stored_interval: int | None = None

    if schedule_type == SCHEDULE_INTERVAL:
        stored_interval = int(interval_minutes or 0)
        if stored_interval <= 0:
            raise ValueError("间隔任务必须提供 interval_minutes")
        if not scheduled_at:
            scheduled_at = normalize_local_iso(
                (local_now() + timedelta(minutes=stored_interval)).isoformat()
            )
    elif schedule_type == SCHEDULE_DAILY:
        if not scheduled_at:
            raise ValueError("每天任务必须提供 scheduled_at")
    else:
        if not scheduled_at:
            raise ValueError("单次任务必须提供 scheduled_at")

    # 平台会话（手机推送）自动强制 auto_delete=True，执行后不留痕迹
    if session_id and infer_platform(session_id):
        auto_delete = True

    return {
        "title": (title or "").strip(),
        "scheduled_at": normalize_local_iso(scheduled_at),
        "task_content": task_content,
        "session_id": session_id,
        "schedule_type": schedule_type,
        "interval_minutes": stored_interval,
        "auto_delete": bool(auto_delete),
    }


# ============ ORM -> dict ============

def task_to_dict(task: ScheduledTask) -> dict:
    """将 ScheduledTask ORM 对象转为字典（供调度器与 API 共用）。"""
    return {
        "id": task.id,
        "user_id": task.user_id,
        "title": task.title or "",
        "task_content": task.task_content or "",
        "scheduled_at": task.scheduled_at or "",
        "session_id": task.session_id or "",
        "status": task.status,
        "schedule_type": (task.schedule_type or SCHEDULE_ONCE).strip(),
        "interval_minutes": task.interval_minutes,
        "auto_delete": bool(task.auto_delete),
        "created_at": task.created_at or "",
        "updated_at": task.updated_at or "",
        "executed_at": task.executed_at or "",
    }


# ============ Service ============

class ScheduledTaskService:
    """定时任务业务逻辑层"""

    @staticmethod
    async def create_task(
        db: AsyncSession,
        user_id: int,
        *,
        title: str = "",
        task_content: str = "",
        scheduled_at: str | None = None,
        session_id: str | None = None,
        schedule_type: str = SCHEDULE_ONCE,
        interval_minutes: int | None = None,
        notify_type: str | None = None,
        auto_delete: bool = False,
    ) -> int:
        """创建定时任务，返回 task_id。"""
        if schedule_type not in SCHEDULE_TYPES:
            raise ValueError(f"schedule_type 必须是 {SCHEDULE_TYPES} 之一")

        title = (title or "").strip()
        task_content = (task_content or "").strip()
        if not task_content:
            raise ValueError("要求说明不能为空")

        scheduled_at = normalize_local_iso(scheduled_at)
        session_id = (session_id or "").strip() or None

        legacy_notify = (notify_type or "none").strip()
        if not session_id and legacy_notify in PLATFORM_SESSION_MAP.values():
            for sid, plat in PLATFORM_SESSION_MAP.items():
                if plat == legacy_notify:
                    session_id = sid
                    break

        stored_interval: int | None = None
        if schedule_type == SCHEDULE_INTERVAL:
            stored_interval = int(interval_minutes or 0)
            if stored_interval <= 0:
                raise ValueError("间隔任务必须提供 interval_minutes")

        now = local_now_iso()
        task = await ScheduledTaskRepository.create(
            db,
            user_id=user_id,
            title=title,
            task_content=task_content,
            scheduled_at=scheduled_at,
            session_id=session_id,
            status="pending",
            schedule_type=schedule_type,
            interval_minutes=stored_interval,
            auto_delete=auto_delete,
            created_at=now,
            updated_at=now,
        )
        return task.id

    @staticmethod
    async def insert_next_recurring_task(
        db: AsyncSession, task: dict, executed_at: str, *, session_id: str | None = None
    ) -> int:
        """执行完成后插入下一条循环任务，字段与原任务一致，仅 scheduled_at 重新计算。"""
        effective_session = (
            session_id if session_id is not None else task.get("session_id") or ""
        ).strip() or None
        payload = {**task, "session_id": effective_session}
        next_at = compute_next_scheduled_at(payload, base_time=executed_at)
        return await ScheduledTaskService.create_task(
            db,
            task["user_id"],
            title=task.get("title") or "",
            task_content=task.get("task_content") or "",
            scheduled_at=next_at,
            session_id=effective_session,
            schedule_type=(task.get("schedule_type") or SCHEDULE_ONCE).strip(),
            interval_minutes=task.get("interval_minutes"),
            auto_delete=bool(task.get("auto_delete", False)),
        )

    @staticmethod
    async def get_pending_tasks(db: AsyncSession, now_iso: str, limit: int = 50) -> list[dict]:
        tasks = await ScheduledTaskRepository.get_pending_tasks(db, now_iso, limit)
        return [task_to_dict(t) for t in tasks]

    @staticmethod
    async def get_task_by_id(db: AsyncSession, task_id: int) -> dict | None:
        task = await ScheduledTaskRepository.find_by_id(db, task_id)
        return task_to_dict(task) if task else None

    @staticmethod
    async def list_tasks(
        db: AsyncSession, user_id: int, page: int = 1, page_size: int = 20
    ) -> dict:
        tasks, total = await ScheduledTaskRepository.list_tasks(db, user_id, page, page_size)
        return {
            "tasks": [task_to_dict(t) for t in tasks],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def reset_stale_running_tasks(db: AsyncSession, stale_minutes: int = 10) -> int:
        return await ScheduledTaskRepository.reset_stale_running_tasks(db, stale_minutes)

    @staticmethod
    async def update_task_status(
        db: AsyncSession, task_id: int, status: str, *, executed_at: str | None = None
    ) -> None:
        await ScheduledTaskRepository.update_status(db, task_id, status, executed_at=executed_at)

    @staticmethod
    async def update_task_session_id(db: AsyncSession, task_id: int, session_id: str) -> None:
        await ScheduledTaskRepository.update_session_id(db, task_id, session_id)

    @staticmethod
    async def cancel_task(db: AsyncSession, task_id: int) -> bool:
        return await ScheduledTaskRepository.cancel_task(db, task_id)

    @staticmethod
    async def delete_task(db: AsyncSession, task_id: int) -> bool:
        return await ScheduledTaskRepository.delete_task(db, task_id)
