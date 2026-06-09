from pydantic import BaseModel
from typing import Optional, List


class ModelItem(BaseModel):
    id: str
    apiKey: str
    baseUrl: str
    model: str
    isActive: bool = True


class ModelConfig(BaseModel):
    model_config = {"extra": "allow"}

    # 多模型列表
    models: List[ModelItem] = []
    # 向后兼容：保留 vision 字段
    vision: Optional[ModelItem] = None


class ModelCreate(BaseModel):
    id: Optional[str] = None
    apiKey: str
    baseUrl: str
    model: str
    isActive: bool = True


class ModelUpdate(BaseModel):
    apiKey: Optional[str] = None
    baseUrl: Optional[str] = None
    model: Optional[str] = None
    isActive: Optional[bool] = None
