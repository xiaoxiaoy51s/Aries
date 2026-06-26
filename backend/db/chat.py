import sqlite3
from .database import get_connection
from utils.session_logger import resolve_message_log_events


def save_message(
    session_id: str,
    role: str,
    content: str,
    reasoning_content: str = None,
    image_path: str = None,
    message_snapshot_json: str = None,
    mode: str = "agent",
) -> int:
    conn = get_connection()
    effective_mode = (mode or "agent").strip().lower() or "agent"

    cursor = conn.execute(
        """
        INSERT INTO chat_messages (session_id, role, content, reasoning_content, image_path, message_snapshot_json, mode)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, role, content, reasoning_content, image_path, message_snapshot_json, effective_mode),
    )
    conn.commit()
    return int(cursor.lastrowid)


def update_message(
    message_id: int,
    *,
    content: str | None = None,
    reasoning_content: str | None = None,
    image_path: str | None = None,
    message_snapshot_json: str | None = None,
) -> None:
    updates: list[str] = []
    values: list[str | int | None] = []

    if content is not None:
        updates.append("content = ?")
        values.append(content)
    if reasoning_content is not None:
        updates.append("reasoning_content = ?")
        values.append(reasoning_content)
    if image_path is not None:
        updates.append("image_path = ?")
        values.append(image_path)
    if message_snapshot_json is not None:
        updates.append("message_snapshot_json = ?")
        values.append(message_snapshot_json)

    if not updates:
        return

    values.append(message_id)
    conn = get_connection()
    conn.execute(f"UPDATE chat_messages SET {', '.join(updates)} WHERE id = ?", values)
    conn.commit()


def get_chat_context_messages(
    session_id: str,
    message_limit: int = 28,
    reasoning_rounds: int = 3,
    max_assistant_len: int = 800,
) -> list[dict]:
    """获取最近 message_limit 条消息 + reasoning_rounds 轮深度思考，
    按对话顺序合并为 LLM 调用上下文（reasoning 以 system 消息置于最前）。

    说明：
    - 消息按时间正序返回（最旧在前、最新在后）。
    - 当 assistant 单条 content 超过 max_assistant_len 时会被截断，避免上下文过长。
    - 仅保留 role in {user, assistant} 的消息，过滤掉空内容。
    """
    messages = get_recent_messages(session_id, limit=message_limit)
    reasoning_list = get_recent_agent_reasoning(session_id, rounds=reasoning_rounds)

    result: list[dict] = []
    if reasoning_list:
        parts = [f"【第{i}轮工作记录】\n{text}" for i, text in enumerate(reasoning_list, 1)]
        result.append({
            "role": "system",
            "content": (
                "以下是你在本对话中最近的工作进展记录（用户不可见，供你接续任务时参考，避免重复劳动或迷失进度）：\n\n"
                + "\n\n".join(parts)
            ),
        })

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role not in ("user", "assistant"):
            continue
        if not content or not content.strip():
            continue
        if role == "assistant" and len(content) > max_assistant_len:
            content = content[:max_assistant_len] + "\n...(内容已截断)"
        result.append({"role": role, "content": content})

    return result


def get_recent_messages(session_id: str, limit: int = 20) -> list[dict]:
    return get_messages_after_id(session_id, after_id=0, limit=limit)


def get_messages_after_id(session_id: str, after_id: int = 0, limit: int = 200) -> list[dict]:
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT id, role, content, reasoning_content, image_path, message_snapshot_json, mode
        FROM chat_messages
        WHERE session_id = ? AND id > ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (session_id, after_id, limit),
    ).fetchall()

    rows = list(rows)
    rows.reverse()

    result = []
    for row in rows:
        item = {
            "id": row[0],
            "role": row[1],
            "content": row[2],
            "reasoning_content": row[3],
            "image_path": row[4],
            "message_snapshot_json": row[5] or None,
            "mode": row[6] or "agent",
        }
        result.append(item)
    return result


def _truncate_context_text(text: str, limit: int = 6000) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...(内容已截断)"


def build_work_trace_from_events(events: list[dict]) -> str:
    """从 JSONL 事件重建一轮工作记录：按时间顺序仅保留深度思考 + 最终回复。

    去掉 tool_call / tool_result，避免日志冗长导致 AI 上下文混乱。
    """
    lines: list[str] = []
    for event in events:
        event_type = event.get("type")
        if event_type == "reasoning_text":
            text = (event.get("text") or "").strip()
            if text:
                lines.append("【深度思考】\n" + _truncate_context_text(text))
        elif event_type == "assistant_text":
            text = (event.get("text") or "").strip()
            if text:
                lines.append("【最终回复】\n" + _truncate_context_text(text, 3000))
    return "\n\n".join(lines).strip()


def get_recent_agent_reasoning(session_id: str, rounds: int = 3) -> list[str]:
    """取最近 N 轮 assistant 工作记录，包含深度思考和最终回复（按时间顺序）。"""
    db_msgs = get_recent_messages(session_id, limit=80)
    trace_list: list[str] = []
    for msg in db_msgs:
        if msg.get("role") != "assistant":
            continue
        events = resolve_message_log_events(msg.get("message_snapshot_json"))
        trace = build_work_trace_from_events(events) if events else ""
        if not trace:
            reasoning = (msg.get("reasoning_content") or "").strip()
            content = (msg.get("content") or "").strip()
            parts = []
            if reasoning:
                parts.append("【深度思考】\n" + _truncate_context_text(reasoning))
            if content:
                parts.append("【最终回复】\n" + _truncate_context_text(content, 3000))
            trace = "\n\n".join(parts)
        if trace:
            trace_list.append(trace)
    return trace_list[-rounds:]


def build_agent_reasoning_context(session_id: str, rounds: int = 3) -> dict | None:
    """将最近 N 轮 agent 工作记录包装为 system 消息。"""
    recent = get_recent_agent_reasoning(session_id, rounds=rounds)
    if not recent:
        return None
    parts = [f"【第{i}轮工作记录】\n{text}" for i, text in enumerate(recent, 1)]
    return {
        "role": "system",
        "content": (
            "以下是你在本对话中最近的工作进展记录（用户不可见，供你接续任务时参考，避免重复劳动或迷失进度）：\n\n"
            + "\n\n".join(parts)
        ),
    }


def compact_session_if_needed(session_id: str, force: bool = False) -> dict | None:
    from memory.compaction import make_memory_record, should_compact, split_messages_for_compaction

    boundary = get_latest_memory_boundary(session_id)
    db_messages = get_messages_after_id(session_id, after_id=boundary, limit=200)
    llm_messages = []
    max_id = boundary
    for msg in db_messages:
        max_id = max(max_id, int(msg.get("id") or 0))
        role = msg.get("role")
        content = msg.get("content") or ""
        if role in ("user", "assistant") and content.strip():
            llm_messages.append({"role": role, "content": content})

    if not force and not should_compact(llm_messages):
        return None

    to_compact, _ = split_messages_for_compaction(llm_messages)
    if not to_compact:
        return None

    compact_until_count = len(to_compact)
    compact_until_id = boundary
    seen = 0
    for msg in db_messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role in ("user", "assistant") and content.strip():
            seen += 1
            compact_until_id = int(msg.get("id") or compact_until_id)
            if seen >= compact_until_count:
                break

    memory = make_memory_record(session_id, to_compact)
    memory["source_until_message_id"] = compact_until_id
    memory_id = save_session_memory(memory)
    memory["id"] = memory_id
    return memory


def get_memory_aware_context_messages(
    session_id: str,
    current_user_text: str = "",
    model: str = "",
) -> tuple[list[dict], dict]:
    from memory.context_loader import build_context_messages

    compact_session_if_needed(session_id)
    boundary = get_latest_memory_boundary(session_id)
    db_messages = get_messages_after_id(session_id, after_id=boundary, limit=120)
    memories = get_session_memories(session_id, limit=3)
    reasoning_list = get_recent_agent_reasoning(session_id, rounds=3)
    return build_context_messages(
        db_messages=db_messages,
        memories=memories,
        reasoning_list=reasoning_list,
        current_user_text=current_user_text,
        model=model,
    )


def get_conversation_history(
    session_id: str,
    limit: int = 20,
    max_assistant_len: int = 800,
    user_only: bool = False,
    include_last: bool = False,
) -> list[dict]:
    fetch_limit = limit if include_last else limit + 1
    all_msgs = get_recent_messages(session_id, limit=fetch_limit)
    history_msgs = all_msgs if include_last else (all_msgs[:-1] if all_msgs else [])

    history: list[dict] = []
    for msg in history_msgs:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role not in ("user", "assistant"):
            continue
        if not content or not content.strip():
            continue
        if user_only and role != "user":
            continue
        if role == "assistant" and len(content) > max_assistant_len:
            content = content[:max_assistant_len] + "\n...(内容已截断)"
        history.append({"role": role, "content": content})

    return history


def list_recent_sessions(limit: int = 30) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT session_id, content, created_at
        FROM chat_messages
        WHERE id IN (
            SELECT MAX(id)
            FROM chat_messages
            WHERE role = 'user'
            GROUP BY session_id
        )
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return [
        {"session_id": session_id, "last_user_message": content, "created_at": created_at}
        for session_id, content, created_at in rows
    ]


def get_session_messages(session_id: str, limit: int = 100) -> list[dict]:
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT id, role, content, created_at, reasoning_content, image_path, message_snapshot_json, mode
        FROM chat_messages
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    rows = list(rows)
    rows.reverse()

    result = []
    for row in rows:
        item = {
            "id": row[0],
            "role": row[1],
            "content": row[2],
            "created_at": row[3],
            "reasoning_content": row[4],
            "image_path": row[5],
            "message_snapshot_json": row[6] or None,
            "mode": row[7] or "agent",
        }
        result.append(item)
    return result


def get_latest_memory_boundary(session_id: str) -> int:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT COALESCE(MAX(source_until_message_id), 0)
        FROM session_memories
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    return int(row[0] or 0) if row else 0


def get_session_memories(session_id: str, limit: int = 3) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, session_id, summary, source_message_count, source_token_estimate,
               summary_token_estimate, source_until_message_id, created_at
        FROM session_memories
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    result = []
    for row in rows:
        result.append({
            "id": row[0],
            "session_id": row[1],
            "summary": row[2],
            "source_message_count": row[3],
            "source_token_estimate": row[4],
            "summary_token_estimate": row[5],
            "source_until_message_id": row[6],
            "created_at": row[7],
        })
    result.reverse()
    return result


def save_session_memory(memory: dict) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """
        INSERT INTO session_memories (
            session_id, summary, source_message_count, source_token_estimate,
            summary_token_estimate, source_until_message_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            memory.get("session_id", ""),
            memory.get("summary", ""),
            memory.get("source_message_count", 0),
            memory.get("source_token_estimate", 0),
            memory.get("summary_token_estimate", 0),
            memory.get("source_until_message_id"),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def delete_session(session_id: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM session_memories WHERE session_id = ?", (session_id,))
    conn.commit()
