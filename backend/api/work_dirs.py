"""工作目录管理 API —— 独立于 sessions，支持归档/删除/重命名。"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from db.work_dirs import (
    upsert_work_dir,
    list_work_dirs,
    delete_work_dir,
    archive_work_dir,
    rename_work_dir,
    get_latest_work_dir,
    DEFAULT_WORK_DIR,
)

router = APIRouter(prefix="/work-dirs", tags=["work-dirs"])


class WorkDirUpsert(BaseModel):
    work_dir: str
    name: Optional[str] = None


class WorkDirArchive(BaseModel):
    work_dir: str
    archived: bool = True


class WorkDirRename(BaseModel):
    work_dir: str
    name: str


@router.get("/")
def get_work_dirs(include_archived: bool = False):
    """列出所有工作目录。"""
    items = list_work_dirs(include_archived=include_archived, limit=500)
    return {"work_dirs": items, "total": len(items)}


@router.get("/latest")
def get_latest():
    """获取最近更新的工作目录（新会话默认值）。"""
    return {"work_dir": get_latest_work_dir()}


@router.post("/")
def create_work_dir(payload: WorkDirUpsert):
    """新增/更新一条工作目录记录。"""
    upsert_work_dir(payload.work_dir, name=payload.name)
    return {"success": True, "work_dir": payload.work_dir}


@router.delete("/")
def remove_work_dir(work_dir: str):
    """删除一条工作目录记录（不影响 sessions 表中的数据）。"""
    delete_work_dir(work_dir)
    return {"success": True, "work_dir": work_dir}


@router.put("/archive")
def set_archived(payload: WorkDirArchive):
    """归档/取消归档一条工作目录。"""
    archive_work_dir(payload.work_dir, archived=payload.archived)
    return {"success": True, "work_dir": payload.work_dir, "archived": payload.archived}


@router.put("/rename")
def set_name(payload: WorkDirRename):
    """重命名工作目录的显示名称。"""
    rename_work_dir(payload.work_dir, payload.name)
    return {"success": True, "work_dir": payload.work_dir, "name": payload.name}
