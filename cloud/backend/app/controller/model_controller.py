from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.interceptor.auth_interceptor import get_current_user
from app.model.model_config import ModelItem
from app.model.user import User
from app.service.model_config_service import ModelConfigService
from app.utils.security import is_masked_secret, mask_secret

router = APIRouter(prefix="/api/models", tags=["models"])


# ============ DTO ============

class ModelResponse(BaseModel):
    id: str
    model: str
    name: str
    apiKey: str
    baseUrl: str
    max_tool_rounds: int
    context_window: int
    isActive: bool

    class Config:
        from_attributes = True


class CreateModelRequest(BaseModel):
    model: str                          # 模型ID（实际模型名称，如 gpt-4o）
    name: str | None = None             # 模型名称（用户备注，默认同 model）
    apiKey: str
    baseUrl: str
    max_tool_rounds: int = 100
    context_window: int = 200_000
    isActive: bool = False


class UpdateModelRequest(BaseModel):
    model: str | None = None
    name: str | None = None
    apiKey: str | None = None
    baseUrl: str | None = None
    max_tool_rounds: int | None = None
    context_window: int | None = None
    isActive: bool | None = None


# ============ 接口 ============

def _to_response(model: ModelItem) -> ModelResponse:
    resp = ModelResponse.model_validate(model)
    resp.apiKey = mask_secret(model.apiKey)
    return resp


@router.get("", response_model=list[ModelResponse])
async def list_models(user: User = Depends(get_current_user)):
    models = await ModelConfigService.list_models(user.email)
    return [_to_response(m) for m in models]


@router.get("/active", response_model=ModelResponse | None)
async def get_active_model(user: User = Depends(get_current_user)):
    model = await ModelConfigService.get_active_model(user.email)
    return _to_response(model) if model else None


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(model_id: str, user: User = Depends(get_current_user)):
    model = await ModelConfigService.get_model(user.email, model_id)
    return _to_response(model)


@router.post("", response_model=ModelResponse)
async def create_model(req: CreateModelRequest, user: User = Depends(get_current_user)):
    model = await ModelConfigService.create_model(user.email, **req.model_dump())
    return _to_response(model)


@router.put("/{model_id}", response_model=ModelResponse)
async def update_model(
    model_id: str,
    req: UpdateModelRequest,
    user: User = Depends(get_current_user),
):
    update_data = req.model_dump(exclude_unset=True)
    if "apiKey" in update_data and is_masked_secret(update_data["apiKey"]):
        del update_data["apiKey"]
    model = await ModelConfigService.update_model(user.email, model_id, update_data)
    return _to_response(model)


@router.delete("/{model_id}")
async def delete_model(model_id: str, user: User = Depends(get_current_user)):
    await ModelConfigService.delete_model(user.email, model_id)
    return {"message": "删除成功"}
