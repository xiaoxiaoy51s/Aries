"""基础对话流模块"""
import json
import uuid
from typing import AsyncGenerator
from uuid import uuid4

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from utils.url_utils import normalize_base_url
from engine.skills_manager import execute_tool
from utils.session_logger import SessionLogger
from models.model_manager import resolve_active_model_config
from db.sessions import upsert_session, get_session
from db.chat import save_message, update_message, get_memory_aware_context_messages
from utils.token_counter import build_token_usage_info, extract_usage_from_response

from api.engine import (
    build_agent_system_prompt,
    get_agent_skills_and_tools,
    stream_agent_mode,
)

from .models import ChatRequest
from .utils import (
    extract_and_save_images,
    prepare_messages,
    _replace_text_content,
)
from .code_review import extract_code_review_marker, build_code_review_context
from .background import (
    register_chat_stream,
    stream_chat_with_background,
    _background_tasks,
)


def _resolve_chat_request(request: ChatRequest) -> ChatRequest:
    base_url, api_key, model = resolve_active_model_config(
        request.baseUrl,
        request.apiKey,
        request.model,
    )
    if not base_url or not api_key:
        raise HTTPException(
            status_code=400,
            detail="未配置模型 API，请先在设置中配置 baseUrl 和 apiKey",
        )
    return request.model_copy(update={"baseUrl": base_url, "apiKey": api_key, "model": model})


async def stream_chat(request: ChatRequest, http_request: Request) -> AsyncGenerator[str, None]:
    request = _resolve_chat_request(request)

    session_id = request.session_id or uuid4().hex
    is_new_session = not request.session_id

    # 首次创建 session 时写入 work_dir（仅当客户端提供）
    if is_new_session and request.work_dir:
        upsert_session(session_id=session_id, work_dir=request.work_dir)
    elif request.session_id and request.work_dir:
        upsert_session(session_id=request.session_id, work_dir=request.work_dir)

    # 提前保存用户消息，便于后续从数据库加载上下文
    prepared = prepare_messages(request.messages)
    user_message = prepared[-1] if prepared else {}
    user_content = user_message.get("content", "") if isinstance(user_message, dict) else ""
    raw_text_content, saved_paths = extract_and_save_images(user_content)
    code_review_mode, cleaned_text = extract_code_review_marker(raw_text_content)
    if code_review_mode:
        _replace_text_content(user_message, cleaned_text or "请开始代码审查。")
    images_json = json.dumps(saved_paths, ensure_ascii=False) if saved_paths else None
    if raw_text_content or images_json or code_review_mode:
        save_message(session_id, "user", raw_text_content or "", image_path=images_json, mode="agent")
        # 新会话的第一条用户消息作为标题（18字+省略号）
        if is_new_session:
            if code_review_mode:
                upsert_session(session_id=session_id, title="代码审查")
            elif raw_text_content.strip():
                raw = raw_text_content.strip().replace("\n", " ")[:18]
                title = raw + ("…" if len(raw_text_content.strip()) > 18 else "")
                upsert_session(session_id=session_id, title=title or "新对话")

    # 从数据库加载 memory-aware 上下文：长期压缩记忆 + 最近 token 窗口 + 最近工作记录
    history_messages, context_token_info = get_memory_aware_context_messages(
        session_id=session_id,
        current_user_text=raw_text_content,
        model=request.model,
    )
    # 当前用户消息可能带图片，这里以原始 prepared 形式追加（含 images 字段）
    current_user_msg = prepared[-1] if prepared else None

    skills_context, tool_definitions, mcp_context, subagents_context = get_agent_skills_and_tools()
    # 取该 session 的工作目录（DB 优先，request 兜底）
    _meta = get_session(session_id) or {}
    effective_work_dir = (_meta.get("work_dir") or request.work_dir or "").strip() or None
    system_prompt = build_agent_system_prompt(
        skills_context,
        work_dir=effective_work_dir,
        session_id=session_id,
        mcp_context=mcp_context,
        subagents_context=subagents_context,
    )
    if code_review_mode:
        system_prompt += build_code_review_context(code_review_mode, effective_work_dir)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages)
    if current_user_msg:
        messages.append(current_user_msg)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {request.apiKey}",
    }

    payload = {
        "model": request.model,
        "messages": messages,
        "stream": True,
    }

    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens

    payload["context_token_info"] = build_token_usage_info(messages, model=request.model)
    payload["context_token_info"].update({
        "memory_context": context_token_info,
    })
    # 透传 memory-aware 上下文消息分组，供 stream_agent_mode 组装功能模块化 breakdown
    payload["context_breakdown_inputs"] = {
        "summarized_messages": context_token_info.get("summarized_messages") or [],
        "conversation_messages": context_token_info.get("conversation_messages") or [],
        "recent_message_count": context_token_info.get("recent_message_count"),
        "memory_count": context_token_info.get("memory_count"),
        "reasoning_count": context_token_info.get("reasoning_count"),
    }

    cancel_event = register_chat_stream(session_id)

    # 使用后台任务管理器
    async for event in stream_chat_with_background(
        request, messages, headers, payload, session_id, effective_work_dir, cancel_event, http_request
    ):
        yield event


async def chat_completions(request: ChatRequest, http_request: Request):
    request = _resolve_chat_request(request)

    if request.stream:
        return StreamingResponse(
            stream_chat(request, http_request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    session_id = request.session_id or uuid4().hex
    is_new_session = not request.session_id
    if is_new_session and request.work_dir:
        upsert_session(session_id=session_id, work_dir=request.work_dir)
    elif request.session_id and request.work_dir:
        upsert_session(session_id=request.session_id, work_dir=request.work_dir)

    # 提前保存用户消息，便于后续从数据库加载上下文
    prepared = prepare_messages(request.messages)
    user_message = prepared[-1] if prepared else {}
    user_content = user_message.get("content", "") if isinstance(user_message, dict) else ""
    raw_text_content, saved_paths = extract_and_save_images(user_content)
    code_review_mode, cleaned_text = extract_code_review_marker(raw_text_content)
    if code_review_mode:
        _replace_text_content(user_message, cleaned_text or "请开始代码审查。")
    images_json = json.dumps(saved_paths, ensure_ascii=False) if saved_paths else None
    if raw_text_content or images_json or code_review_mode:
        save_message(session_id, "user", raw_text_content or "", image_path=images_json, mode="agent")

    # 从数据库加载 memory-aware 上下文：长期压缩记忆 + 最近 token 窗口 + 最近工作记录
    history_messages, context_token_info = get_memory_aware_context_messages(
        session_id=session_id,
        current_user_text=raw_text_content,
        model=request.model,
    )
    current_user_msg = prepared[-1] if prepared else None

    skills_context, tool_definitions, mcp_context, subagents_context = get_agent_skills_and_tools()
    # 取该 session 的工作目录（DB 优先，request 兜底）
    _meta = get_session(session_id) or {}
    effective_work_dir = (_meta.get("work_dir") or request.work_dir or "").strip() or None
    system_prompt = build_agent_system_prompt(
        skills_context,
        work_dir=effective_work_dir,
        session_id=session_id,
        mcp_context=mcp_context,
        subagents_context=subagents_context,
    )
    if code_review_mode:
        system_prompt += build_code_review_context(code_review_mode, effective_work_dir)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history_messages)
    if current_user_msg:
        messages.append(current_user_msg)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {request.apiKey}",
    }

    payload = {
        "model": request.model,
        "messages": messages,
        "stream": False,
    }

    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens

    if tool_definitions:
        payload["tools"] = tool_definitions
        payload["tool_choice"] = "auto"
    elif request.tools:
        payload["tools"] = [tool.model_dump() for tool in request.tools]
    if request.tool_choice:
        payload["tool_choice"] = request.tool_choice

    assistant_message_id = save_message(
        session_id, "assistant", "", message_snapshot_json="", mode="agent"
    )
    logger = SessionLogger(session_id=session_id, message_id=assistant_message_id)
    logger.set_model(request.model)
    logger.set_token_usage({
        "context": build_token_usage_info(messages, model=request.model),
        "memory_context": context_token_info,
    })

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{normalize_base_url(request.baseUrl)}/chat/completions",
            headers=headers,
            json=payload,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.text)

        result = response.json()
        logger.add_token_usage(extract_usage_from_response(result))

        message = result.get("choices", [{}])[0].get("message", {})
        assistant_content = message.get("content", "") or ""
        raw_reasoning = message.get("reasoning_content", "") or ""
        if raw_reasoning:
            logger.append_reasoning_delta(raw_reasoning)
            logger.flush_reasoning_segment()
        if assistant_content:
            logger.record_assistant_content(assistant_content)

        if "tool_calls" in message:
            # 第一轮工作说明落盘（多轮工具调用时，避免中间轮次丢失）
            logger.flush_assistant_round()

            tool_results = []
            for call_index, tool_call in enumerate(message["tool_calls"]):
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"]) if tool_call["function"]["arguments"] else {}
                tool_call_id = tool_call.get("id", "") or f"tool_0_{call_index}"

                logger.write_tool_call(tool_call_id, tool_name, tool_args)
                tool_result = execute_tool(
                    tool_name, tool_args, work_dir=effective_work_dir, session_id=session_id
                )

                tool_status = "completed" if tool_result.get("success") else "error"
                logger.write_tool_result(
                    tool_call_id,
                    tool_name,
                    tool_status,
                    result=tool_result.get("output", "") or "",
                    error=tool_result.get("error", "") or "",
                    session_id=tool_result.get("session_id", "") or "",
                )

                tool_results.append({
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "result": tool_result,
                })

                messages.append({
                    "role": "assistant",
                    "content": assistant_content,
                    "tool_calls": [tool_call],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": tool_result.get("output", "") or tool_result.get("error", ""),
                })

            payload["messages"] = messages
            payload["stream"] = False

            follow_up_response = await client.post(
                f"{normalize_base_url(request.baseUrl)}/chat/completions",
                headers=headers,
                json=payload,
            )
            if follow_up_response.status_code != 200:
                raise HTTPException(status_code=follow_up_response.status_code, detail=follow_up_response.text)

            final_result = follow_up_response.json()
            logger.add_token_usage(extract_usage_from_response(final_result))
            final_message = final_result.get("choices", [{}])[0].get("message", {})
            assistant_content = final_message.get("content", "") or ""
            raw_reasoning = final_message.get("reasoning_content", "") or ""
            if raw_reasoning:
                logger.append_reasoning_delta(raw_reasoning)
                logger.flush_reasoning_segment()
            if assistant_content:
                logger.record_assistant_content(assistant_content)

            result = final_result
            if tool_results:
                result["tool_results"] = tool_results

        if assistant_content:
            logger.write_assistant_segment(assistant_content)

        result["context_token_usage"] = {
            "context": build_token_usage_info(messages, model=request.model),
            "memory_context": context_token_info,
        }

        update_message(
            assistant_message_id,
            content=assistant_content or "（无响应）",
            message_snapshot_json=logger.jsonl_path_str(),
            reasoning_content=logger.build_db_reasoning(),
        )

        logger.finalize()

        return result


async def temp_chat(req, http_request: Request):
    """临时对话：加载 session 上下文 + 临时消息，流式返回，不存 DB。"""
    base_url, api_key, model = resolve_active_model_config()
    if not base_url or not api_key:
        raise HTTPException(status_code=400, detail="未配置模型 API")

    # 构建 system prompt
    skills_context, _, mcp_context, subagents_context = get_agent_skills_and_tools()
    _meta = get_session(req.session_id) if req.session_id else {}
    effective_work_dir = (_meta.get("work_dir") or req.work_dir or "").strip() or None
    system_prompt = build_agent_system_prompt(
        skills_context, work_dir=effective_work_dir,
        session_id=req.session_id, mcp_context=mcp_context,
        subagents_context=subagents_context,
    )

    messages = [{"role": "system", "content": system_prompt}]

    # 加载 session 的记忆上下文（如果有 session_id）
    if req.session_id:
        user_text = ""
        for m in reversed(req.messages):
            if m.role == "user":
                user_text = m.content if isinstance(m.content, str) else ""
                break
        history_messages, _ = get_memory_aware_context_messages(
            session_id=req.session_id,
            current_user_text=user_text,
            model=model,
        )
        messages.extend(history_messages)

    # 追加临时消息（前端传入的全部临时对话消息）
    for m in req.messages:
        msg_dict = {"role": m.role}
        if isinstance(m.content, str):
            msg_dict["content"] = m.content
        elif isinstance(m.content, list):
            msg_dict["content"] = [p.model_dump() if not isinstance(p, dict) else p for p in m.content]
        else:
            msg_dict["content"] = m.content
        messages.append(msg_dict)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if req.temperature is not None:
        payload["temperature"] = req.temperature
    if req.max_tokens is not None:
        payload["max_tokens"] = req.max_tokens

    async def stream_temp():
        timeout = httpx.Timeout(connect=30.0, read=900.0, write=120.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            async with client.stream(
                "POST",
                f"{normalize_base_url(base_url)}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    yield f"data: {json.dumps({'error': error_text.decode()})}\n\n"
                    return
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            yield "data: [DONE]\n\n"
                            return
                        try:
                            chunk = json.loads(data)
                            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                        except json.JSONDecodeError:
                            continue

    return StreamingResponse(
        stream_temp(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )