from fastapi import APIRouter

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/events")
async def debug_events():
    return {"events": []}
