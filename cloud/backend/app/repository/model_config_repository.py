import asyncio
import json
from pathlib import Path

from app.model.model_config import ModelConfig


class ModelConfigRepository:
    """模型配置文件读写层

    配置路径：~/.Aries/{user_email}/config/model.json
    """

    @staticmethod
    def _get_config_path(user_email: str) -> Path:
        return Path.home() / ".Aries" / user_email / "config" / "model.json"

    @staticmethod
    async def read(user_email: str) -> ModelConfig:
        """读取用户模型配置，文件不存在则返回空配置"""
        path = ModelConfigRepository._get_config_path(user_email)

        def _read() -> ModelConfig:
            if not path.exists():
                return ModelConfig(models=[])
            data = json.loads(path.read_text(encoding="utf-8"))
            return ModelConfig(**data)

        return await asyncio.to_thread(_read)

    @staticmethod
    async def write(user_email: str, config: ModelConfig) -> None:
        """写入用户模型配置，自动创建目录"""
        path = ModelConfigRepository._get_config_path(user_email)
        payload = json.dumps(config.model_dump(), ensure_ascii=False, indent=2)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")

        await asyncio.to_thread(_write)
