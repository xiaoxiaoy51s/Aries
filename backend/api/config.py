from fastapi import APIRouter, HTTPException
from typing import List

from models import model_manager, ModelItem, ModelCreate, ModelUpdate

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/")
async def get_config():
    return model_manager.get_config()


@router.get("/models", response_model=List[ModelItem])
async def list_models():
    """获取所有模型配置。"""
    return model_manager.list_models()


@router.get("/model")
async def get_model():
    """获取当前激活的模型配置。"""
    active = model_manager.get_active_model()
    if not active:
        return {"id": "", "apiKey": "", "baseUrl": "", "model": "", "isActive": False}
    return active


@router.post("/models", response_model=ModelItem)
async def create_model(data: ModelCreate):
    """新增一个模型配置。"""
    return model_manager.create_model(data)


@router.put("/models/{model_id}")
async def update_model(model_id: str, update_data: ModelUpdate):
    success = model_manager.update_model(model_id, update_data)
    if not success:
        raise HTTPException(status_code=404, detail="模型不存在")
    return {"success": True, "message": "模型已更新"}


@router.delete("/models/{model_id}")
async def delete_model(model_id: str):
    success = model_manager.delete_model(model_id)
    if not success:
        raise HTTPException(status_code=404, detail="模型不存在")
    return {"success": True, "message": "模型已删除"}


@router.post("/models/{model_id}/activate")
async def activate_model(model_id: str):
    """激活指定模型。"""
    success = model_manager.update_model(model_id, ModelUpdate(isActive=True))
    if not success:
        raise HTTPException(status_code=404, detail="模型不存在")
    return {"success": True, "message": "已切换到该模型"}


# 兼容旧接口
@router.put("/")
async def update_legacy(update_data: ModelUpdate):
    """兼容旧版：更新激活模型。"""
    active = model_manager.get_active_model()
    if not active:
        raise HTTPException(status_code=400, detail="没有可更新的激活模型")
    success = model_manager.update_model(active.id, update_data)
    if not success:
        raise HTTPException(status_code=400, detail="模型更新失败")
    return {"success": True, "message": "模型配置已更新"}
