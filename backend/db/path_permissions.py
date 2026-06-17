"""路径权限管理：白名单（完全放行）/ 黑名单（直接拒绝）/ 其余走原有确认流程。"""

from pathlib import Path
from typing import Optional

from .database import get_connection


def _normalize(p: str) -> str:
    """统一路径格式：转正斜杠、去末尾斜杠。"""
    return Path(p).resolve().as_posix().rstrip("/")


# 默认白名单路径：用户工作目录
DEFAULT_WHITELIST_PATH = str((Path.home() / ".MIMOClaw" / "work_dir").resolve())


def init_default_whitelist():
    """初始化默认白名单（用户工作目录）。"""
    conn = get_connection()
    try:
        # 检查是否已存在
        existing = conn.execute(
            "SELECT id FROM path_permissions WHERE path = ?",
            (_normalize(DEFAULT_WHITELIST_PATH),)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO path_permissions (path, type) VALUES (?, 'whitelist')",
                (_normalize(DEFAULT_WHITELIST_PATH),)
            )
            conn.commit()
    finally:
        conn.close()


def _path_matches(rule_path: str, target_path: str) -> bool:
    """判断 target_path 是否命中 rule_path（精确或子目录）。"""
    rule = _normalize(rule_path)
    target = _normalize(target_path)
    return target == rule or target.startswith(rule + "/")


def add_permission(path: str, perm_type: str) -> dict:
    conn = get_connection()
    try:
        normalized = _normalize(path)
        # 如果已存在同路径但不同类型的记录，先删除
        conn.execute(
            "DELETE FROM path_permissions WHERE path = ? AND type != ?",
            (normalized, perm_type),
        )
        conn.execute(
            """INSERT OR REPLACE INTO path_permissions (path, type)
               VALUES (?, ?)""",
            (normalized, perm_type),
        )
        conn.commit()
        return {"success": True, "path": normalized, "type": perm_type}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def remove_permission(path: str) -> dict:
    conn = get_connection()
    try:
        normalized = _normalize(path)
        conn.execute("DELETE FROM path_permissions WHERE path = ?", (normalized,))
        conn.commit()
        return {"success": True}
    finally:
        conn.close()


def list_permissions() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, path, type, created_at FROM path_permissions ORDER BY type, path"
        ).fetchall()
        return [
            {"id": r[0], "path": r[1], "type": r[2], "created_at": r[3] or ""}
            for r in rows
        ]
    finally:
        conn.close()


def check_path_permission(target_path: str) -> Optional[dict]:
    """检查路径权限。

    返回:
        None -> 不在黑白名单中，走原有确认流程
        {"allowed": True} -> 白名单命中，直接放行
        {"allowed": False, "reason": "..."} -> 黑名单命中，直接拒绝
    """
    try:
        target = _normalize(target_path)
    except Exception:
        return {"allowed": False, "reason": "无效路径"}

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT path, type FROM path_permissions"
        ).fetchall()
    finally:
        conn.close()

    whitelist_hits = []
    blacklist_hits = []

    for r in rows:
        rule_path, rule_type = r[0], r[1]
        if _path_matches(rule_path, target):
            if rule_type == "whitelist":
                whitelist_hits.append(rule_path)
            else:
                blacklist_hits.append(rule_path)

    # 黑名单优先：如果同时命中黑白名单，拒绝
    if blacklist_hits:
        return {
            "allowed": False,
            "reason": f"路径在黑名单中，已被禁止访问。匹配规则: {', '.join(blacklist_hits)}",
        }

    if whitelist_hits:
        return {"allowed": True, "reason": f"路径在白名单中，已自动放行。匹配规则: {', '.join(whitelist_hits)}"}

    return None
