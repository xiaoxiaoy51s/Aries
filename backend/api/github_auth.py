"""GitHub OAuth2 授权 API。

支持两种连接方式：
1. OAuth Web Flow - 点击授权，浏览器登录，自动回调
2. Personal Access Token - 手动粘贴 token
"""

import json
import secrets
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/github", tags=["github"])

# GitHub OAuth 配置
GITHUB_OAUTH_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_OAUTH_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_API_USER = "https://api.github.com/user"

# 配置文件路径
_GITHUB_CONFIG_PATH = Path.home() / ".Aries" / "github_config.json"

# OAuth App 配置（用户需要替换为自己的）
# 申请地址：https://github.com/settings/developers
DEFAULT_CLIENT_ID = ""
DEFAULT_CLIENT_SECRET = ""

# 临时存储 OAuth state（防 CSRF）
_pending_states: dict[str, dict] = {}


# ---------- Models ----------

class PatConnectRequest(BaseModel):
    token: str


class OAuthStartResponse(BaseModel):
    auth_url: str
    state: str


class GithubConfigRequest(BaseModel):
    client_id: str = ""
    client_secret: str = ""


# ---------- Helpers ----------

def _load_config() -> dict:
    """加载 GitHub 配置。"""
    if not _GITHUB_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(_GITHUB_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(config: dict) -> None:
    """保存 GitHub 配置。"""
    _GITHUB_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _GITHUB_CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def _get_client_credentials() -> tuple[str, str]:
    """获取 OAuth App 的 client_id 和 client_secret。"""
    config = _load_config()
    client_id = config.get("client_id") or DEFAULT_CLIENT_ID
    client_secret = config.get("client_secret") or DEFAULT_CLIENT_SECRET
    return client_id, client_secret


async def _verify_token(token: str) -> Optional[dict]:
    """验证 GitHub token 并获取用户信息。"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            GITHUB_API_USER,
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Aries-Agent",
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            return None
        return resp.json()


# ---------- APIs ----------

@router.get("/status")
async def github_status():
    """获取 GitHub 连接状态。"""
    config = _load_config()
    token = config.get("token")

    if not token:
        return {
            "connected": False,
            "username": None,
            "avatar_url": None,
            "scope": [],
        }

    # 验证 token 是否仍然有效
    user_info = await _verify_token(token)
    if not user_info:
        # Token 无效，清除配置
        config.pop("token", None)
        _save_config(config)
        return {
            "connected": False,
            "username": None,
            "avatar_url": None,
            "scope": [],
            "error": "Token 已失效，请重新授权",
        }

    return {
        "connected": True,
        "username": user_info.get("login"),
        "avatar_url": user_info.get("avatar_url"),
        "name": user_info.get("name"),
        "scope": config.get("scope", []),
    }


@router.get("/auth/start")
async def github_auth_start():
    """启动 OAuth2 授权流程，返回授权 URL。"""
    client_id, _ = _get_client_credentials()

    if not client_id:
        raise HTTPException(
            status_code=400,
            detail="GitHub OAuth App 未配置。请先在设置中配置 Client ID，或使用 PAT 方式连接。"
        )

    # 生成 state 参数（防 CSRF）
    state = secrets.token_urlsafe(32)

    # 存储 state，包含时间戳
    _pending_states[state] = {"created_at": time.time()}

    # 构建授权 URL
    params = {
        "client_id": client_id,
        "scope": "repo read:user",
        "state": state,
        "redirect_uri": "http://localhost:30000/github/callback",
    }
    auth_url = f"{GITHUB_OAUTH_AUTHORIZE}?{urlencode(params)}"

    return {"auth_url": auth_url, "state": state}


@router.get("/callback")
async def github_callback(
    code: str = Query(..., description="GitHub 授权码"),
    state: str = Query(..., description="防 CSRF state 参数"),
):
    """处理 GitHub OAuth 回调。"""
    # 验证 state
    if state not in _pending_states:
        raise HTTPException(status_code=400, detail="无效的授权请求（state 不匹配）")

    # 清理 state
    _pending_states.pop(state, None)

    # 获取 client 凭证
    client_id, client_secret = _get_client_credentials()

    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="GitHub OAuth App 配置不完整")

    # 用 code 换取 access_token
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GITHUB_OAUTH_TOKEN,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": "http://localhost:30000/github/callback",
            },
            headers={"Accept": "application/json"},
            timeout=10.0,
        )

        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail="获取 token 失败")

        data = resp.json()

        if "error" in data:
            raise HTTPException(
                status_code=400,
                detail=f"授权失败: {data.get('error_description', data['error'])}"
            )

        access_token = data.get("access_token")
        scope = data.get("scope", "").split(",") if data.get("scope") else []

        if not access_token:
            raise HTTPException(status_code=500, detail="未获取到 access_token")

    # 验证 token 并获取用户信息
    user_info = await _verify_token(access_token)
    if not user_info:
        raise HTTPException(status_code=500, detail="获取用户信息失败")

    # 保存配置
    config = _load_config()
    config.update({
        "token": access_token,
        "token_type": "oauth",
        "username": user_info.get("login"),
        "avatar_url": user_info.get("avatar_url"),
        "name": user_info.get("name"),
        "scope": scope,
        "connected_at": time.time(),
    })
    _save_config(config)

    # 返回成功页面（可以直接在浏览器中显示）
    return {
        "success": True,
        "message": "GitHub 授权成功！可以关闭此页面。",
        "username": user_info.get("login"),
    }


@router.post("/pat")
async def github_connect_pat(body: PatConnectRequest):
    """使用 Personal Access Token 连接 GitHub。"""
    token = body.token.strip()

    if not token:
        raise HTTPException(status_code=400, detail="Token 不能为空")

    # 验证 token
    user_info = await _verify_token(token)
    if not user_info:
        raise HTTPException(status_code=400, detail="Token 无效或已过期")

    # 保存配置
    config = _load_config()
    config.update({
        "token": token,
        "token_type": "pat",
        "username": user_info.get("login"),
        "avatar_url": user_info.get("avatar_url"),
        "name": user_info.get("name"),
        "scope": ["repo", "read:user"],
        "connected_at": time.time(),
    })
    _save_config(config)

    return {
        "success": True,
        "username": user_info.get("login"),
        "message": "GitHub 连接成功！",
    }


@router.delete("/disconnect")
async def github_disconnect():
    """断开 GitHub 连接。"""
    config = _load_config()
    config.pop("token", None)
    config.pop("token_type", None)
    config.pop("username", None)
    config.pop("avatar_url", None)
    config.pop("name", None)
    config.pop("scope", None)
    config.pop("connected_at", None)
    _save_config(config)

    return {"success": True, "message": "GitHub 连接已断开"}


@router.get("/repositories")
async def github_repositories():
    """获取用户的仓库列表（需要 repo 权限）。"""
    config = _load_config()
    token = config.get("token")

    if not token:
        raise HTTPException(status_code=400, detail="GitHub 未连接")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Aries-Agent",
            },
            params={"sort": "updated", "per_page": 30},
            timeout=15.0,
        )

        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="获取仓库列表失败")

        repos = resp.json()

    return {
        "repositories": [
            {
                "id": r["id"],
                "name": r["name"],
                "full_name": r["full_name"],
                "description": r.get("description"),
                "html_url": r["html_url"],
                "clone_url": r["clone_url"],
                "default_branch": r.get("default_branch", "main"),
                "private": r["private"],
                "updated_at": r.get("updated_at"),
            }
            for r in repos
        ]
    }


@router.get("/user")
async def github_user():
    """获取当前连接的用户信息。"""
    config = _load_config()
    token = config.get("token")

    if not token:
        raise HTTPException(status_code=400, detail="GitHub 未连接")

    user_info = await _verify_token(token)
    if not user_info:
        raise HTTPException(status_code=401, detail="Token 已失效")

    return {
        "login": user_info.get("login"),
        "name": user_info.get("name"),
        "avatar_url": user_info.get("avatar_url"),
        "bio": user_info.get("bio"),
        "public_repos": user_info.get("public_repos"),
        "followers": user_info.get("followers"),
        "following": user_info.get("following"),
    }


@router.post("/config")
async def update_github_config(body: GithubConfigRequest):
    """更新 GitHub OAuth App 配置（可选）。"""
    config = _load_config()

    if body.client_id:
        config["client_id"] = body.client_id
    if body.client_secret:
        config["client_secret"] = body.client_secret

    _save_config(config)

    return {"success": True, "message": "GitHub OAuth App 配置已更新"}


@router.get("/config")
async def get_github_config():
    """获取 GitHub OAuth App 配置状态。"""
    config = _load_config()
    return {
        "has_client_id": bool(config.get("client_id") or DEFAULT_CLIENT_ID),
        "has_client_secret": bool(config.get("client_secret") or DEFAULT_CLIENT_SECRET),
    }


# 清理过期的 state（可选，定期调用）
def cleanup_expired_states():
    """清理超过 10 分钟的未使用 state。"""
    now = time.time()
    expired = [
        s for s, data in _pending_states.items()
        if now - data.get("created_at", 0) > 600
    ]
    for s in expired:
        _pending_states.pop(s, None)
