"""定时任务调度器。

参照 backend/utils/scheduler.py 适配 cloud 后端（async SQLAlchemy + 流式 ChatService）。

核心字段：
- schedule_type + interval_minutes + scheduled_at
- session_id：结果写到哪里（网页 session UUID / {email}__qq__ 等）
- 循环任务执行完成后 INSERT 新行，原行标记 completed
"""
import asyncio
import json
import logging
import uuid

from app.database import async_session
from app.repository.user_repository import UserRepository
from app.service.chat_service import ChatService
from app.service.scheduled_task_service import (
    SCHEDULE_ONCE,
    ScheduledTaskService,
    infer_notify_type,
    infer_platform,
    is_recurring,
    session_id_for,
)
from app.utils.time_utils import local_now_iso, local_now_str

logger = logging.getLogger(__name__)

SCAN_INTERVAL_SECONDS = 60


async def run_scheduler():
    """调度器主循环：每 SCAN_INTERVAL_SECONDS 秒扫一次表。"""
    logger.info("[Scheduler] 已启动，每 %ss 扫一次表", SCAN_INTERVAL_SECONDS)
    while True:
        try:
            await scan_and_execute()
        except asyncio.CancelledError:
            logger.info("[Scheduler] 已停止")
            break
        except Exception as e:
            logger.exception("[Scheduler] 扫表异常: %s", e)
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


async def scan_and_execute():
    """扫描待执行任务并逐个执行。"""
    async with async_session() as db:
        stale = await ScheduledTaskService.reset_stale_running_tasks(db)
        if stale:
            logger.warning("[Scheduler] 重置 %s 个中断的 running 任务为 pending", stale)

        now = local_now_iso()
        tasks = await ScheduledTaskService.get_pending_tasks(db, now)

    if not tasks:
        logger.debug("[Scheduler] 扫描完成，无待执行任务")
        return

    logger.info(
        "[Scheduler] 扫描 now=%s (本地 %s), 待执行 %s 个", now, local_now_str(), len(tasks)
    )

    for task in tasks:
        await execute_task(task)


async def execute_task(task: dict):
    """执行单个定时任务：调用 ChatService 流式对话并收集回复。"""
    task_id = task["id"]
    user_id = task["user_id"]
    title = (task.get("title") or "").strip()
    body = (task.get("task_content") or "").strip()
    task_session = (task.get("session_id") or "").strip()
    push_platform = infer_notify_type(task_session)

    logger.info("[Scheduler] 任务 %s 开始执行: %s", task_id, title or "(无标题)")

    if not body:
        logger.warning("[Scheduler] 任务 %s 缺少要求说明(task_content)，已标记失败", task_id)
        async with async_session() as db:
            await ScheduledTaskService.update_task_status(
                db, task_id, "failed", executed_at=local_now_iso()
            )
        return

    user_text = body
    logger.info("[Scheduler] 任务 %s 发送给 AI 的要求说明: %s", task_id, user_text[:120])

    try:
        # 标记 running
        async with async_session() as db:
            await ScheduledTaskService.update_task_status(db, task_id, "running")

        # 查找用户（ChatService 需要 user_email 解析模型配置）
        async with async_session() as db:
            user = await UserRepository.find_by_id(db, user_id)
        if not user:
            logger.warning(
                "[Scheduler] 任务 %s 用户不存在(user_id=%s)，已标记失败", task_id, user_id
            )
            async with async_session() as db:
                await ScheduledTaskService.update_task_status(
                    db, task_id, "failed", executed_at=local_now_iso()
                )
            return

        # 确定 session_id（平台会话按用户邮箱隔离：email__qq__）
        platform_session = infer_platform(task_session)
        if platform_session:
            session_id = session_id_for(platform_session, user.email)
            if session_id != task_session:
                async with async_session() as db:
                    await ScheduledTaskService.update_task_session_id(db, task_id, session_id)
            logger.info("[Scheduler] 任务 %s -> 平台会话 [%s]", task_id, session_id)
        elif push_platform in ("wechat", "qq", "feishu"):
            session_id = session_id_for(push_platform, user.email)
            async with async_session() as db:
                await ScheduledTaskService.update_task_session_id(db, task_id, session_id)
            logger.info(
                "[Scheduler] 任务 %s -> 平台会话 [%s]（legacy notify）", task_id, session_id
            )
        elif task_session:
            session_id = task_session
            logger.info("[Scheduler] 任务 %s -> 网页会话 [%s]", task_id, session_id[:20])
        else:
            session_id = f"sess-{uuid.uuid4().hex[:12]}"
            logger.info("[Scheduler] 任务 %s -> 新建网页会话 [%s]", task_id, session_id)
            async with async_session() as db:
                await ScheduledTaskService.update_task_session_id(db, task_id, session_id)

        # 调用 ChatService 流式对话，消费 SSE 收集回复
        reply = await _run_agent_in_session(user.email, user.id, session_id, user_text)
        logger.info(
            "[Scheduler] 任务 %s AI 回复: %s", task_id, (reply or "")[:120]
        )
        logger.info("[Scheduler] 任务 %s AI 回复长度=%s", task_id, len(reply or ""))

        if push_platform in ("wechat", "qq", "feishu"):
            logger.info(
                "[Scheduler] 任务 %s 结果已写入会话，"
                "是否推送到 %s 由 AI 通过工具自行决定",
                task_id,
                push_platform,
            )

        # 执行后处理（标记完成 / 插入下次循环任务）
        async with async_session() as db:
            await _handle_post_execution(db, task, task_id, session_id=session_id)

    except Exception as e:
        logger.exception("[Scheduler] 任务 %s 执行失败: %s", task_id, e)
        async with async_session() as db:
            await ScheduledTaskService.update_task_status(
                db, task_id, "failed", executed_at=local_now_iso()
            )


async def _run_agent_in_session(
    user_email: str, user_id: int, session_id: str, user_text: str
) -> str:
    """在指定 session 中跑一轮对话，消费流式 SSE 并返回最终助手回复。

    参照 backend/services/platform_chat.py 的 run_agent_in_session，
    适配 cloud 后端的 ChatService.chat_stream 流式生成器。
    """
    reply_parts: list[str] = []
    async with async_session() as db:
        async for sse in ChatService.chat_stream(
            db, user_email, user_id, session_id, user_text
        ):
            if not sse.startswith("data: "):
                continue
            raw = sse[6:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                event = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if event.get("type") == "assistant_text":
                reply_parts.append(event.get("text", ""))
    return "".join(reply_parts)


async def _handle_post_execution(
    db, task: dict, task_id: int, *, session_id: str
) -> None:
    """执行后处理：一次性任务标记完成/删除，循环任务插入下次。"""
    executed_at = local_now_iso()
    schedule_type = (task.get("schedule_type") or SCHEDULE_ONCE).strip()
    auto_delete = bool(task.get("auto_delete", False))

    if not is_recurring(schedule_type):
        if auto_delete:
            await ScheduledTaskService.delete_task(db, task_id)
            logger.info("[Scheduler] 任务 %s 已执行并自动删除（auto_delete）", task_id)
        else:
            await ScheduledTaskService.update_task_status(
                db, task_id, "completed", executed_at=executed_at
            )
            logger.info("[Scheduler] 任务 %s 完成", task_id)
        return

    # 循环任务：先生成下一条，再处理原记录
    next_id = None
    try:
        next_id = await ScheduledTaskService.insert_next_recurring_task(
            db, task, executed_at, session_id=session_id
        )
    except ValueError as e:
        logger.warning("[Scheduler] 任务 %s 无法生成下次任务: %s", task_id, e)

    if auto_delete:
        await ScheduledTaskService.delete_task(db, task_id)
        if next_id:
            logger.info(
                "[Scheduler] 任务 %s 已执行并自动删除，下次任务 #%s (%s)",
                task_id,
                next_id,
                schedule_type,
            )
        else:
            logger.info("[Scheduler] 任务 %s 已执行并自动删除（无下次任务）", task_id)
    else:
        await ScheduledTaskService.update_task_status(
            db, task_id, "completed", executed_at=executed_at
        )
        if next_id:
            logger.info(
                "[Scheduler] 任务 %s 完成，已插入下次任务 #%s (%s)",
                task_id,
                next_id,
                schedule_type,
            )
        else:
            logger.info("[Scheduler] 任务 %s 完成（无下次任务）", task_id)
