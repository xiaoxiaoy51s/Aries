"""L2 工具结果缓存：幂等只读工具的运行时结果复用。

缓存键：sha256(tool_name, normalized_args, work_dir, path_mtime_fingerprint)
TTL：read 类 5min，search 类 30min
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 工具名 → TTL（秒）
CACHEABLE_TOOLS: dict[str, int] = {
    "read_file": 300,
    "search_file": 1800,
    "list_files": 1800,
    "web_search": 1800,
}

# 别名（文档/旧名 → 实际工具名）
_TOOL_ALIASES: dict[str, str] = {
    "read": "read_file",
    "grep": "search_file",
    "glob": "list_files",
}

_NON_CACHEABLE_TOOLS: frozenset[str] = frozenset({
    "write_file",
    "edit_file",
    "apply_patch",
    "multi_replace_string",
    "delete_file",
    "cli_executor",
    "stop_command",
    "todo_write",
    "create_scheduled_task",
    "delegate_to_subagent",
    "send_file_to_user",
    "check_command_status",
})

_NON_CACHEABLE_PREFIXES: tuple[str, ...] = ("computer_",)

# key → (expires_at, result_dict, stored_at)
_cache: dict[str, tuple[float, dict[str, Any], float]] = {}

# work_dir → set of cache keys（便于写操作后批量失效）
_work_dir_index: dict[str, set[str]] = {}

MAX_CACHE_ENTRIES = 512

_stats = {"hits": 0, "misses": 0, "stores": 0, "evictions": 0, "invalidations": 0}

# cli_executor 中视为只读、不触发 L2 全量失效的前缀
_READONLY_CLI_PREFIXES: tuple[str, ...] = (
    "git status", "git log", "git diff", "git branch", "git show", "git stash list",
    "ls", "dir", "pwd", "echo", "cat ", "type ", "head ", "tail ", "where ",
    "npm list", "npm run", "npm test", "npm view", "node -v", "node --version",
    "python --version", "python -V", "pip list", "pip show",
    "curl ", "wget ", "ping ",
)

_SKIP_ARG_KEYS = frozenset({
    "skip_confirmation",
    "_work_dir",
    "invocation_id",
})


def _canonical_tool_name(tool_name: str) -> str:
    name = (tool_name or "").strip()
    return _TOOL_ALIASES.get(name, name)


def is_cacheable_tool(tool_name: str) -> bool:
    name = _canonical_tool_name(tool_name)
    if name in _NON_CACHEABLE_TOOLS:
        return False
    if any(name.startswith(p) for p in _NON_CACHEABLE_PREFIXES):
        return False
    return name in CACHEABLE_TOOLS


def is_cache_busting_tool(tool_name: str, args: dict[str, Any] | None = None) -> bool:
    """改文件 / 非只读 shell 后应使同 work_dir 缓存失效。"""
    name = _canonical_tool_name(tool_name)
    if name == "cli_executor":
        command = str((args or {}).get("command") or "").strip().lower()
        if not command:
            return False
        if any(command.startswith(p) for p in _READONLY_CLI_PREFIXES):
            return False
        return True
    if name in {
        "write_file", "edit_file", "apply_patch", "multi_replace_string",
        "delete_file",
    }:
        return True
    return any(name.startswith(p) for p in _NON_CACHEABLE_PREFIXES)


def normalize_tool_args(args: dict[str, Any] | None) -> str:
    if not args:
        return "{}"
    cleaned: dict[str, Any] = {}
    for key in sorted(args.keys()):
        if key in _SKIP_ARG_KEYS:
            continue
        val = args[key]
        if val is None or val == "":
            continue
        cleaned[key] = val
    return json.dumps(cleaned, sort_keys=True, ensure_ascii=False, default=str)


def _file_stat_token(path: Path | None) -> str:
    if not path:
        return "missing"
    try:
        st = path.stat()
        return f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return "missing"


def _resolve_path(work_dir: str | None, raw: str) -> Path | None:
    raw = (raw or ".").strip() or "."
    try:
        from utils.user_file_manager import UserFileManager
        fm = UserFileManager(work_dir=work_dir)
        if raw in (".", "./"):
            return fm.get_user_dir()
        return fm.resolve_file_path(raw)
    except Exception:
        try:
            p = Path(raw)
            if p.is_absolute():
                return p
            base = Path(work_dir) if work_dir else Path.cwd()
            return (base / raw).resolve()
        except Exception:
            return None


def _resolve_skill_file_path(skill_name: str, file_path: str) -> Path | None:
    try:
        from engine.skills_manager import get_skill_by_name
        from engine.plugin_manager import discover_plugins

        skill_path: Path | None = None
        entry = get_skill_by_name(skill_name)
        if entry is not None:
            skill_path = entry.skill_path
        else:
            for plugin in discover_plugins():
                if plugin.kind == "skills" and plugin.name == skill_name:
                    skill_path = Path(plugin.target_path)
                    break
        if skill_path is None:
            return None
        target = (skill_path / file_path).resolve()
        if not str(target).startswith(str(skill_path.resolve())):
            return None
        return target if target.is_file() else None
    except Exception:
        return None


def get_path_mtime_fingerprint(
    tool_name: str,
    args: dict[str, Any],
    work_dir: str | None,
) -> str:
    """同 work_dir + 同 path + 同 mtime → 相同指纹；文件变更后自动 miss。"""
    name = _canonical_tool_name(tool_name)

    if name == "read_file":
        skill = (args.get("skill_name") or "").strip()
        file_path = (args.get("file_path") or args.get("path") or "").strip()
        if skill and file_path:
            return _file_stat_token(_resolve_skill_file_path(skill, file_path))
        return _file_stat_token(_resolve_path(work_dir, file_path))

    if name in ("search_file", "list_files"):
        raw = (
            args.get("path")
            or args.get("directory")
            or args.get("dir")
            or "."
        )
        return _file_stat_token(_resolve_path(work_dir, str(raw)))

    if name == "web_search":
        return "-"

    return "-"


def make_tool_cache_key(
    tool_name: str,
    args: dict[str, Any],
    work_dir: str | None,
) -> str:
    name = _canonical_tool_name(tool_name)
    normalized = normalize_tool_args(args)
    wd = (work_dir or "").strip()
    mtime_fp = get_path_mtime_fingerprint(name, args, work_dir)
    payload = f"{name}\0{normalized}\0{wd}\0{mtime_fp}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _index_key(work_dir: str | None, cache_key: str) -> None:
    wd = (work_dir or "").strip()
    if not wd:
        return
    _work_dir_index.setdefault(wd, set()).add(cache_key)


def _should_store_result(result: dict[str, Any]) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("requires_confirmation"):
        return False
    if result.get("success") is False:
        return False
    if result.get("error"):
        return False
    return True


def _purge_expired(now: float | None = None) -> None:
    ts = now if now is not None else time.monotonic()
    dead = [k for k, (exp, _, _) in _cache.items() if exp <= ts]
    for key in dead:
        _cache.pop(key, None)


def _evict_if_needed() -> None:
    if len(_cache) < MAX_CACHE_ENTRIES:
        return
    _purge_expired()
    if len(_cache) < MAX_CACHE_ENTRIES:
        return
    # 淘汰最早写入的条目
    oldest_key = min(_cache, key=lambda k: _cache[k][2])
    _cache.pop(oldest_key, None)
    _stats["evictions"] += 1


def get_cached_tool_result(
    tool_name: str,
    args: dict[str, Any],
    work_dir: str | None,
) -> dict[str, Any] | None:
    if not is_cacheable_tool(tool_name):
        return None
    key = make_tool_cache_key(tool_name, args, work_dir)
    entry = _cache.get(key)
    if not entry:
        _stats["misses"] += 1
        return None
    expires_at, stored, _stored_at = entry
    if time.monotonic() >= expires_at:
        _cache.pop(key, None)
        _stats["misses"] += 1
        return None
    _stats["hits"] += 1
    out = dict(stored)
    out["_cached"] = True
    return out


def store_tool_result(
    tool_name: str,
    args: dict[str, Any],
    work_dir: str | None,
    result: dict[str, Any],
) -> None:
    if not is_cacheable_tool(tool_name):
        return
    if not _should_store_result(result):
        return
    name = _canonical_tool_name(tool_name)
    ttl = CACHEABLE_TOOLS.get(name, 300)
    key = make_tool_cache_key(tool_name, args, work_dir)
    clean = {k: v for k, v in result.items() if not str(k).startswith("_")}
    now = time.monotonic()
    _evict_if_needed()
    _cache[key] = (now + ttl, clean, now)
    _index_key(work_dir, key)
    _stats["stores"] += 1


def invalidate_work_dir_cache(work_dir: str | None) -> int:
    """写/删/执行命令后清除该 work_dir 下所有 L2 缓存。"""
    wd = (work_dir or "").strip()
    if not wd:
        return 0
    keys = _work_dir_index.pop(wd, set())
    for key in keys:
        _cache.pop(key, None)
    _stats["invalidations"] += len(keys)
    return len(keys)


def clear_tool_cache() -> None:
    _cache.clear()
    _work_dir_index.clear()


def cache_stats() -> dict[str, int | float]:
    now = time.monotonic()
    alive = sum(1 for exp, _, _ in _cache.values() if exp > now)
    total = _stats["hits"] + _stats["misses"]
    hit_rate = round(_stats["hits"] / total * 100, 1) if total else 0.0
    return {
        "entries": len(_cache),
        "alive": alive,
        "max_entries": MAX_CACHE_ENTRIES,
        "hits": _stats["hits"],
        "misses": _stats["misses"],
        "stores": _stats["stores"],
        "evictions": _stats["evictions"],
        "invalidations": _stats["invalidations"],
        "hit_rate_percent": hit_rate,
    }
