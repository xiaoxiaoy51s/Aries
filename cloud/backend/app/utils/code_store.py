"""验证码 Redis 存储"""

import redis.asyncio as aioredis

from app.config.settings import settings

_redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def store_code(email: str, code: str):
    ttl = settings.CODE_EXPIRE_MINUTES * 60
    await _redis.setex(f"verify_code:{email}", ttl, code)


async def verify_code(email: str, code: str) -> bool:
    stored = await _redis.get(f"verify_code:{email}")
    if stored and stored == code:
        await _redis.delete(f"verify_code:{email}")
        return True
    return False
