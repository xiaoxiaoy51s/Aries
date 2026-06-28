"""聚合各层进程内缓存的运行指标，供 /system/cache-stats 暴露。"""
from __future__ import annotations

from typing import Any


def collect_cache_stats() -> dict[str, Any]:
    from utils.prompt_cache import is_prompt_cache_enabled
    from utils.tool_cache import cache_stats as tool_cache_stats
    from api.engine.approval_cache import approval_stats

    stats: dict[str, Any] = {
        "l1_prompt_cache": {
            "enabled": is_prompt_cache_enabled(),
            "storage": "in_memory",
            "note": "Provider 前缀缓存；命中率见 run_metadata.token_usage.prompt_cache",
        },
        "l2_tool_cache": tool_cache_stats(),
        "l3_approval_cache": approval_stats(),
    }

    try:
        from aries_mcp.runtime import get_mcp_pool
        pool = get_mcp_pool()
        diagnostics = pool.get_diagnostics()
        stats["l4_mcp_cache"] = {
            "servers": len(diagnostics),
            "connected": sum(1 for d in diagnostics if d.get("status") == "connected"),
            "cached_tools": sum(int(d.get("tool_count") or 0) for d in diagnostics),
            "storage": "disk_json",
        }
    except Exception as exc:
        stats["l4_mcp_cache"] = {"error": str(exc)}

    return stats
