"""在用户 JSONL 聊天日志中搜索（全事件类型 + 子 Agent 日志，底层 ripgrep）。"""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repository.session_repository import SessionRepository
from app.tools.file_ops import find_rg
from app.utils.session_logger import get_user_session_root, parse_session_log_filename

EVENT_LABELS: dict[str, str] = {
    "user_message": "用户消息",
    "assistant_text": "助手回复",
    "reasoning_text": "思考过程",
    "tool_call": "工具调用",
    "tool_result": "工具结果",
    "sub_agent": "子 Agent",
    "error": "错误",
    "token_usage": "Token 用量",
    "finalized": "完成",
}


def parse_log_file_meta(path: Path | str) -> dict[str, str]:
    """解析日志文件来源：主会话或 sub_agent。"""
    p = Path(path)
    if "sub_agent" in p.parts:
        return {
            "source": "sub_agent",
            "session_id": "",
            "message_id": p.stem,
            "task_id": p.stem,
        }
    parsed = parse_session_log_filename(p)
    if parsed:
        session_id, message_id = parsed
        return {
            "source": "session",
            "session_id": session_id,
            "message_id": message_id,
            "task_id": "",
        }
    return {
        "source": "unknown",
        "session_id": "",
        "message_id": p.stem,
        "task_id": "",
    }


def _text_matches(text: str, query: str, case_sensitive: bool) -> bool:
    if not text:
        return False
    if case_sensitive:
        return query in text
    return query.lower() in text.lower()


def _make_snippet(text: str, query: str, radius: int = 48) -> str:
    if not text:
        return ""
    idx = text.lower().find(query.lower()) if query else 0
    if idx < 0:
        idx = 0
    start = max(0, idx - radius)
    end = min(len(text), idx + len(query) + radius)
    snippet = text[start:end].replace("\n", " ")
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def _extract_event_text(event: dict[str, Any]) -> str:
    """从任意 JSONL 事件提取可搜索/展示文本。"""
    ev_type = event.get("type") or ""
    chunks: list[str] = []

    if ev_type == "user_message":
        chunks.append(str(event.get("text") or ""))
    elif ev_type in ("assistant_text", "reasoning_text"):
        chunks.append(str(event.get("text") or ""))
    elif ev_type == "tool_call":
        chunks.append(str(event.get("tool_name") or ""))
        args = event.get("args")
        if args:
            chunks.append(json.dumps(args, ensure_ascii=False))
    elif ev_type == "tool_result":
        chunks.append(str(event.get("tool_name") or ""))
        chunks.append(str(event.get("result") or ""))
        chunks.append(str(event.get("error") or ""))
    elif ev_type == "sub_agent":
        for key in ("subagent", "task", "final_output", "error", "log_path"):
            val = event.get(key)
            if val:
                chunks.append(str(val))
    elif ev_type == "error":
        chunks.append(str(event.get("error") or ""))
        chunks.append(str(event.get("details") or ""))
    elif ev_type == "token_usage":
        usage = event.get("token_usage")
        if usage:
            chunks.append(json.dumps(usage, ensure_ascii=False))
        model = event.get("model")
        if model:
            chunks.append(str(model))
    else:
        chunks.append(json.dumps(event, ensure_ascii=False))

    return "\n".join(c for c in chunks if c).strip()


def _parse_log_line(line: str, query: str, case_sensitive: bool) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None

    event: dict[str, Any] | None = None
    display_text = line

    try:
        event = json.loads(line)
        display_text = _extract_event_text(event) or line
    except json.JSONDecodeError:
        display_text = line

    if not _text_matches(display_text, query, case_sensitive) and not _text_matches(line, query, case_sensitive):
        return None

    ev_type = (event or {}).get("type") or "raw"
    snippet_source = display_text if _text_matches(display_text, query, case_sensitive) else line
    return {
        "event_type": ev_type,
        "event_label": EVENT_LABELS.get(ev_type, ev_type),
        "text": display_text,
        "snippet": _make_snippet(snippet_source, query),
        "timestamp": (event or {}).get("timestamp", ""),
    }


def _build_hit(log_path: Path, parsed_line: dict[str, Any], line_no: int = 0) -> dict[str, Any]:
    meta = parse_log_file_meta(log_path)
    key = str(log_path.resolve())
    return {
        **meta,
        **parsed_line,
        "log_path": key,
        "line": line_no,
        "match_key": f"{key}:{line_no}",
    }


def _append_hit(
    results: list[dict[str, Any]],
    seen: set[str],
    hit: dict[str, Any],
    limit: int,
) -> bool:
    if hit["match_key"] in seen:
        return len(results) >= limit
    seen.add(hit["match_key"])
    results.append(hit)
    return len(results) >= limit


def _collect_from_log_file(
    log_path: Path,
    query: str,
    case_sensitive: bool,
    seen: set[str],
    results: list[dict[str, Any]],
    limit: int,
) -> None:
    if len(results) >= limit:
        return
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for idx, line in enumerate(lines, start=1):
        parsed = _parse_log_line(line, query, case_sensitive)
        if not parsed:
            continue
        if _append_hit(results, seen, _build_hit(log_path, parsed, idx), limit):
            return


def _search_with_python(
    session_root: Path,
    query: str,
    *,
    limit: int,
    case_sensitive: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not session_root.exists():
        return results

    jsonl_files = sorted(
        session_root.rglob("*.jsonl"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    for log_path in jsonl_files:
        _collect_from_log_file(log_path, query, case_sensitive, seen, results, limit)
        if len(results) >= limit:
            break
    return results


def _search_with_rg(
    session_root: Path,
    query: str,
    *,
    limit: int,
    case_sensitive: bool,
) -> list[dict[str, Any]]:
    rg = find_rg()
    if not rg:
        return _search_with_python(session_root, query, limit=limit, case_sensitive=case_sensitive)

    cmd = [
        rg,
        "--json",
        "--glob", "*.jsonl",
        "-m", str(max(limit * 5, 200)),
    ]
    if not case_sensitive:
        cmd.append("-i")
    cmd.extend(["-F", query, str(session_root)])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.TimeoutExpired):
        return _search_with_python(session_root, query, limit=limit, case_sensitive=case_sensitive)

    if proc.returncode not in (0, 1):
        return _search_with_python(session_root, query, limit=limit, case_sensitive=case_sensitive)

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_line in proc.stdout.splitlines():
        if len(results) >= limit:
            break
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "match":
            continue

        data = entry.get("data") or {}
        path_text = (data.get("path") or {}).get("text") or ""
        if not path_text:
            continue
        log_path = Path(path_text)
        json_part = (data.get("lines") or {}).get("text") or ""
        line_no = int(data.get("line_number") or 0)

        parsed = _parse_log_line(json_part, query, case_sensitive)
        if not parsed:
            continue
        if _append_hit(results, seen, _build_hit(log_path, parsed, line_no), limit):
            break
    return results


class SessionSearchService:
    @staticmethod
    async def search_user_messages(
        db: AsyncSession,
        user_id: int,
        user_email: str,
        query: str,
        *,
        limit: int = 30,
        case_sensitive: bool = False,
    ) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        limit = max(1, min(limit, 100))

        session_root = get_user_session_root(user_email)
        hits = await asyncio.to_thread(
            _search_with_rg,
            session_root,
            q,
            limit=limit,
            case_sensitive=case_sensitive,
        )

        session_ids = {h["session_id"] for h in hits if h.get("session_id")}
        title_map: dict[str, str] = {}
        for sid in session_ids:
            session = await SessionRepository.find_by_id(db, sid)
            if session and session.user_id == user_id:
                title_map[sid] = session.title or sid
            else:
                title_map[sid] = sid

        for hit in hits:
            sid = hit.get("session_id") or ""
            if sid:
                hit["session_title"] = title_map.get(sid, sid)
            elif hit.get("source") == "sub_agent":
                task = hit.get("task_id") or hit.get("message_id") or "sub_agent"
                hit["session_title"] = f"子 Agent · {task[:12]}"
            else:
                hit["session_title"] = hit.get("log_path", "未知日志")

        hits.sort(key=lambda h: (h.get("timestamp") or "", h.get("line") or 0), reverse=True)
        return hits[:limit]
