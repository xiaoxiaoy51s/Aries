"""应用版本读取与 GitHub Releases 对比。"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from utils.network_manager import get_proxy_for_url

logger = logging.getLogger(__name__)

GITHUB_OWNER = "xiaoxiaoy51s"
GITHUB_REPO = "Aries"
GITHUB_RELEASES_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
_PACKAGE_JSON = Path(__file__).resolve().parent.parent.parent / "frontend" / "package.json"


def get_app_version() -> str:
    """读取当前应用版本（backend/VERSION → frontend/package.json → 默认 1.0.0）。"""
    if _VERSION_FILE.is_file():
        text = _VERSION_FILE.read_text(encoding="utf-8").strip()
        if text:
            return text.splitlines()[0].strip()

    if _PACKAGE_JSON.is_file():
        try:
            data = json.loads(_PACKAGE_JSON.read_text(encoding="utf-8"))
            version = str(data.get("version", "")).strip()
            if version:
                return version
        except Exception as exc:
            logger.debug("读取 package.json 版本失败: %s", exc)

    return "1.0.0"


def normalize_version(version: str) -> str:
    """去掉 v 前缀与首尾空白。"""
    return re.sub(r"^[vV]", "", (version or "").strip())


def _parse_version(version: str) -> tuple[int, int, int, str]:
    """解析 semver 主版本号；预发布段单独比较。"""
    normalized = normalize_version(version)
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:[-.]?(.*))?$", normalized)
    if not match:
        return (0, 0, 0, normalized)
    major, minor, patch, prerelease = match.groups()
    return (int(major), int(minor), int(patch), (prerelease or "").lower())


def compare_versions(left: str, right: str) -> int:
    """比较两个版本号。返回 -1 / 0 / 1（left 小于 / 等于 / 大于 right）。"""
    a = _parse_version(left)
    b = _parse_version(right)
    if a[:3] != b[:3]:
        return -1 if a[:3] < b[:3] else 1
    # 无预发布 > 有预发布
    if not a[3] and b[3]:
        return 1
    if a[3] and not b[3]:
        return -1
    if a[3] == b[3]:
        return 0
    return -1 if a[3] < b[3] else 1


async def fetch_latest_release() -> dict[str, Any]:
    """从 GitHub Releases 获取最新版本信息。"""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Aries-Desktop",
    }
    proxy = get_proxy_for_url(GITHUB_RELEASES_URL)
    try:
        async with httpx.AsyncClient(
            timeout=15,
            trust_env=False,
            proxy=proxy.get("https") if proxy else None,
        ) as client:
            resp = await client.get(GITHUB_RELEASES_URL, headers=headers)
            if resp.status_code == 404:
                return {
                    "found": False,
                    "error": "GitHub 上暂无 Release，请先发布首个版本",
                }
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        return {"found": False, "error": f"GitHub API 错误: {exc.response.status_code}"}
    except Exception as exc:
        logger.warning("获取 GitHub Release 失败: %s", exc)
        return {"found": False, "error": str(exc)}

    tag_name = normalize_version(str(data.get("tag_name", "")))
    return {
        "found": bool(tag_name),
        "version": tag_name,
        "name": str(data.get("name") or tag_name),
        "html_url": str(data.get("html_url") or f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"),
        "body": str(data.get("body") or ""),
        "published_at": data.get("published_at"),
    }


async def check_for_update() -> dict[str, Any]:
    """对比本地版本与 GitHub 最新 Release。"""
    current = get_app_version()
    release = await fetch_latest_release()

    result: dict[str, Any] = {
        "current_version": current,
        "github_repo": f"{GITHUB_OWNER}/{GITHUB_REPO}",
        "latest_version": None,
        "update_available": False,
        "release_name": None,
        "release_url": f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases",
        "release_notes": None,
        "published_at": None,
        "error": release.get("error"),
    }

    if not release.get("found"):
        return result

    latest = str(release["version"])
    result.update(
        latest_version=latest,
        release_name=release.get("name"),
        release_url=release.get("html_url"),
        release_notes=release.get("body"),
        published_at=release.get("published_at"),
        update_available=compare_versions(current, latest) < 0,
    )
    return result
