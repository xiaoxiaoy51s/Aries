"""定时任务调度器。

原理（极简版）：
- 每 30s 扫一次表，找出 status='pending' 且 scheduled_at<=now 的任务
- 把任务内容当作"用户消息"丢进对应 session（新建或绑定的历史会话）
- 调用 AI（agent 模式，自动加载该 session 的历史记忆）
- 把 AI 回复也存进 chat_messages
- 若绑定的 session 是平台会话（__wechat__/__feishu__/__qq__），把 AI 回复回推到对应 bot
- 单次任务标 completed，循环任务按 interval_seconds 重新排期
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

from db.scheduled_task import (
    TASK_TYPE_RECURRING,
    get_pending_tasks,
    reset_stale_running_tasks,
    reschedule_recurring_task,
    update_task_session_id,
    update_task_status,
)
# 注意：services.platform_chat 与 api.modes.agent_mode 存在间接循环 import，
# 必须在函数内 lazy import，不能放在模块顶部。

logger = logging.getLogger(__name__)

SCAN_INTERVAL_SECONDS = 30


async def run_scheduler():
    print("[Scheduler] 已启动，每 {}s 扫一次表".format(SCAN_INTERVAL_SECONDS), flush=True)
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

    # DB 时间戳统一 UTC，扫描也用 UTC
    now = datetime.utcnow().isoformat()
    tasks = get_pending_tasks(now)
    print(f"[Scheduler] 扫描 now={now}, 待执行 {len(tasks)} 个", flush=True)
    logger.info("[Scheduler] 扫描 now=%s, 待执行 %s 个", now, len(tasks))

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
    user_text = body if body else (f"[定时任务] {title}" if title else f"[定时任务 #{task_id}]")

    print(f"[Scheduler] 任务 {task_id} 开始执行: {title or '(无标题)'}", flush=True)
    logger.info("[Scheduler] 任务 %s 开始执行: %s", task_id, title or "(无标题)")

    try:
        update_task_status(task_id, "running")

        task_session = (task.get("session_id") or "").strip()
        if task_session:
            session_id = task_session
            print(f"[Scheduler] 任务 {task_id} → 复用历史会话 [{session_id[:20]}]", flush=True)
        else:
            session_id = str(uuid.uuid4())
            print(f"[Scheduler] 任务 {task_id} → 新建会话 [{session_id[:8]}]", flush=True)
            update_task_session_id(task_id, session_id)

        reply = await run_agent_in_session(session_id, user_text)
        print(f"[Scheduler] 任务 {task_id} AI 回复: {(reply or '')[:120]}", flush=True)
        logger.info("[Scheduler] 任务 %s AI 回复长度=%s", task_id, len(reply or ""))

        if session_id in (session_id_for("wechat"), session_id_for("qq"), session_id_for("feishu")):
            platform = (
                "wechat" if session_id == session_id_for("wechat")
                else "qq" if session_id == session_id_for("qq")
                else "feishu"
            )
            try:
                pushed = push_message_to_platform(platform, reply or "")
                print(f"[Scheduler] 任务 {task_id} 回推 {platform}: {'成功' if pushed else '无目标用户/失败'}", flush=True)
            except Exception as e:
                print(f"[Scheduler] 任务 {task_id} 回推 {platform} 异常: {e}", flush=True)

        _handle_post_execution(task, task_id)

    except Exception as e:
        print(f"[Scheduler] 任务 {task_id} 执行失败: {e}", flush=True)
        logger.exception("[Scheduler] 任务 %s 执行失败", task_id)
        update_task_status(task_id, "failed", executed_at=datetime.utcnow().isoformat())


def _handle_post_execution(task: dict, task_id: int) -> None:
    task_type = task.get("task_type") or "once"
    if task_type != TASK_TYPE_RECURRING:
        update_task_status(task_id, "completed", executed_at=datetime.utcnow().isoformat())
        print(f"[Scheduler] 任务 {task_id} 完成", flush=True)
        return

    interval = task.get("interval_seconds")
    if not interval or interval <= 0:
        update_task_status(task_id, "completed", executed_at=datetime.utcnow().isoformat())
        print(f"[Scheduler] 任务 {task_id} 缺 interval，已当作一次性", flush=True)
        return

    next_at = (datetime.utcnow() + timedelta(seconds=int(interval))).isoformat()
    reschedule_recurring_task(task_id, next_at)
    print(f"[Scheduler] 任务 {task_id} 循环，下次执行 {next_at}", flush=True)
