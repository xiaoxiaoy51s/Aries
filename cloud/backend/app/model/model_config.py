from typing import Optional

from pydantic import BaseModel


class ModelItem(BaseModel):
    """单个模型配置项"""
    id: str                              # 配置项唯一ID
    model: str                           # 模型ID（实际模型名称，如 gpt-4o）
    name: str                            # 模型名称（用户备注，如 我的GPT）
    apiKey: str                          # API Key
    baseUrl: str                         # Base URL
    max_tool_rounds: int = 100           # 工具调用轮次
    context_window: int = 200_000        # 最大上下文
    isActive: bool = False               # 是否为当前激活模型


class ModelConfig(BaseModel):
    """用户模型配置文件结构"""
    models: list[ModelItem] = []
