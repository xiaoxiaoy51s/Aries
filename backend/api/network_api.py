"""Network Config API - 代理配置管理

前端设置页面通过这些 API 读取/保存 ~/.Aries/network.json
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from utils.network_manager import (
    load_network_config,
    save_network_config,
    ensure_network_config_exists,
    NETWORK_CONFIG_PATH,
)

router = APIRouter(prefix="/network", tags=["network"])


class NetworkConfigUpdate(BaseModel):
    enabled: bool = False
    proxy_url: str = "http://127.0.0.1:7890"
    proxy_domains: List[str] = []
    proxy_commands: List[str] = []
    command_proxy: bool = True


@router.get("/config")
async def get_network_config():
    """读取网络代理配置。"""
    ensure_network_config_exists()
    return load_network_config()


@router.put("/config")
async def update_network_config(config: NetworkConfigUpdate):
    """保存网络代理配置。"""
    data = config.model_dump()
    save_network_config(data)
    return {"success": True, "data": load_network_config()}


@router.post("/test")
async def test_proxy():
    """测试代理是否可用（尝试通过代理访问一个已知网站）。"""
    import httpx
    from utils.network_manager import is_proxy_enabled, get_proxy_url

    if not is_proxy_enabled():
        return {"success": False, "error": "代理未启用"}

    proxy_url = get_proxy_url()
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=10) as client:
            resp = await client.get("https://www.google.com")
            return {
                "success": resp.status_code == 200,
                "status_code": resp.status_code,
                "proxy_url": proxy_url,
            }
    except Exception as exc:
        return {"success": False, "error": str(exc), "proxy_url": proxy_url}
