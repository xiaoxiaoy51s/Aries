"""工具执行逻辑：单工具执行、子 Agent 并行委派。"""
import json
import asyncio
from typing import Any, Optional, AsyncGenerator, TYPE_CHECKING

if TYPE_CHECKING:
    from services.platform_segment import PlatformStreamSink

from engine.tool_definitions import execute_async as execute_tool
from .confirmation import (
    CONFIRMATION_TIMEOUT_SECONDS,
    register_confirmation_wait,
    wait_for_confirmation_with_cancel,
)
from .todo_handler import update_todos, clear_todos
from .stream_constants import TOOL_EXECUTION_TIMEOUT_SECONDS
from .tool_hooks import run_pre_tool_hooks, run_post_tool_hooks
from .approval_cache import cache_approval, is_approved
from utils.tool_cache import (
    get_cached_tool_result,
    store_tool_result,
    invalidate_work_dir_cache,
    is_cache_busting_tool,
)

# 工具错误级别
TOOL_ERROR_RESPOND_TO_MODEL = "respond_to_model"  # 软错误：回传模型，继续对话
TOOL_ERROR_FATAL = "fatal"                          # 硬错误：终止整轮

# 可安全并行的只读工具（无副作用、不修改状态）
PARALLEL_SAFE_TOOLS: set[str] = {
    "read_file", "list_files", "search_file",
    "check_command_status", "todo_write", "send_file_to_user",
}


def is_parallel_safe(tool_name: str) -> bool:
    """判断工具是否可安全并行执行（只读、无副作用）。"""
    return tool_name in PARALLEL_SAFE_TOOLS


async def run_single_tool(
    tool_name: str,
    args: dict,
    tool_id: str,
    session_id: str,
    work_dir: str | None,
    round_no: int,
    logger,
    cancel_event: Optional[asyncio.Event] = None,
    segment_sink: Optional["PlatformStreamSink"] = None,
    assistant_message_id: str | None = None,
) -> tuple[dict, dict, bool]:
    """执行单个工具调用。

    返回 (tool_result_dict, result_event_dict, stream_stopped)
    """
    stream_stopped = False
    terminal_session_id = ""

    # cli_executor：解析终端 session
    if tool_name == "cli_executor":
        custom_sid = (args.get("session_id") or "").strip()
        try:
            from services.terminal_manager import TerminalManager
            tm = TerminalManager.get_instance()
            invocation_key = f"{session_id}:{tool_id}"
            if custom_sid:
                terminal_session_id = custom_sid
            else:
                terminal_session_id = tm.resolve_agent_session_id(work_dir)
            TerminalManager.register_invocation_session(invocation_key, terminal_session_id)
        except Exception:
            terminal_session_id = custom_sid or f"agent:{work_dir}"

    reasoning_text = logger.write_tool_call(
        tool_id,
        tool_name,
        args,
        session_id=terminal_session_id,
    )
    if segment_sink:
        if reasoning_text:
            await segment_sink.on_reasoning(reasoning_text)
        await segment_sink.on_tool_start(tool_name)

    invocation_id = f"{session_id}:{tool_id}"

    # ===== PreToolUse hook =====
    hook_context = {"session_id": session_id, "work_dir": work_dir, "round_no": round_no, "tool_id": tool_id}
    hook_ret = await run_pre_tool_hooks(tool_name, args, hook_context)
    if "blocked" in hook_ret:
        result = {"success": False, "error": f"工具被 hook 阻断：{hook_ret['blocked']}", "output": hook_ret["blocked"]}
        return result, {}, False
    if "updated_args" in hook_ret:
        args = hook_ret["updated_args"]

    # ===== L2 工具结果缓存（只读/幂等工具） =====
    cached_result = get_cached_tool_result(tool_name, args, work_dir)
    if cached_result is not None:
        return cached_result, {}, False

    # todo_write 拦截
    if tool_name == "todo_write":
        todo_args = args.get("todos", [])
        merge_mode = bool(args.get("merge", False))
        updated = update_todos(session_id, todo_args, merge=merge_mode)
        if updated and all(t.get("status") == "completed" for t in updated):
            clear_todos(session_id)
            updated = []
            output = "任务清单已全部完成并已自动清空"
        else:
            output = f"任务清单已更新（{len(updated)} 项）"
        result = {"success": True, "todos": updated, "output": output}
        return result, {}, False

    # 普通工具执行
    try:
        result = await asyncio.wait_for(
            execute_tool(
                tool_name,
                args,
                work_dir=work_dir,
                session_id=session_id,
                invocation_id=invocation_id,
                cancel_event=cancel_event,
            ),
            timeout=TOOL_EXECUTION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        result = {
            "success": False,
            "error": "Tool execution timed out",
            "output": (
                f"工具 `{tool_name}` 执行超时（>{int(TOOL_EXECUTION_TIMEOUT_SECONDS)} 秒）。"
                "Playwright 等浏览器任务可能页面加载过慢，请减少 wait_ms 或拆分步骤。"
            ),
        }

    # 危险命令确认流程
    if isinstance(result, dict) and result.get("requires_confirmation"):
        command_str = result.get("command", "")
        # 审批缓存：当前会话已批准过相同命令，直接跳过确认
        if command_str and is_approved(session_id, command_str):
            result.pop("requires_confirmation", None)
            retry_args = dict(args)
            retry_args["skip_confirmation"] = True
            result = await execute_tool(
                tool_name, retry_args,
                work_dir=work_dir, session_id=session_id,
                invocation_id=invocation_id, cancel_event=cancel_event,
            )
        else:
            confirm_event = {
                "confirmation_required": {
                    "tool_call_id": tool_id,
                    "tool_name": tool_name,
                    "command": command_str,
                    "danger_info": result.get("danger_info", ""),
                    "danger_types": result.get("danger_types", []),
                    "args": args,
                    "round": round_no,
                }
            }
            register_confirmation_wait(tool_id)
            yield_event_confirm = confirm_event

            confirmed = await wait_for_confirmation_with_cancel(
                tool_id,
                cancel_event=cancel_event,
                timeout=CONFIRMATION_TIMEOUT_SECONDS,
            )
            stream_stopped = bool(cancel_event and cancel_event.is_set())
            if stream_stopped or not confirmed:
                result = {
                    "success": False,
                    "error": "Stream stopped" if stream_stopped else "User cancelled",
                    "output": "用户已停止生成" if stream_stopped else "用户取消了危险命令执行",
                    "requires_confirmation": False,
                }
            else:
                # 缓存审批结果，同会话后续相同命令不再确认
                if command_str:
                    cache_approval(session_id, command_str)
                retry_args = dict(args)
                retry_args["skip_confirmation"] = True
                result = await execute_tool(
                    tool_name, retry_args,
                    work_dir=work_dir, session_id=session_id,
                    invocation_id=invocation_id, cancel_event=cancel_event,
                )
        yield_event_confirm = confirm_event
    else:
        yield_event_confirm = {}

    # ===== PostToolUse hook =====
    if isinstance(result, dict):
        post_ret = await run_post_tool_hooks(tool_name, args, result, hook_context)
        if "blocked" in post_ret:
            result = {"success": False, "error": f"结果被 hook 阻断：{post_ret['blocked']}", "output": post_ret["blocked"]}
        elif "feedback" in post_ret:
            result = dict(result)
            result["output"] = post_ret["feedback"]

    # ===== L2 缓存写入 / 写操作后失效 =====
    if isinstance(result, dict):
        if is_cache_busting_tool(tool_name, args) and result.get("success") is not False and not result.get("error"):
            invalidate_work_dir_cache(work_dir)
        else:
            store_tool_result(tool_name, args, work_dir, result)

    # ===== 错误级别标记 =====
    # 工具执行超时、hook 阻断 → 软错误（回传模型继续）
    # execute_tool 抛异常且非超时 → 硬错误（标记 fatal）
    if isinstance(result, dict) and result.get("error") and not result.get("success", True):
        is_timeout = "timed out" in str(result.get("error", "")).lower() or "超时" in str(result.get("error", ""))
        is_user_cancel = "cancel" in str(result.get("error", "")).lower() or "取消" in str(result.get("error", ""))
        if is_timeout or is_user_cancel:
            result["_error_level"] = TOOL_ERROR_RESPOND_TO_MODEL
        else:
            result["_error_level"] = TOOL_ERROR_RESPOND_TO_MODEL

    return result, yield_event_confirm, stream_stopped


def build_tool_result_event(
    tool_name: str,
    tool_id: str,
    status: str,
    output: str,
    round_no: int,
    result: dict | None = None,
    cached: bool = False,
) -> dict[str, Any]:
    """构建工具结果事件。"""
    event = {
        "tool_name": tool_name,
        "tool_call_id": tool_id,
        "status": status,
        "output": output,
        "round": round_no,
    }
    if cached:
        event["cached"] = True
    if result:
        result_session_id = result.get("session_id") if isinstance(result, dict) else None
        if result_session_id:
            event["session_id"] = result_session_id
        result_pid = result.get("pid") if isinstance(result, dict) else None
        if result_pid:
            event["pid"] = result_pid
        if isinstance(result, dict) and result.get("auto_detached"):
            event["auto_detached"] = True
        _file_change = result.get("file_change") if isinstance(result, dict) else None
        if _file_change:
            event["file_change"] = _file_change
    return event


async def run_delegate_items(
    delegate_items: list[dict[str, Any]],
    session_id: str,
    work_dir: str | None,
    logger,
    cancel_event: Optional[asyncio.Event] = None,
    round_no: int = 0,
) -> AsyncGenerator[dict[str, Any], None]:
    """并行执行所有 delegate_to_subagent 调用。

    以 async generator 形式产出：
    - 实时事件 dict（含 "type" 和 "data" 键）供 SSE 转发
    - 最终用 {"__final_results": [...]} 标记结束并携带结果列表
    """
    if not delegate_items:
        yield {"__final_results": []}
        return

    from engine.subagent_runtime import run_subagent

    parallel_event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def _on_parallel_subagent_event(payload: dict[str, Any]) -> None:
        await parallel_event_queue.put(payload)

    sub_futures: dict[asyncio.Task, dict[str, Any]] = {}
    # 参数校验失败的结果，直接构造错误返回，不进入实际执行
    precheck_failures: list[dict[str, Any]] = []
    for item in delegate_items:
        tool_id = item["tool_id"]
        tool_name = item["tool_name"]
        sub_name = item["sub_name"]
        sub_task = item["sub_task"]

        # 参数校验：subagent_name 和 task 必须非空
        if not sub_name:
            err_msg = (
                "参数错误：subagent_name 不能为空。"
                "请从 Available Subagents 路由表中选择一个有效的 name 传入。"
            )
            precheck_failures.append({
                "tool_call_id": tool_id,
                "tool_name": tool_name,
                "item": item,
                "result": {"error": err_msg, "status": "failed", "log_path": ""},
            })
            logger.write_subagent_block(
                tool_call_id=tool_id,
                subagent_name=sub_name or "(empty)",
                task=item.get("sub_desc") or sub_task,
                status="failed",
                log_path="",
                final_output="",
                error=err_msg,
            )
            continue
        if not sub_task:
            err_msg = "参数错误：task 不能为空。请在 task 字段中提供完整的任务描述。"
            precheck_failures.append({
                "tool_call_id": tool_id,
                "tool_name": tool_name,
                "item": item,
                "result": {"error": err_msg, "status": "failed", "log_path": ""},
            })
            logger.write_subagent_block(
                tool_call_id=tool_id,
                subagent_name=sub_name,
                task="(empty)",
                status="failed",
                log_path="",
                final_output="",
                error=err_msg,
            )
            continue

        run_kwargs: dict[str, Any] = dict(
            subagent_name=sub_name,
            task=sub_task,
            context=item["sub_context"],
            work_dir=work_dir,
            cancel_event=cancel_event,
            on_event=_on_parallel_subagent_event,
        )
        if item.get("sub_isolation"):
            run_kwargs["isolation"] = item["sub_isolation"]
        task_obj = asyncio.create_task(run_subagent(**run_kwargs))
        sub_futures[task_obj] = item

    pending_tasks = set(sub_futures.keys())
    while pending_tasks:
        if cancel_event and cancel_event.is_set():
            for t in pending_tasks:
                t.cancel()
            break
        done, pending_tasks = await asyncio.wait(pending_tasks, timeout=0.5)
        while True:
            try:
                ev = parallel_event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            # 转发实时事件到 SSE 流（格式：{"subagent_xxx": {...}} → {"type": "subagent_xxx", "data": {...}}）
            for ev_type, ev_data in ev.items():
                yield {"type": ev_type, "data": ev_data}

    # drain 剩余事件
    while True:
        try:
            ev = parallel_event_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        for ev_type, ev_data in ev.items():
            yield {"type": ev_type, "data": ev_data}

    tool_results = []
    for task_obj, item in sub_futures.items():
        tool_id = item["tool_id"]
        tool_name = item["tool_name"]
        sub_name = item["sub_name"]
        sub_desc = item["sub_desc"]
        sub_task_text = item["sub_task"]

        try:
            sub_result = task_obj.result()
        except asyncio.CancelledError:
            sub_result = {"error": "用户取消了子 Agent 任务", "status": "cancelled", "log_path": ""}
        except Exception as exc:
            sub_result = {"error": f"子 Agent 异常：{exc}", "status": "failed", "log_path": ""}

        final_status = "success" if "result" in sub_result else sub_result.get("status", "failed")
        logger.write_subagent_block(
            tool_call_id=tool_id,
            subagent_name=sub_name,
            task=sub_desc or sub_task_text,
            status=final_status,
            log_path=str(sub_result.get("log_path") or ""),
            final_output=str(sub_result.get("result") or ""),
            error=str(sub_result.get("error") or ""),
        )

        tool_results.append({
            "tool_call_id": tool_id,
            "role": "tool",
            "content": json.dumps(sub_result, ensure_ascii=False),
        })
        logger.write_tool_result(
            tool_id, tool_name,
            "completed" if final_status == "success" else "error",
            result=json.dumps(sub_result, ensure_ascii=False),
            error=str(sub_result.get("error") or ""),
        )

    # 合并参数校验失败的结果
    for fail in precheck_failures:
        tool_results.append({
            "tool_call_id": fail["tool_call_id"],
            "role": "tool",
            "content": json.dumps(fail["result"], ensure_ascii=False),
        })
        logger.write_tool_result(
            fail["tool_call_id"], fail["tool_name"],
            "error",
            result=json.dumps(fail["result"], ensure_ascii=False),
            error=str(fail["result"].get("error") or ""),
        )

    yield {"__final_results": tool_results}
