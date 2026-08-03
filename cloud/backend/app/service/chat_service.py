import asyncio
import base64
import json
import time
import uuid
import httpx
from typing import AsyncGenerator, Optional, TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.services.platform_segment import PlatformStreamSink

from app.memory.context_loader import build_context_messages
from app.repository.session_repository import MessageRepository
from app.service.model_config_service import ModelConfigService
from app.service.session_service import SessionService
from app.tools.registry import get_tool_schemas, execute_tool, parse_tool_arguments
from app.tools.sandbox import cleanup_session_processes
from app.utils.session_logger import SessionLogger
from app.utils.token_counter import normalize_api_usage


def _build_tool_content(tool_result: str, tc_args: dict) -> tuple[str, list[tuple[str, str]], str]:
    """构造 tool message content（纯文本）+ 待注入图片列表。

    很多模型 API 的 tool 消息不支持 content array（multimodal），
    因此 tool 消息 content 始终为纯文本；图片由调用方作为单独的
    user 消息注入（参考 computer-use 方案）。

    返回 (content, images, log_text)：
    - content: tool 消息的纯文本 content
    - images: [(base64, mime), ...]，调用方需追加 user 消息注入
    - log_text: 日志/SSE 展示文本
    """
    if isinstance(tool_result, str) and tool_result.startswith('{"__image_ref__"'):
        try:
            info = json.loads(tool_result)
            if info.get("__image_ref__"):
                img_path = info["path"]
                mime = info.get("mime", "image/png")
                display = info.get("display", img_path)
                with open(img_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                content = f"(已加载图片: {display}，画面已通过视觉通道注入)"
                return content, [(b64, mime)], f"(图片已加载: {display})"
        except Exception as e:
            return f"图片加载失败: {e}", [], f"图片加载失败: {e}"
    return tool_result, [], tool_result


class ChatService:
    """聊天业务逻辑层

    集成会话管理 + JSONL 日志 + 流式输出 + 工具调用循环。
    """

    @staticmethod
    async def _resolve_model(user_email: str):
        return await ModelConfigService.get_active_model(user_email)

    @staticmethod
    async def _stream_one_round(
        *,
        client: httpx.AsyncClient,
        url: str,
        headers: dict,
        payload: dict,
        logger: SessionLogger,
        sse_queue: list[str],
        result_out: dict,  # mutable container for return value
    ) -> AsyncGenerator[str, None]:
        """执行一轮流式请求，yield SSE 事件，结果写入 result_out。

        result_out 被填充:
          - content: str
          - tool_calls: list[dict]
          - finish_reason: str
        """
        accumulated_content = ""
        tool_calls_acc: dict[int, dict] = {}
        finish_reason = ""

        async with client.stream("POST", url, headers=headers, json=payload) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                yield f'data: {json.dumps({"type": "error", "error": error_text.decode()})}\n\n'
                result_out.update({
                    "content": "",
                    "tool_calls": [],
                    "finish_reason": "error",
                })
                return

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    choices = chunk.get("choices") or []
                    if choices:
                        choice = choices[0]
                        delta = choice.get("delta", {})
                        finish_reason = choice.get("finish_reason", "") or finish_reason

                        # reasoning
                        reasoning = delta.get("reasoning_content", "")
                        if reasoning:
                            logger.append_reasoning_delta(reasoning)

                        # content
                        content = delta.get("content", "")
                        if content:
                            accumulated_content += content
                            logger.record_assistant_content(content)

                        # tool_calls (增量累积)
                        delta_tool_calls = delta.get("tool_calls")
                        if delta_tool_calls:
                            for tc in delta_tool_calls:
                                idx = tc.get("index", 0)
                                if idx not in tool_calls_acc:
                                    tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                                if tc.get("id"):
                                    tool_calls_acc[idx]["id"] = tc["id"]
                                func = tc.get("function", {})
                                if func.get("name"):
                                    tool_calls_acc[idx]["name"] = func["name"]
                                if func.get("arguments"):
                                    tool_calls_acc[idx]["arguments"] += func["arguments"]

                    # token usage
                    usage = chunk.get("usage")
                    if usage:
                        normalized = normalize_api_usage(usage)
                        logger.add_token_usage(normalized)

                    # flush SSE
                    while sse_queue:
                        yield sse_queue.pop(0)

                except json.JSONDecodeError:
                    continue

        tool_calls = [tool_calls_acc[k] for k in sorted(tool_calls_acc.keys())]
        result_out.update({
            "content": accumulated_content,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
        })

    @staticmethod
    async def chat_stream(
        db: AsyncSession,
        user_email: str,
        user_id: int,
        session_id: str | None,
        message: str,
        *,
        images: list[str] | None = None,
        platform: str = "",
        as_agent: str = "",
        segment_sink: "PlatformStreamSink | None" = None,
        cancel_event: Optional[Any] = None,
        workspace_dir: str | None = None,
        skills: list[str] | None = None,
        use_kb: bool = False,
    ) -> AsyncGenerator[str, None]:
        """流式对话 + 工具调用循环。

        当模型返回 tool_calls 时，执行工具并将结果回传给模型，循环直到
        模型不再请求工具或达到 max_tool_rounds 上限。
        platform 非空时，平台说明写入 system prompt，不污染用户消息。
        as_agent 非空时，以该子 Agent 提示词作为主对话身份。
        use_kb 为 True 时，先对用户消息做知识库检索，将命中文档注入 system prompt。
        """

        # 1. 获取模型配置
        model = await ChatService._resolve_model(user_email)
        if not model:
            yield f'data: {json.dumps({"type": "error", "error": "尚未配置模型，请先在设置中添加模型。"})}\n\n'
            yield "data: [DONE]\n\n"
            return

        max_rounds = getattr(model, "max_tool_rounds", 100) or 100

        image_list = [img for img in (images or []) if img]
        clean_message = (message or "").strip()
        if not clean_message and not image_list:
            yield f'data: {json.dumps({"type": "error", "error": "消息内容不能为空。"})}\n\n'
            yield "data: [DONE]\n\n"
            return

        # 2. 创建或获取 session
        title_source = clean_message or ("[图片]" if image_list else "新对话")
        session = None
        if not session_id:
            session_id = f"sess-{uuid.uuid4().hex[:12]}"
            title = title_source[:30].replace("\n", " ") + ("..." if len(title_source) > 30 else "")
            ws = (workspace_dir or "default").strip() or "default"
            await SessionService.create_session(
                db, session_id, user_id, title,
                user_email=user_email, workspace_dir=ws,
            )
            session = await SessionService.get_session(db, session_id)
        else:
            session = await SessionService.get_session(db, session_id)
            if not session:
                title = title_source[:30].replace("\n", " ") + ("..." if len(title_source) > 30 else "")
                ws = (workspace_dir or "default").strip() or "default"
                await SessionService.create_session(
                    db, session_id, user_id, title,
                    user_email=user_email, workspace_dir=ws,
                )
                session = await SessionService.get_session(db, session_id)

        session_workspace = (session.workspace_dir if session else None) or "default"

        # 3. 推送 session_id
        yield f'data: {json.dumps({"type": "session", "session_id": session_id})}\n\n'

        # 4. 写入用户消息
        user_msg = await MessageRepository.create(
            db, session_id=session_id, user_id=user_id, role="user", log_path=""
        )
        user_logger = SessionLogger(user_email, session_id, user_msg.id)
        user_logger.write_user_message(clean_message, image_list)
        await MessageRepository.update_log_path(db, user_msg.id, user_logger.jsonl_path_str)
        user_logger.finalize()

        # 5. 创建 assistant 消息 + logger
        assistant_msg = await MessageRepository.create(
            db, session_id=session_id, user_id=user_id, role="assistant", log_path=""
        )

        sse_queue: list[str] = []

        def on_event(event: dict):
            # 前端 SSE 仍按 token 广播；平台推送不在这里触发（避免按 token 刷屏）
            sse_queue.append(f"data: {json.dumps(event, ensure_ascii=False)}\n\n")

        logger = SessionLogger(user_email, session_id, assistant_msg.id, on_event=on_event)
        logger.set_model(model.model)
        await MessageRepository.update_log_path(db, assistant_msg.id, logger.jsonl_path_str)

        # 6. 构建上下文
        db_messages = await SessionService.get_messages(db, session_id)
        messages, context_info = build_context_messages(
            db_messages=db_messages,
            current_user_text=clean_message,
            current_user_images=image_list,
            model=model.model,
            platform=platform,
            user_email=user_email,
            as_agent=as_agent,
            workspace_dir=session_workspace,
            skills=skills,
        )

        # 6.5 知识库模式：BM25 检索 wiki 文档，命中文档注入 system prompt（不污染用户消息）
        if use_kb and clean_message:
            try:
                from app.service.wiki import retrieval

                kb_pages = await retrieval.retrieve(user_email, clean_message, top_k=5)
                if kb_pages:
                    kb_ctx = "\n\n".join(
                        f"### {p['file_path']}\n{p['content_md'] or ''}" for p in kb_pages
                    )
                    kb_sys = (
                        "【知识库资料】用户开启了知识库问答模式。请优先基于以下 wiki 文档内容回答，"
                        "并用 [[标题]] 或 [来源: 文件路径] 标注引用来源；"
                        "若资料不足以回答，请明确说明基于资料无法回答。\n\n"
                        f"Wiki 文档：\n{kb_ctx}"
                    )
                    # 注入为 system 消息（置于最前，历史消息之后由 build_context_messages 已排好）
                    messages.insert(
                        0, {"role": "system", "content": kb_sys}
                    )
                    context_info["kb_retrieved"] = len(kb_pages)
            except Exception:
                # 检索失败不阻断主对话
                pass

        yield f'data: {json.dumps({"type": "context_info", "context_info": context_info})}\n\n'

        # 7. 工具调用循环
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {model.apiKey}",
        }
        base_url = model.baseUrl.rstrip("/")
        api_url = f"{base_url}/chat/completions"
        timeout = httpx.Timeout(connect=30.0, read=300.0, write=120.0, pool=30.0)
        tool_schemas = get_tool_schemas()
        # 以子 Agent 身份作主对话时，禁止再委派（避免递归身份混乱）
        if as_agent:
            tool_schemas = [
                s for s in tool_schemas
                if s.get("function", {}).get("name") != "delegate_to_subagent"
            ]
        start_ts = time.time()

        async def _push_flushed_assistant_segment() -> None:
            """对齐参考后端：只推送 flush 后的整段 assistant_text，不推 token。"""
            if not segment_sink:
                return
            flushed = logger.flush_assistant_segment()
            if flushed.strip():
                await segment_sink.on_assistant(flushed)

        try:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                for round_num in range(max_rounds + 1):
                    if cancel_event and cancel_event.is_set():
                        break
                    payload = {
                        "model": model.model,
                        "messages": messages,
                        "stream": True,
                        "stream_options": {"include_usage": True},
                    }
                    if tool_schemas:
                        payload["tools"] = tool_schemas

                    # 流式请求
                    result: dict = {}
                    async for sse in ChatService._stream_one_round(
                        client=client,
                        url=api_url,
                        headers=headers,
                        payload=payload,
                        logger=logger,
                        sse_queue=sse_queue,
                        result_out=result,
                    ):
                        yield sse

                    # flush 残留 SSE
                    while sse_queue:
                        yield sse_queue.pop(0)

                    tool_calls = result.get("tool_calls", [])
                    content = result.get("content", "")

                    # 本轮回复整段推送到平台（与参考 backend flush_assistant_round 一致）
                    await _push_flushed_assistant_segment()

                    # 没有工具调用 -> 正常结束
                    if not tool_calls:
                        break

                    # 有工具调用 -> 执行并回传
                    # 构建 assistant 消息（含 tool_calls）
                    assistant_tool_msg = {
                        "role": "assistant",
                        "content": content or None,
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": tc["arguments"],
                                },
                            }
                            for tc in tool_calls
                        ],
                    }
                    messages.append(assistant_tool_msg)

                    # 拆分：delegate_to_subagent 并行执行，其余工具串行
                    delegate_items: list[dict] = []
                    normal_calls: list[dict] = []
                    for tc in tool_calls:
                        tc_args = parse_tool_arguments(tc["arguments"])
                        if tc["name"] == "delegate_to_subagent":
                            delegate_items.append({
                                "tool_id": tc["id"],
                                "tool_name": tc["name"],
                                "sub_name": str(
                                    tc_args.get("subagent_name") or tc_args.get("agent_name") or ""
                                ).strip(),
                                "sub_task": str(tc_args.get("task") or "").strip(),
                                "sub_context": str(tc_args.get("context") or "").strip(),
                                "sub_isolation": str(tc_args.get("isolation") or "").strip(),
                                "args": tc_args,
                            })
                        else:
                            normal_calls.append(tc)

                    pending_images: list[tuple[str, str]] = []
                    for tc in normal_calls:
                        tc_id = tc["id"]
                        tc_name = tc["name"]
                        tc_args = parse_tool_arguments(tc["arguments"])

                        logger.write_tool_call(tc_id, tc_name, tc_args)

                        tool_context = {
                            "user_email": user_email,
                            "session_id": session_id,
                            "user_id": user_id,
                            "workspace_dir": session_workspace,
                        }
                        tool_result = await execute_tool(tc_name, tc_args, context=tool_context)

                        # tool 消息 content 始终为纯文本；图片剥离出来待注入
                        tool_content, images, log_text = _build_tool_content(tool_result, tc_args)
                        logger.write_tool_result(tc_id, tc_name, log_text)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": tool_content,
                        })
                        pending_images.extend(images)

                    # 图片作为单独 user 消息注入（兼容所有 API，tool 消息不支持 content array）
                    if pending_images:
                        user_content: list[dict] = [
                            {"type": "text", "text": "以下是读取到的图片，请根据图片内容进行分析："}
                        ]
                        for b64, mime in pending_images:
                            user_content.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            })
                        messages.append({"role": "user", "content": user_content})

                    if delegate_items:
                        async for sse in ChatService._run_delegates(
                            delegate_items=delegate_items,
                            user_email=user_email,
                            user_id=user_id,
                            session_id=session_id,
                            logger=logger,
                            messages=messages,
                            sse_queue=sse_queue,
                            cancel_event=cancel_event,
                            workspace_dir=session_workspace,
                        ):
                            yield sse

                    # flush SSE（tool_call/result 事件）
                    while sse_queue:
                        yield sse_queue.pop(0)

                    # 继续下一轮，让模型处理工具结果

            # finalize（若仍有未 flush 的尾段，补推一次）
            duration_ms = int((time.time() - start_ts) * 1000)
            await _push_flushed_assistant_segment()
            logger.finalize(duration_ms=duration_ms)
            while sse_queue:
                yield sse_queue.pop(0)

        except Exception as e:
            duration_ms = int((time.time() - start_ts) * 1000)
            await _push_flushed_assistant_segment()
            logger.finalize(duration_ms=duration_ms)
            while sse_queue:
                yield sse_queue.pop(0)
            yield f'data: {json.dumps({"type": "error", "error": str(e)})}\n\n'

        finally:
            # 流式结束：杀掉本次会话启动的所有后台进程
            killed = cleanup_session_processes(session_id)
            if killed:
                logger._emit({"type": "info", "message": f"已清理 {killed} 个后台进程"})

        yield "data: [DONE]\n\n"

    @staticmethod
    async def _run_delegates(
        *,
        delegate_items: list[dict],
        user_email: str,
        user_id: int,
        session_id: str,
        logger: SessionLogger,
        messages: list[dict],
        sse_queue: list[str],
        cancel_event: Optional[Any] = None,
        workspace_dir: str = "default",
    ) -> AsyncGenerator[str, None]:
        """并行执行 delegate_to_subagent，并把结果写回主对话。"""
        from app.engine.subagent_runtime import (
            format_subagent_result_for_main,
            run_subagent,
        )

        async def _on_event(payload: dict[str, Any]) -> None:
            sse_queue.append(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n")

        # asyncio.Event：兼容 threading.Event
        async_cancel: asyncio.Event | None = None
        if cancel_event is not None:
            async_cancel = asyncio.Event()

            async def _mirror_cancel() -> None:
                while True:
                    if getattr(cancel_event, "is_set", lambda: False)():
                        async_cancel.set()
                        return
                    await asyncio.sleep(0.2)

            mirror_task = asyncio.create_task(_mirror_cancel())
        else:
            mirror_task = None

        sub_futures: dict[asyncio.Task, dict] = {}
        for item in delegate_items:
            tool_id = item["tool_id"]
            sub_name = item["sub_name"]
            sub_task = item["sub_task"]
            logger.write_tool_call(tool_id, "delegate_to_subagent", item.get("args") or {})

            if not sub_name or not sub_task:
                err = (
                    "参数错误：subagent_name 不能为空。"
                    if not sub_name
                    else "参数错误：task 不能为空。"
                )
                fail = {"error": err, "status": "failed", "log_path": ""}
                formatted = format_subagent_result_for_main(fail)
                logger.write_subagent_block(
                    tool_call_id=tool_id,
                    subagent_name=sub_name or "(empty)",
                    task=sub_task or "(empty)",
                    status="failed",
                    error=err,
                )
                logger.write_tool_result(tool_id, "delegate_to_subagent", formatted, error=err)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": formatted,
                })
                continue

            logger.write_subagent_block(
                tool_call_id=tool_id,
                subagent_name=sub_name,
                task=sub_task,
                status="running",
            )
            task_obj = asyncio.create_task(
                run_subagent(
                    subagent_name=sub_name,
                    task=sub_task,
                    user_email=user_email,
                    context=item.get("sub_context") or "",
                    cancel_event=async_cancel,
                    on_event=_on_event,
                    session_id=session_id,
                    parent_tool_call_id=tool_id,
                    user_id=user_id,
                    workspace_dir=workspace_dir,
                )
            )
            sub_futures[task_obj] = item

        pending = set(sub_futures.keys())
        while pending:
            if cancel_event and getattr(cancel_event, "is_set", lambda: False)():
                for t in pending:
                    t.cancel()
                break
            done, pending = await asyncio.wait(pending, timeout=0.3)
            while sse_queue:
                yield sse_queue.pop(0)

        while sse_queue:
            yield sse_queue.pop(0)

        for task_obj, item in sub_futures.items():
            tool_id = item["tool_id"]
            sub_name = item["sub_name"]
            sub_task = item["sub_task"]
            try:
                sub_result = task_obj.result()
            except asyncio.CancelledError:
                sub_result = {
                    "error": "用户取消了子 Agent 任务",
                    "status": "cancelled",
                    "log_path": "",
                }
            except Exception as exc:
                sub_result = {
                    "error": f"子 Agent 异常：{exc}",
                    "status": "failed",
                    "log_path": "",
                }

            final_status = "success" if "result" in sub_result else sub_result.get("status", "failed")
            formatted = format_subagent_result_for_main(sub_result)
            logger.write_subagent_block(
                tool_call_id=tool_id,
                subagent_name=sub_name,
                task=sub_task,
                status=final_status,
                log_path=str(sub_result.get("log_path") or ""),
                final_output=str(sub_result.get("result") or formatted),
                error=str(sub_result.get("error") or ""),
            )
            logger.write_tool_result(
                tool_id,
                "delegate_to_subagent",
                formatted,
                error=str(sub_result.get("error") or ""),
            )
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": formatted,
            })
            yield f'data: {json.dumps({"type": "tool_result", "tool_name": "delegate_to_subagent", "tool_call_id": tool_id, "status": final_status, "output": formatted}, ensure_ascii=False)}\n\n'

        if mirror_task is not None:
            mirror_task.cancel()
            try:
                await mirror_task
            except (asyncio.CancelledError, Exception):
                pass
