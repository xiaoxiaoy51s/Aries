import json
import sqlite3
from .database import get_connection


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
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(chat_messages)")
    columns = {row[1] for row in cursor.fetchall()}
    has_mode = "mode" in columns
    effective_mode = (mode or "agent").strip().lower() or "agent"

    col_names = ["session_id", "role", "content", "reasoning_content",
                 "image_path", "message_snapshot_json"]
    col_values: list = [session_id, role, content, reasoning_content,
                        image_path, message_snapshot_json]

    if has_mode:
        col_names.append("mode")
        col_values.append(effective_mode)

    placeholders = ", ".join("?" * len(col_names))
    sql = f"INSERT INTO chat_messages ({', '.join(col_names)}) VALUES ({placeholders})"
    cursor.execute(sql, col_values)

    conn.commit()
    last_id = int(cursor.lastrowid)
    conn.close()
    return last_id


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
    conn.close()


def get_chat_context_messages(
    session_id: str,
    message_limit: int = 28,
    reasoning_rounds: int = 2,
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(chat_messages)")
    has_mode = "mode" in {row[1] for row in cursor.fetchall()}
    mode_col = ", mode" if has_mode else ""

    rows = conn.execute(
        f"""
        SELECT id, role, content, reasoning_content, image_path, message_snapshot_json{mode_col}
        FROM chat_messages
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()

    rows = list(rows)
    rows.reverse()
    conn.close()

    result = []
    for row in rows:
        item = {
            "id": row[0],
            "role": row[1],
            "content": row[2],
            "reasoning_content": row[3],
            "image_path": row[4],
            "message_snapshot_json": row[5] or None,
        }
        if has_mode:
            item["mode"] = row[6] or "agent"
        result.append(item)
    return result


def get_recent_agent_reasoning(session_id: str, rounds: int = 2) -> list[str]:
    """取最近 N 轮 assistant 的深度思考，供 agent 模式注入上下文。"""
    db_msgs = get_recent_messages(session_id, limit=50)
    reasoning_list: list[str] = []
    for msg in db_msgs:
        if msg.get("role") != "assistant":
            continue
        reasoning = (msg.get("reasoning_content") or "").strip()
        if not reasoning:
            continue
        reasoning_list.append(reasoning)
    return reasoning_list[-rounds:]


def build_agent_reasoning_context(session_id: str, rounds: int = 2) -> dict | None:
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
    conn.close()

    return [
        {"session_id": session_id, "last_user_message": content, "created_at": created_at}
        for session_id, content, created_at in rows
    ]


def get_session_messages(session_id: str, limit: int = 100) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(chat_messages)")
    has_mode = "mode" in {row[1] for row in cursor.fetchall()}
    mode_col = ", mode" if has_mode else ""

    rows = conn.execute(
        f"""
        SELECT id, role, content, created_at, reasoning_content, image_path, message_snapshot_json{mode_col}
        FROM chat_messages
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    rows = list(rows)
    rows.reverse()
    conn.close()

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
        }
        if has_mode:
            item["mode"] = row[7] or "agent"
        result.append(item)
    return result


def delete_session(session_id: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
