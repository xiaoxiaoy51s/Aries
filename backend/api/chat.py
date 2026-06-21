import json
import base64
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, AsyncGenerator, Union, List
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx

from utils.url_utils import normalize_base_url
from utils.skills_manager import execute_tool
from utils.session_logger import SessionLogger
from models.model_manager import resolve_active_model_config
from db.sessions import upsert_session, get_session
from db.chat import save_message, update_message, get_memory_aware_context_messages
from utils.token_counter import build_token_usage_info, extract_usage_from_response
from prompt.code_review_prompts import (
    CODE_REVIEW_SYSTEM_PROMPT,
    CODE_REVIEW_USER_PROMPTS,
    CODE_REVIEW_MODES,
    DEPENDENCY_EXCLUDE_PATTERNS,
)

from api.modes import (
    build_agent_system_prompt,
    get_agent_skills_and_tools,
    stream_agent_mode,
    resolve_confirmation,
)
from services.chat_stream_manager import register as register_chat_stream, unregister as unregister_chat_stream, request_cancel as request_chat_cancel

router = APIRouter(prefix="/chat", tags=["chat"])


class ImageURL(BaseModel):
    url: str


class ImageContent(BaseModel):
    type: str = "image_url"
    image_url: ImageURL


class TextContent(BaseModel):
    type: str = "text"
    text: str


ContentPart = Union[TextContent, ImageContent]


class Message(BaseModel):
    role: str
    content: Optional[Union[str, List[ContentPart]]] = None
    name: Optional[str] = None
    tool_calls: Optional[list] = None
    tool_call_id: Optional[str] = None


class ToolFunction(BaseModel):
    name: str
    description: Optional[str] = ""
    parameters: Optional[dict] = None


class Tool(BaseModel):
    type: str = "function"
    function: ToolFunction


class ChatRequest(BaseModel):
    baseUrl: str = ""
    apiKey: str = ""
    model: str = ""
    messages: list[Message]
    session_id: Optional[str] = None
    work_dir: Optional[str] = None
    tools: Optional[list[Tool]] = None
    tool_choice: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = True
    public_url: Optional[str] = None


class VisionRequest(BaseModel):
    baseUrl: str = ""
    apiKey: str = ""
    model: str = ""
    text: str
    images: list[str]
    session_id: Optional[str] = None
    work_dir: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = True


def load_file_as_base64_url(file_path: str, mime_type: Optional[str] = None) -> str:
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()

    if not mime_type:
        ext = path.suffix.lower().lstrip(".")
        mime_map = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
        }
        mime_type = mime_map.get(ext, "application/octet-stream")

    return f"data:{mime_type};base64,{data}"


def save_base64_image(base64_str: str, upload_dir: str = None) -> str:
    if upload_dir is None:
        today = datetime.now().strftime("%Y/%m/%d")
        upload_path = Path.home() / ".Aries" / "uploads" / today
        url_prefix = f"/uploads/{today}"
    else:
        upload_path = Path(upload_dir)
        url_prefix = "/uploads"
    upload_path.mkdir(parents=True, exist_ok=True)

    match = re.match(r'^data:image/(\w+);base64,(.+)$', base64_str)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid base64 image format")

    ext = match.group(1)
    if ext == "jpeg":
        ext = "jpg"
    image_data = base64.b64decode(match.group(2))

    filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = upload_path / filename

    with open(file_path, "wb") as f:
        f.write(image_data)

    return f"{url_prefix}/{filename}"


CODE_REVIEW_MARKER_RE = re.compile(
    r"^@code_review(?:\s+(unstaged|staged|branch|commit|full))?(?:\s+|\n|$)",
    re.IGNORECASE,
)


def _extract_code_review_marker(text: str) -> tuple[Optional[str], str]:
    match = CODE_REVIEW_MARKER_RE.match(text or "")
    if not match:
        return None, text
    mode = (match.group(1) or "branch").lower()
    return mode, (text[match.end():] or "").lstrip()


def _detect_base_branch(work_dir: str) -> str:
    """自动检测默认基础分支名称。"""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, cwd=work_dir, timeout=5,
        )
        if result.returncode == 0:
            ref = result.stdout.strip()
            return ref.replace("refs/remotes/origin/", "") or "main"
    except Exception:
        pass
    # 兜底：检查 main / master 是否存在
    for branch in ("main", "master"):
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--verify", f"origin/{branch}"],
                capture_output=True, text=True, cwd=work_dir, timeout=5,
            )
            if r.returncode == 0:
                return branch
        except Exception:
            pass
    return "main"


def _fetch_review_diff(mode: str, work_dir: str) -> str:
    """根据审查模式预取 git diff，自动排除依赖文件。"""
    import subprocess

    if not work_dir:
        return "(无法获取工作目录，跳过 diff 预取)"

    if mode == "full":
        # 全面审查：返回项目结构概览而非 diff
        try:
            r = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                capture_output=True, text=True, cwd=work_dir, timeout=10,
            )
            files = r.stdout.strip().split("\n") if r.stdout.strip() else []
            # 排除依赖文件
            exclude_suffixes = (".lock", "-lock.json", ".min.js", ".min.css", ".map", ".pyc")
            exclude_dirs = ("node_modules", "__pycache__", "dist", "build", ".next", "vendor", "target")
            filtered = []
            for f in files:
                if not f:
                    continue
                if any(f.endswith(s) for s in exclude_suffixes):
                    continue
                if any(d in f for d in exclude_dirs):
                    continue
                filtered.append(f)
            return "\n".join(filtered[:200]) or "(未找到源代码文件)"
        except Exception as exc:
            return f"(获取项目结构失败: {exc})"

    # 构建 git diff 命令
    if mode == "unstaged":
        cmd = ["git", "diff"]
    elif mode == "staged":
        cmd = ["git", "diff", "--cached"]
    elif mode == "branch":
        base = _detect_base_branch(work_dir)
        cmd = ["git", "diff", f"origin/{base}...HEAD"]
    elif mode == "commit":
        cmd = ["git", "diff", "HEAD~1..HEAD"]
    else:
        cmd = ["git", "diff"]

    # 追加依赖排除 pathspec
    cmd.append("--")
    cmd.extend(DEPENDENCY_EXCLUDE_PATTERNS)

    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, cwd=work_dir, timeout=30,
        )
        diff = r.stdout.strip()
        if not diff:
            return "(未检测到代码变更)"
        # 截断超长 diff
        if len(diff) > 50000:
            diff = diff[:50000] + "\n\n...(diff 过长已截断，请聚焦已展示部分)..."
        return diff
    except subprocess.TimeoutExpired:
        return "(获取 diff 超时，请缩小审查范围)"
    except Exception as exc:
        return f"(获取 diff 失败: {exc})"


def _build_code_review_context(mode: str, work_dir: str | None = None) -> str:
    """构建代码审查的 system prompt 上下文。"""
    # 预取 diff
    diff_content = _fetch_review_diff(mode, work_dir or "")

    # 获取对应模式的 user prompt 模板
    user_prompt_template = CODE_REVIEW_USER_PROMPTS.get(mode, CODE_REVIEW_USER_PROMPTS["branch"])
    user_prompt = user_prompt_template.replace("{diff_content}", diff_content)

    mode_info = CODE_REVIEW_MODES.get(mode, {})
    mode_label = mode_info.get("label", mode)

    return (
        "\n# 代码审查模式\n"
        f"用户消息以 `@code_review {mode}` 开头，本轮必须按以下代码审查规则执行。\n"
        f"当前审查模式：{mode_label}\n\n"
        f"{CODE_REVIEW_SYSTEM_PROMPT}\n\n"
        f"{user_prompt}\n"
    )


def _replace_text_content(user_message: dict, text: str) -> None:
    if isinstance(user_message.get("content"), str):
        user_message["content"] = text


def extract_and_save_images(user_content) -> tuple:
    text_content = ""
    saved_paths = []

    if isinstance(user_content, list):
        text_parts = []
        for part in user_content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
                elif part.get("type") == "image_url":
                    image_url = part.get("image_url", {})
                    if isinstance(image_url, dict):
                        url = image_url.get("url", "")
                        if url.startswith("data:"):
                            file_path = save_base64_image(url)
                            saved_paths.append(file_path)
                        else:
                            saved_paths.append(url)
        text_content = " ".join(text_parts)
    elif isinstance(user_content, str):
        text_content = user_content

    return text_content, saved_paths


def prepare_messages(messages: list[Message]) -> list:
    result = []
    for msg in messages:
        msg_dict = {"role": msg.role}

        if msg.content is None:
            msg_dict["content"] = None
        elif isinstance(msg.content, str):
            msg_dict["content"] = msg.content
        elif isinstance(msg.content, list):
            content_parts = []
            for part in msg.content:
                if isinstance(part, dict):
                    content_parts.append(part)
                else:
                    content_parts.append(part.model_dump())
            msg_dict["content"] = content_parts

        if msg.name:
            msg_dict["name"] = msg.name
        if msg.tool_calls:
            msg_dict["tool_calls"] = msg.tool_calls
        if msg.tool_call_id:
            msg_dict["tool_call_id"] = msg.tool_call_id

        result.append(msg_dict)
    return result


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


class StopChatRequest(BaseModel):
    session_id: str


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
    code_review_mode, cleaned_text = _extract_code_review_marker(raw_text_content)
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
        system_prompt += _build_code_review_context(code_review_mode, effective_work_dir)

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

    async def disconnect_check():
        return await http_request.is_disconnected()

    try:
        # 仅下发轻量摘要，避免把消息分组泄露到前端 SSE
        _ctx_info = payload.get("context_token_info") or {}
        _ctx_summary = {
            "estimated_tokens": _ctx_info.get("estimated_tokens"),
            "context_window": _ctx_info.get("context_window"),
            "usage_percent": _ctx_info.get("usage_percent"),
        }
        yield f"data: {json.dumps({'context_token_usage': _ctx_summary}, ensure_ascii=False)}\n\n"
        async for event in stream_agent_mode(
            request,
            messages,
            headers,
            payload,
            session_id,
            work_dir=effective_work_dir,
            cancel_event=cancel_event,
            disconnect_check=disconnect_check,
        ):
            yield event
    finally:
        unregister_chat_stream(session_id)


@router.post("/stop")
async def stop_chat(body: StopChatRequest):
    session_id = (body.session_id or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id 不能为空")
    if request_chat_cancel(session_id):
        return {"status": "stopping", "message": "已请求停止生成"}
    return {"status": "idle", "message": "当前没有运行中的对话"}


@router.post("/completions")
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
    code_review_mode, cleaned_text = _extract_code_review_marker(raw_text_content)
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
        system_prompt += _build_code_review_context(code_review_mode, effective_work_dir)

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


@router.post("/vision")
async def chat_vision(request: VisionRequest, http_request: Request):
    content = []

    for image in request.images:
        if image.startswith("data:"):
            image_url = image
        elif image.startswith("http"):
            image_url = image
        else:
            image_url = load_file_as_base64_url(image)

        content.append({
            "type": "image_url",
            "image_url": {"url": image_url}
        })

    content.append({
        "type": "text",
        "text": request.text
    })

    messages = [{"role": "user", "content": content}]

    chat_req = ChatRequest(
        baseUrl=request.baseUrl,
        apiKey=request.apiKey,
        model=request.model,
        messages=messages,
        session_id=request.session_id,
        work_dir=request.work_dir,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        stream=request.stream,
    )

    return await chat_completions(chat_req, http_request)


@router.get("/sessions/recent")
async def get_recent_sessions(limit: int = 30):
    from db.chat import list_recent_sessions
    sessions = list_recent_sessions(limit=limit)
    return sessions


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, limit: int = 100):
    from db.chat import get_session_messages as get_messages
    messages = get_messages(session_id, limit=limit)
    return messages


class ConfirmToolRequest(BaseModel):
    tool_call_id: str
    confirmed: bool = True


@router.post("/confirm-tool")
async def confirm_tool(req: ConfirmToolRequest):
    ok = resolve_confirmation(req.tool_call_id, req.confirmed)
    if not ok:
        raise HTTPException(status_code=404, detail="未找到待确认的工具调用")
    return {"status": "ok", "confirmed": req.confirmed}


class TempChatRequest(BaseModel):
    messages: list[Message]  # 临时对话的全部消息（含本轮 user）
    session_id: Optional[str] = None  # 用于加载上下文记忆
    work_dir: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@router.post("/temp")
async def temp_chat(req: TempChatRequest, http_request: Request):
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
