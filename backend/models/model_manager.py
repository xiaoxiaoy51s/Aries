import json
import threading
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
    """模型配置管理器，带内存缓存。

    缓存策略：
    - 首次读取从磁盘加载，后续直接返回内存副本。
    - save_config 时更新内存缓存并写盘。
    - 通过 mtime 检测外部修改，若文件被外部更改则自动失效重载。
    """

    def __init__(self) -> None:
        self._cache: Optional[ModelConfig] = None
        self._cache_mtime: Optional[float] = None
        self._lock = threading.Lock()

    def _read_from_disk(self) -> Optional[ModelConfig]:
        """从磁盘读取配置（不加锁，调用方自行加锁）。"""
        config_path = _get_config_path()
        if not config_path.exists():
            return None
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
            return config
        except Exception:
            return None

    def get_config(self) -> ModelConfig:
        config_path = _get_config_path()
        with self._lock:
            # 检查文件 mtime 是否变化（外部修改检测）
            try:
                current_mtime = config_path.stat().st_mtime
            except OSError:
                current_mtime = None

            # 缓存有效且文件未被外部修改：直接返回副本
            if (
                self._cache is not None
                and self._cache_mtime is not None
                and current_mtime is not None
                and current_mtime == self._cache_mtime
            ):
                return _dict_to_config(_config_to_dict(self._cache))

            # 缓存失效或首次读取：从磁盘加载
            config = self._read_from_disk()
            if config is None:
                # 文件不存在：创建默认配置并写盘
                default = _make_default_config()
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(
                    json.dumps(_config_to_dict(default), ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                self._cache = default
                try:
                    self._cache_mtime = config_path.stat().st_mtime
                except OSError:
                    self._cache_mtime = None
                return default

            self._cache = config
            try:
                self._cache_mtime = config_path.stat().st_mtime
            except OSError:
                self._cache_mtime = None
            return _dict_to_config(_config_to_dict(config))

    def save_config(self, config: ModelConfig) -> None:
        config_path = _get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(_config_to_dict(config), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        with self._lock:
            self._cache = _dict_to_config(_config_to_dict(config))
            try:
                self._cache_mtime = config_path.stat().st_mtime
            except OSError:
                self._cache_mtime = None

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
            context_window=data.context_window or 200_000,
            max_tool_rounds=data.max_tool_rounds or 100,
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
) -> dict:
    """解析最终使用的模型配置。

    优先级：传入参数 > 配置文件激活模型
    返回 dict: {baseUrl, apiKey, model, context_window, max_tool_rounds}
    """
    active = model_manager.get_active_model()
    if not active:
        return {
            "baseUrl": base_url,
            "apiKey": api_key,
            "model": model,
            "context_window": 200_000,
            "max_tool_rounds": 100,
        }
    return {
        "baseUrl": base_url or active.baseUrl or "",
        "apiKey": api_key or active.apiKey or "",
        "model": model or active.model or "",
        "context_window": active.context_window or 200_000,
        "max_tool_rounds": active.max_tool_rounds or 100,
    }
