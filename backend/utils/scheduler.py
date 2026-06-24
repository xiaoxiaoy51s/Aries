"""定时任务调度器。

核心字段：
- schedule_type + interval_minutes + scheduled_at
- session_id：结果写到哪里（网页 UUID / __wechat__ 等）
- 循环任务执行完成后 INSERT 新行，原行标记 completed
"""

import asyncio
import logging
import uuid

from db.scheduled_task import (
    SCHEDULE_ONCE,
    delete_task,
    get_pending_tasks,
    infer_notify_type,
    infer_platform,
    insert_next_recurring_task,
    is_recurring,
    reset_stale_running_tasks,
    update_task_session_id,
    update_task_status,
)
from utils.time_utils import local_now_iso, local_now_str

logger = logging.getLogger(__name__)

SCAN_INTERVAL_SECONDS = 60


async def run_scheduler():
    print(f"[Scheduler] 已启动，每 {SCAN_INTERVAL_SECONDS}s 扫一次表", flush=True)
    logger.info("[Scheduler] 已启动，每 %ss 扫一次表", SCAN_INTERVAL_SECONDS)
    while True:
        try:
            await scan_and_execute()
        except asyncio.CancelledError:
            print("[Scheduler] 已停止", flush=True)
            break
        except Exception as e:
            print(f"[Scheduler] 扫表异常: {e}", flush=True)
            logger.exception("[Scheduler] 扫表异常")
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


async def scan_and_execute():
    stale = reset_stale_running_tasks()
    if stale:
        msg = f"[Scheduler] 重置 {stale} 个中断的 running 任务为 pending"
        print(msg, flush=True)
        logger.warning(msg)

    now = local_now_iso()
    tasks = get_pending_tasks(now)
    print(f"[Scheduler] 扫描 now={now} (本地 {local_now_str()}), 待执行 {len(tasks)} 个", flush=True)
    logger.info("[Scheduler] 扫描 now=%s (本地 %s), 待执行 %s 个", now, local_now_str(), len(tasks))

    if not tasks:
        return

    for task in tasks:
        await execute_task(task)


async def execute_task(task: dict):
    from services.platform_chat import run_agent_in_session, session_id_for
    from services.platform_push import push_message_to_platform

    task_id = task["id"]
    title = (task.get("title") or "").strip()
    body = (task.get("task_content") or "").strip()
    task_session = (task.get("session_id") or "").strip()
    push_platform = infer_notify_type(task_session, task.get("notify_type"))

    print(f"[Scheduler] 任务 {task_id} 开始执行: {title or '(无标题)'}", flush=True)
    logger.info("[Scheduler] 任务 %s 开始执行: %s", task_id, title or "(无标题)")

    if not body:
        print(f"[Scheduler] 任务 {task_id} 缺少要求说明(task_content)，已标记失败", flush=True)
        update_task_status(task_id, "failed", executed_at=local_now_iso())
        return

    user_text = body
    print(f"[Scheduler] 任务 {task_id} 发送给 AI 的要求说明: {user_text[:120]}", flush=True)

    try:
        update_task_status(task_id, "running")

        platform_session = infer_platform(task_session)
        if platform_session:
            session_id = task_session
            print(f"[Scheduler] 任务 {task_id} → 平台会话 [{session_id}]", flush=True)
        elif push_platform in ("wechat", "qq", "feishu"):
            session_id = session_id_for(push_platform)
            update_task_session_id(task_id, session_id)
            print(f"[Scheduler] 任务 {task_id} → 平台会话 [{session_id}]（legacy notify）", flush=True)
        elif task_session:
            session_id = task_session
            print(f"[Scheduler] 任务 {task_id} → 网页会话 [{session_id[:20]}]", flush=True)
        else:
            session_id = str(uuid.uuid4())
            print(f"[Scheduler] 任务 {task_id} → 新建网页会话 [{session_id[:8]}]", flush=True)
            update_task_session_id(task_id, session_id)

        reply = await run_agent_in_session(session_id, user_text)
        print(f"[Scheduler] 任务 {task_id} AI 回复: {(reply or '')[:120]}", flush=True)
        logger.info("[Scheduler] 任务 %s AI 回复长度=%s", task_id, len(reply or ""))

        await _push_task_reply(task_id, push_platform, reply, push_message_to_platform)
        _handle_post_execution(task, task_id, session_id=session_id)

    except Exception as e:
        print(f"[Scheduler] 任务 {task_id} 执行失败: {e}", flush=True)
        logger.exception("[Scheduler] 任务 %s 执行失败", task_id)
        update_task_status(task_id, "failed", executed_at=local_now_iso())


async def _push_task_reply(task_id, push_platform, reply, push_message_to_platform):
    if push_platform not in ("wechat", "qq", "feishu"):
        print(f"[Scheduler] 任务 {task_id} 未推送到手机（session 为网页会话）", flush=True)
        return

    try:
        pushed = await push_message_to_platform(push_platform, reply or "")
        status = "成功" if pushed else "失败（请检查平台绑定，并先用手机发一条消息）"
        print(f"[Scheduler] 任务 {task_id} 推送到 {push_platform}: {status}", flush=True)
        logger.info("[Scheduler] 任务 %s 推送到 %s: %s", task_id, push_platform, status)
    except Exception as e:
        print(f"[Scheduler] 任务 {task_id} 推送到 {push_platform} 异常: {e}", flush=True)
        logger.exception("[Scheduler] 任务 %s 推送异常", task_id)


def _handle_post_execution(task: dict, task_id: int, *, session_id: str) -> None:
    executed_at = local_now_iso()
    schedule_type = (task.get("schedule_type") or SCHEDULE_ONCE).strip()
    auto_delete = bool(task.get("auto_delete", False))

    if not is_recurring(schedule_type):
        if auto_delete:
            delete_task(task_id)
            print(f"[Scheduler] 任务 {task_id} 已执行并自动删除（auto_delete）", flush=True)
        else:
            update_task_status(task_id, "completed", executed_at=executed_at)
            print(f"[Scheduler] 任务 {task_id} 完成", flush=True)
        return

    # 循环任务：先生成下一条，再处理原记录
    next_id = None
    try:
        next_id = insert_next_recurring_task(task, executed_at, session_id=session_id)
    except ValueError as e:
        print(f"[Scheduler] 任务 {task_id} 无法生成下次任务: {e}", flush=True)

    if auto_delete:
        delete_task(task_id)
        if next_id:
            print(
                f"[Scheduler] 任务 {task_id} 已执行并自动删除，下次任务 #{next_id} ({schedule_type})",
                flush=True,
            )
        else:
            print(f"[Scheduler] 任务 {task_id} 已执行并自动删除（无下次任务）", flush=True)
    else:
        update_task_status(task_id, "completed", executed_at=executed_at)
        if next_id:
            print(
                f"[Scheduler] 任务 {task_id} 完成，已插入下次任务 #{next_id} ({schedule_type})",
                flush=True,
            )
