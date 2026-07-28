import json
import time
import uuid
import httpx
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.context_loader import build_context_messages
from app.repository.session_repository import MessageRepository
from app.service.model_config_service import ModelConfigService
from app.service.session_service import SessionService
from app.tools.registry import get_tool_schemas, execute_tool, parse_tool_arguments
from app.tools.sandbox import cleanup_session_processes
from app.utils.session_logger import SessionLogger
from app.utils.token_counter import normalize_api_usage


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
    ) -> AsyncGenerator[str, None]:
        """流式对话 + 工具调用循环。

        当模型返回 tool_calls 时，执行工具并将结果回传给模型，循环直到
        模型不再请求工具或达到 max_tool_rounds 上限。
        """

        # 1. 获取模型配置
        model = await ChatService._resolve_model(user_email)
        if not model:
            yield f'data: {json.dumps({"type": "error", "error": "尚未配置模型，请先在设置中添加模型。"})}\n\n'
            yield "data: [DONE]\n\n"
            return

        max_rounds = getattr(model, "max_tool_rounds", 100) or 100

        # 2. 创建或获取 session
        if not session_id:
            session_id = f"sess-{uuid.uuid4().hex[:12]}"
            title = message[:30].replace("\n", " ") + ("..." if len(message) > 30 else "")
            await SessionService.create_session(db, session_id, user_id, title)
        else:
            session = await SessionService.get_session(db, session_id)
            if not session:
                title = message[:30].replace("\n", " ") + ("..." if len(message) > 30 else "")
                await SessionService.create_session(db, session_id, user_id, title)

        # 3. 推送 session_id
        yield f'data: {json.dumps({"type": "session", "session_id": session_id})}\n\n'

        # 4. 写入用户消息
        user_msg = await MessageRepository.create(
            db, session_id=session_id, user_id=user_id, role="user", log_path=""
        )
        user_logger = SessionLogger(user_email, session_id, user_msg.id)
        user_logger.write_user_message(message, [])
        await MessageRepository.update_log_path(db, user_msg.id, user_logger.jsonl_path_str)
        user_logger.finalize()

        # 5. 创建 assistant 消息 + logger
        assistant_msg = await MessageRepository.create(
            db, session_id=session_id, user_id=user_id, role="assistant", log_path=""
        )

        sse_queue: list[str] = []

        def on_event(event: dict):
            sse_queue.append(f"data: {json.dumps(event, ensure_ascii=False)}\n\n")

        logger = SessionLogger(user_email, session_id, assistant_msg.id, on_event=on_event)
        logger.set_model(model.model)
        await MessageRepository.update_log_path(db, assistant_msg.id, logger.jsonl_path_str)

        # 6. 构建上下文
        db_messages = await SessionService.get_messages(db, session_id)
        messages, context_info = build_context_messages(
            db_messages=db_messages,
            current_user_text=message,
            model=model.model,
        )
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
        start_ts = time.time()

        try:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                for round_num in range(max_rounds + 1):
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

                    # 执行每个工具
                    for tc in tool_calls:
                        tc_id = tc["id"]
                        tc_name = tc["name"]
                        tc_args = parse_tool_arguments(tc["arguments"])

                        # 记录 tool_call 事件
                        logger.write_tool_call(tc_id, tc_name, tc_args)

                        # 执行工具（传入用户上下文，shell 工具需要确定工作区）
                        tool_context = {
                            "user_email": user_email,
                            "session_id": session_id,
                            "user_id": user_id,
                        }
                        tool_result = await execute_tool(tc_name, tc_args, context=tool_context)

                        # 记录 tool_result 事件
                        logger.write_tool_result(tc_id, tc_name, tool_result)

                        # 添加 tool 消息到上下文
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": tool_result,
                        })

                    # flush SSE（tool_call/result 事件）
                    while sse_queue:
                        yield sse_queue.pop(0)

                    # 继续下一轮，让模型处理工具结果

            # finalize
            duration_ms = int((time.time() - start_ts) * 1000)
            logger.finalize(duration_ms=duration_ms)
            while sse_queue:
                yield sse_queue.pop(0)

        except Exception as e:
            duration_ms = int((time.time() - start_ts) * 1000)
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
