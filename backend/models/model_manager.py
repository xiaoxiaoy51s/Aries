import json
import uuid
from pathlib import Path
from typing import Optional, List

from .model_config import ModelConfig, ModelItem, ModelCreate, ModelUpdate


def _get_config_path() -> Path:
    return Path.home() / ".Aries" / "config.json"


def _sanitize(value: str) -> str:
    return value.strip() if isinstance(value, str) else value


def _make_default_config() -> ModelConfig:
    return ModelConfig(models=[])


def _config_to_dict(config: ModelConfig) -> dict:
    return json.loads(config.model_dump_json())


def _dict_to_config(data: dict) -> ModelConfig:
    return ModelConfig(**data)


class ModelManager:
    def get_config(self) -> ModelConfig:
        config_path = _get_config_path()
        if not config_path.exists():
            default = _make_default_config()
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                json.dumps(_config_to_dict(default), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            return default
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            # 兼容旧版只有 vision 字段的配置
            if "vision" in data and "models" not in data:
                vision = data.pop("vision")
                data["models"] = [vision]
            elif "models" not in data:
                data["models"] = []
            config = _dict_to_config(data)
            # 清理数据
            for m in config.models:
                m.apiKey = _sanitize(m.apiKey)
                m.baseUrl = _sanitize(m.baseUrl)
            self.save_config(config)
            return config
        except Exception:
            return _make_default_config()

    def save_config(self, config: ModelConfig) -> None:
        config_path = _get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(_config_to_dict(config), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def list_models(self) -> List[ModelItem]:
        return self.get_config().models

    def get_active_model(self) -> Optional[ModelItem]:
        """获取 isActive=True 的模型，没有则取第一个，都没有则返回 None。"""
        config = self.get_config()
        for m in config.models:
            if m.isActive:
                return m
        if config.models:
            return config.models[0]
        return None

    def get_model_by_id(self, model_id: str) -> Optional[ModelItem]:
        for m in self.list_models():
            if m.id == model_id:
                return m
        return None

    def create_model(self, data: ModelCreate) -> ModelItem:
        config = self.get_config()
        model_id = data.id or f"model-{uuid.uuid4().hex[:8]}"
        # 如果新模型设为 active，取消其他模型的 active
        if data.isActive:
            for m in config.models:
                m.isActive = False
        new_model = ModelItem(
            id=model_id,
            apiKey=_sanitize(data.apiKey),
            baseUrl=_sanitize(data.baseUrl),
            model=data.model,
            isActive=data.isActive,
        )
        config.models.append(new_model)
        self.save_config(config)
        return new_model

    def update_model(self, model_id: str, update_data: ModelUpdate) -> bool:
        config = self.get_config()
        target = None
        for m in config.models:
            if m.id == model_id:
                target = m
                break
        if not target:
            return False
        update_dict = update_data.model_dump(exclude_unset=True)
        # 如果设为 active，取消其他模型的 active
        if update_dict.get("isActive") is True:
            for m in config.models:
                m.isActive = False
        for key, value in update_dict.items():
            if key in ("apiKey", "baseUrl") and isinstance(value, str):
                value = _sanitize(value)
            setattr(target, key, value)
        self.save_config(config)
        return True

    def delete_model(self, model_id: str) -> bool:
        config = self.get_config()
        before = len(config.models)
        config.models = [m for m in config.models if m.id != model_id]
        if len(config.models) == before:
            return False
        # 如果删除的是激活模型，且还有其他模型，则把第一个设为激活
        if config.models and not any(m.isActive for m in config.models):
            config.models[0].isActive = True
        self.save_config(config)
        return True


model_manager = ModelManager()


def resolve_active_model_config(
    base_url: str = "",
    api_key: str = "",
    model: str = "",
) -> tuple[str, str, str]:
    """解析最终使用的模型配置。

    优先级：传入参数 > 配置文件激活模型
    """
    active = model_manager.get_active_model()
    if not active:
        return base_url, api_key, model
    final_base_url = base_url or active.baseUrl or ""
    final_api_key = api_key or active.apiKey or ""
    final_model = model or active.model or ""
    return final_base_url, final_api_key, final_model
