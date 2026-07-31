import uuid

from app.exception.model_exception import DuplicateModelNameError, ModelNotFoundError
from app.model.model_config import ModelConfig, ModelItem
from app.repository.model_config_repository import ModelConfigRepository


class ModelConfigService:
    """模型配置业务逻辑层"""

    @staticmethod
    def _resolve_name(name: str | None, model: str) -> str:
        resolved = (name or "").strip()
        return resolved or model

    @staticmethod
    def _ensure_unique_name(
        models: list[ModelItem],
        name: str,
        exclude_id: str | None = None,
    ) -> None:
        for m in models:
            if exclude_id and m.id == exclude_id:
                continue
            if m.name == name:
                raise DuplicateModelNameError()

    @staticmethod
    async def list_models(user_email: str) -> list[ModelItem]:
        config = await ModelConfigRepository.read(user_email)
        return config.models

    @staticmethod
    async def get_model(user_email: str, model_id: str) -> ModelItem:
        config = await ModelConfigRepository.read(user_email)
        for m in config.models:
            if m.id == model_id:
                return m
        raise ModelNotFoundError()

    @staticmethod
    async def get_active_model(user_email: str) -> ModelItem | None:
        """获取激活模型，无激活则取第一个，都没有返回 None"""
        config = await ModelConfigRepository.read(user_email)
        for m in config.models:
            if m.isActive:
                return m
        return config.models[0] if config.models else None

    @staticmethod
    async def create_model(user_email: str, **kwargs) -> ModelItem:
        config = await ModelConfigRepository.read(user_email)
        model_id = kwargs.pop("id", None) or f"model-{uuid.uuid4().hex[:8]}"
        kwargs["name"] = ModelConfigService._resolve_name(kwargs.get("name"), kwargs["model"])
        ModelConfigService._ensure_unique_name(config.models, kwargs["name"])

        # 如果新模型设为 active，取消其他模型的 active
        if kwargs.get("isActive"):
            for m in config.models:
                m.isActive = False

        new_model = ModelItem(id=model_id, **kwargs)
        config.models.append(new_model)
        await ModelConfigRepository.write(user_email, config)
        return new_model

    @staticmethod
    async def update_model(user_email: str, model_id: str, update_data: dict) -> ModelItem:
        config = await ModelConfigRepository.read(user_email)
        target = None
        for m in config.models:
            if m.id == model_id:
                target = m
                break
        if not target:
            raise ModelNotFoundError()

        # 如果设为 active，取消其他模型的 active
        if update_data.get("isActive") is True:
            for m in config.models:
                m.isActive = False

        if "name" in update_data or "model" in update_data:
            next_name = ModelConfigService._resolve_name(
                update_data.get("name", target.name),
                update_data.get("model", target.model),
            )
            ModelConfigService._ensure_unique_name(config.models, next_name, exclude_id=target.id)
            update_data["name"] = next_name

        for key, value in update_data.items():
            if hasattr(target, key) and value is not None:
                setattr(target, key, value)

        await ModelConfigRepository.write(user_email, config)
        return target

    @staticmethod
    async def delete_model(user_email: str, model_id: str) -> None:
        config = await ModelConfigRepository.read(user_email)
        before = len(config.models)
        config.models = [m for m in config.models if m.id != model_id]
        if len(config.models) == before:
            raise ModelNotFoundError()

        # 删除的是激活模型时，自动激活第一个
        if config.models and not any(m.isActive for m in config.models):
            config.models[0].isActive = True

        await ModelConfigRepository.write(user_email, config)
