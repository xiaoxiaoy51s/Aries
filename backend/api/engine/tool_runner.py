"""工具执行逻辑：单工具执行、子 Agent 并行委派。"""
import json
import asyncio
from typing import Any, Optional, TYPE_CHECKING

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

    reasoning_text = logger.write_tool_call(tool_id, tool_name, args)
    if segment_sink:
        if reasoning_text:
            await segment_sink.on_reasoning(reasoning_text)
        await segment_sink.on_tool_start(tool_name)

    invocation_id = f"{session_id}:{tool_id}"

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
        confirm_event = {
            "confirmation_required": {
                "tool_call_id": tool_id,
                "tool_name": tool_name,
                "command": result.get("command", ""),
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
            retry_args = dict(args)
            retry_args["skip_confirmation"] = True
            result = await execute_tool(
                tool_name,
                retry_args,
                work_dir=work_dir,
                session_id=session_id,
                invocation_id=invocation_id,
                cancel_event=cancel_event,
            )
        yield_event_confirm = confirm_event
    else:
        yield_event_confirm = {}

    return result, yield_event_confirm, stream_stopped


def build_tool_result_event(
    tool_name: str,
    tool_id: str,
    status: str,
    output: str,
    round_no: int,
    result: dict | None = None,
) -> dict[str, Any]:
    """构建工具结果事件。"""
    event = {
        "tool_name": tool_name,
        "tool_call_id": tool_id,
        "status": status,
        "output": output,
        "round": round_no,
    }
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
) -> list[dict]:
    """并行执行所有 delegate_to_subagent 调用。

    返回 tool_results 列表。
    """
    if not delegate_items:
        return []

    from engine.subagent_runtime import run_subagent

    parallel_event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def _on_parallel_subagent_event(payload: dict[str, Any]) -> None:
        await parallel_event_queue.put(payload)

    sub_futures: dict[asyncio.Task, dict[str, Any]] = {}
    for item in delegate_items:
        run_kwargs: dict[str, Any] = dict(
            subagent_name=item["sub_name"],
            task=item["sub_task"],
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

    while True:
        try:
            ev = parallel_event_queue.get_nowait()
        except asyncio.QueueEmpty:
            break

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

    return tool_results
