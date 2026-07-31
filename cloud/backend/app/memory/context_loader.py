"""上下文构建器。

全量加载对话历史，从 JSONL 重建消息内容，不上传 reasoning_content。
提供 token 用量预估和缓存命中统计。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.utils.session_logger import read_jsonl_events, reconstruct_from_events
from app.utils.token_counter import build_context_token_info


def _build_user_content(text: str, image_urls: list[str] | None = None) -> str | list[dict[str, Any]]:
    """构建 user 消息 content，支持纯文本或多模态（text + image_url）。"""
    urls = [u for u in (image_urls or []) if u]
    clean_text = (text or "").strip()
    if not urls:
        return clean_text
    parts: list[dict[str, Any]] = []
    if clean_text:
        parts.append({"type": "text", "text": clean_text})
    for url in urls:
        parts.append({"type": "image_url", "image_url": {"url": url}})
    if not parts:
        parts.append({"type": "text", "text": "请描述这张图片的内容"})
    return parts


def _extract_user_parts(content: Any) -> tuple[str, list[str]]:
    if isinstance(content, str):
        return content.strip(), []
    if isinstance(content, list):
        text_parts: list[str] = []
        urls: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                text_parts.append(part.get("text", ""))
            elif part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url", "")
                if url:
                    urls.append(url)
        return "".join(text_parts).strip(), urls
    return "", []


def _build_api_messages(
    db_messages: list[dict[str, Any]],
    current_user_text: str,
    current_user_images: list[str] | None = None,
) -> list[dict[str, Any]]:
    """从数据库消息列表构建 API 消息序列。

    规则：
    - 不上传 reasoning_content
    - user 消息直接取 content
    - assistant 消息从 JSONL 重建
    - 去掉与 current_user_text 重复的最后一条 user 消息
    """
    result: list[dict[str, Any]] = []

    for msg in db_messages:
        role = msg.get("role", "")
        if role == "user":
            content = (msg.get("content") or "").strip()
            image_urls = msg.get("image_urls") or []
            user_content = _build_user_content(content, image_urls)
            if user_content:
                result.append({"role": "user", "content": user_content})
        elif role == "assistant":
            # 从 JSONL 重建
            log_path = msg.get("log_path") or ""
            content_text = ""
            if log_path:
                events = read_jsonl_events(log_path)
                reconstructed = reconstruct_from_events(events)
                content_text = (reconstructed.get("assistant_content") or "").strip()
            if not content_text:
                content_text = (msg.get("content") or "").strip()
            if content_text:
                result.append({"role": "assistant", "content": content_text})

    # 去掉与当前用户消息重复的最后一条 user 消息
    cur_text = (current_user_text or "").strip()
    cur_images = [u for u in (current_user_images or []) if u]
    if result:
        last = result[-1]
        if last.get("role") == "user":
            last_text, last_images = _extract_user_parts(last.get("content"))
            if last_text == cur_text and last_images == cur_images:
                result = result[:-1]

    return result


_PLATFORM_LABELS = {"qq": "QQ", "wechat": "微信", "feishu": "飞书"}


def build_context_messages(
    db_messages: list[dict[str, Any]],
    current_user_text: str = "",
    current_user_images: list[str] | None = None,
    model: str = "",
    platform: str = "",
    user_email: str = "",
    as_agent: str = "",
    workspace_dir: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """构建完整的上下文消息列表（含 system prompt + 历史 + 当前用户消息）。

    as_agent 非空时：以该子 Agent 的 system_prompt 作为主对话提示词，
    不再注入 Available Subagents 路由表（当前身份就是该 Agent）。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    system_parts: list[str] = []

    agent_entry = None
    if as_agent and user_email:
        try:
            from app.engine.subagent_manager import get_subagent_by_name

            agent_entry = get_subagent_by_name(as_agent, user_email)
        except Exception:
            agent_entry = None

    if agent_entry:
        system_parts.append(
            f"你是 Aries Cloud 中的智能体 `{agent_entry.name}`。"
            f"Today's date is {today}."
        )
        if agent_entry.description:
            system_parts.append(f"职责：{agent_entry.description}")
        if agent_entry.system_prompt.strip():
            system_parts.append(agent_entry.system_prompt.strip())
        system_parts.append(
            "你当前以主对话身份运行（不是被委派的子 Agent），直接与用户对话并完成任务；"
            "无需调用 report_to_main。"
        )
        try:
            from app.engine.skills_manager import build_skills_prompt_section

            skills_section = build_skills_prompt_section(
                user_email or None,
                for_main=False,
                allowed_names=agent_entry.allowed_skills,
            )
            if skills_section:
                system_parts.append(skills_section)
        except Exception:
            pass
    else:
        system_parts.extend([
            "You are Aries Cloud, a helpful AI assistant.",
            f"Today's date is {today}.",
        ])
        if platform:
            label = _PLATFORM_LABELS.get(platform, platform)
            system_parts.append(
                f"当前对话来自{label}。"
                f"直接回复即可，系统会自动把你的回复送达{label}，无需调用工具；"
                f"仅在需要主动推送（如定时任务结果）时才调用 send_message_to_user 并指定 platform。"
                f"创建定时任务时默认写入{label}会话。"
            )
        try:
            from app.engine.subagent_manager import build_subagent_router_section

            subagents_section = build_subagent_router_section(user_email or None)
            if subagents_section:
                system_parts.append(subagents_section)
        except Exception:
            pass
        try:
            from app.engine.skills_manager import build_skills_prompt_section

            skills_section = build_skills_prompt_section(user_email or None, for_main=True)
            if skills_section:
                system_parts.append(skills_section)
        except Exception:
            pass

    # 工作目录信息：让 AI 知道当前会话绑定的沙箱目录，无需自行 pwd 探测
    ws = (workspace_dir or "default").strip() or "default"
    try:
        from app.tools.sandbox import ensure_workspace

        ws_path = str(ensure_workspace(user_email, ws))
    except Exception:
        ws_path = ws
    system_parts.append(
        f"当前会话的工作目录为 {ws_path}。"
        "你的 shell 命令与文件读写都在该目录下进行（沙箱隔离，仅限该目录）；"
        "用户上传的文件也存放在此目录。处理文件相关请求时默认基于此目录，无需 pwd 探测。"
    )

    # 专用 CLI 工具说明：告诉 AI 特定任务必须使用对应命令行工具
    system_parts.append(
        "【专用 CLI 工具】以下任务必须使用对应的命令行工具，不要用 Python 库或自写代码替代：\n"
        "- 修改/编辑 Office 文档（.xlsx/.docx/.pptx）：必须使用 officecli 工具。"
        "先运行 `officecli --help` 查看全部命令；常用操作如 `officecli get/set/add/remove` 修改文档节点、"
        "`officecli view <file> text` 读取文本、`officecli watch <file>` 启动预览，"
        "修改完成后用 `officecli save <file>` 或 `officecli close <file>` 落盘。\n"
        "- 浏览器控制（网页爬取、网页点击、表单填写、截图等）：必须使用 playwright CLI 工具，"
        "不要使用 requests/httpx 等纯 HTTP 库替代。先运行 `playwright --help` 或对应子命令的 `--help` "
        "确认支持的功能与参数后再执行。\n"
        "- 使用任何 CLI 工具前，先执行 `命令 --help` 确认对应功能与参数，避免臆测用法。"
    )

    system_msg: dict[str, Any] = {
        "role": "system",
        "content": "\n".join(system_parts),
    }

    # 2. 历史消息
    history_messages = _build_api_messages(db_messages, current_user_text, current_user_images)

    # 3. 当前用户消息
    user_msg = {"role": "user", "content": _build_user_content(current_user_text, current_user_images)}

    # 4. 组装完整消息列表
    messages = [system_msg] + history_messages + [user_msg]

    # 5. token 统计（不含当前 user_msg，只算已发送的上下文）
    context_token_info = build_context_token_info(
        [system_msg] + history_messages,
        model=model,
    )

    return messages, context_token_info
