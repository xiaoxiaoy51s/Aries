from fastapi import APIRouter

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/events")
async def debug_events():
    return {"events": []}


@router.get("/health")
async def debug_health():
    """运行时资源快照：定位"用久了变卡"时哪类资源在持续增长。

    summary 中数字后括号为相对启动基线的增量，只涨不回即为泄漏嫌疑。
    """
    from utils import runtime_diagnostics as diag

    snap = diag.collect_snapshot()
    return {
        "summary": diag.format_line(snap, diag._BASELINE),
        "warnings": diag._check_warnings(snap),
        "snapshot": snap,
    }
