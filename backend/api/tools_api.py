"""CLI 工具检测与管理 API。

提供检测系统 PATH 中 CLI 工具、手动连接 / 断开、添加自定义 CLI 的功能。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from utils.tools_config import (
    add_custom_cli,
    get_custom_clis,
    get_tool_config,
    remove_custom_cli,
    remove_tool_config,
    save_tool_config,
)
from utils.tools_status import (
    CLI_CANDIDATES,
    CLI_ROUTING_CONFIGS,
    detect_cli_by_id,
)

router = APIRouter(prefix="/api/tools", tags=["tools"])


def _build_tool_info(cli_id: str) -> dict[str, Any]:
    """构建单个 CLI 工具的完整检测信息"""
    # 先查预定义列表
    detected = detect_cli_by_id(cli_id)
    custom = False

    if detected is None:
        # 尝试从自定义列表查找
        custom_spec = None
        for c in get_custom_clis():
            if c["id"] == cli_id:
                custom_spec = c
                break
        if custom_spec is None:
            return {"id": cli_id, "installed": False, "connected": False, "path": None, "error": "unknown cli"}
        custom = True
        detected = {
            "id": custom_spec["id"],
            "name": custom_spec["name"],
            "description": custom_spec.get("description", ""),
            "installed": False,
            "path": None,
            "binary": custom_spec.get("binary", []),
            "connectable": True,
        }

    # 读取用户手动连接的配置
    saved = get_tool_config(cli_id)

    # 查找 vendor 字段
    if custom:
        vendor = "custom"
    else:
        candidate_meta = next((c for c in CLI_CANDIDATES if c["id"] == cli_id), {})
        vendor = candidate_meta.get("vendor", "")

    routing = CLI_ROUTING_CONFIGS.get(cli_id, {})
    if custom and not routing:
        # 自定义 CLI 使用用户填写的路由配置
        rc = custom_spec.get("routing_config", {})
        routing = rc if isinstance(rc, dict) else {}

    result: dict[str, Any] = {
        "id": detected["id"],
        "name": detected["name"],
        "description": detected["description"],
        "vendor": vendor,
        "connectable": True,
        "system_installed": detected.get("installed", False),
        "system_path": detected.get("path"),
        "routing_config": routing,
        "custom": custom,
    }

    # 判定最终连接状态：优先使用手动配置
    if saved and saved.get("connected"):
        result["connected"] = True
        result["path"] = saved.get("path", detected.get("path"))
        result["source"] = saved.get("source", "manual")
    elif detected.get("installed"):
        result["connected"] = True
        result["path"] = detected["path"]
        result["source"] = "system"
    else:
        result["connected"] = False
        result["path"] = None
        result["source"] = None

    return result


def _merge_detect(predefined: bool, custom_only: bool = False) -> dict[str, Any]:
    """合并预定义 + 自定义 CLI 检测结果"""
    tools: dict[str, Any] = {}

    if not custom_only:
        for candidate in CLI_CANDIDATES:
            tools[candidate["id"]] = _build_tool_info(candidate["id"])

    for custom_spec in get_custom_clis():
        tools[custom_spec["id"]] = _build_tool_info(custom_spec["id"])

    return {"tools": tools}


@router.get("/detect")
async def detect_tools() -> dict[str, Any]:
    """检测所有 CLI 工具状态（预定义 + 自定义）"""
    return _merge_detect(predefined=True)


class ConnectRequest(BaseModel):
    cli_id: str
    path: str | None = None


@router.post("/connect")
async def connect_tool(req: ConnectRequest) -> dict[str, Any]:
    """手动连接一个 CLI 工具（预定义或自定义均可）"""
    cli_id = req.cli_id
    path = req.path

    # 查找工具信息
    detected = detect_cli_by_id(cli_id)
    tool_name = cli_id
    if detected:
        tool_name = detected["name"]
    else:
        # 检查自定义列表
        for c in get_custom_clis():
            if c["id"] == cli_id:
                tool_name = c["name"]
                break
        else:
            return {"success": False, "error": f"未知工具: {cli_id}"}

    source = "system"
    if path:
        p = Path(path)
        if not p.exists():
            return {"success": False, "error": f"路径不存在: {path}"}
        source = "manual"
    else:
        if detected and detected["installed"]:
            path = detected["path"]
        else:
            return {"success": False, "error": f"未在 PATH 中找到 {tool_name}，请指定路径"}

    save_tool_config(cli_id, {
        "path": path,
        "source": source,
        "connected": True,
    })

    return {
        "success": True,
        "tool": {
            "id": cli_id,
            "name": tool_name,
            "connected": True,
            "path": path,
            "source": source,
        },
    }


class DisconnectRequest(BaseModel):
    cli_id: str


@router.post("/disconnect")
async def disconnect_tool(req: DisconnectRequest) -> dict[str, Any]:
    """断开一个 CLI 工具的连接"""
    cli_id = req.cli_id
    remove_tool_config(cli_id)
    return {"success": True, "tool_id": cli_id}


class AddCustomCLIRequest(BaseModel):
    path: str


@router.post("/custom")
async def add_custom_cli_endpoint(req: AddCustomCLIRequest) -> dict[str, Any]:
    """添加自定义 CLI 定义（仅需可执行文件路径，后端自动提取信息）"""
    p = Path(req.path)
    if not p.exists():
        return {"success": False, "error": f"路径不存在: {req.path}"}

    # 从文件名自动推导 id 和 name
    stem = p.stem  # code.CMD → code, my-cli.exe → my-cli
    cli_id = stem.lower().replace(" ", "-")
    cli_name = stem

    # 检查 id 是否和预定义冲突
    if detect_cli_by_id(cli_id) is not None:
        # 加后缀避免冲突
        cli_id = f"custom-{cli_id}"
        cli_name = f"{stem} (自定义)"

    spec = {
        "id": cli_id,
        "name": cli_name,
        "binary": [stem],
        "description": f"用户自定义 CLI: {p.name}",
        "vendor": "custom",
        "routing_config": {},
    }

    # 尝试运行 --help 自动提取配置
    try:
        import subprocess
        result = subprocess.run([str(p), "--help"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            help_text = result.stdout[:2000] or result.stderr[:2000]
            # 简单启发式提取 description
            first_line = help_text.strip().split("\n")[0] if help_text.strip() else ""
            if first_line and len(first_line) < 120:
                spec["description"] = first_line
    except Exception:
        pass

    add_custom_cli(spec)

    # 自动连接到这个路径
    save_tool_config(cli_id, {
        "path": req.path,
        "source": "manual",
        "connected": True,
    })

    return {"success": True, "tool": {**spec, "connected": True, "path": req.path}}


@router.delete("/custom/{custom_id}")
async def delete_custom_cli(custom_id: str) -> dict[str, Any]:
    """删除自定义 CLI 定义"""
    removed = remove_custom_cli(custom_id)
    return {"success": True, "removed": removed}
