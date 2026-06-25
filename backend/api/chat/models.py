"""聊天 API 的共享模型定义"""
from typing import Optional, Union, List
from pydantic import BaseModel


class ImageURL(BaseModel):
    url: str


class ImageContent(BaseModel):
    type: str = "image_url"
    image_url: ImageURL


class TextContent(BaseModel):
    type: str = "text"
    text: str


ContentPart = Union[TextContent, ImageContent]


class Message(BaseModel):
    role: str
    content: Optional[Union[str, List[ContentPart]]] = None
    name: Optional[str] = None
    tool_calls: Optional[list] = None
    tool_call_id: Optional[str] = None


class ToolFunction(BaseModel):
    name: str
    description: Optional[str] = ""
    parameters: Optional[dict] = None


class Tool(BaseModel):
    type: str = "function"
    function: ToolFunction


class ChatRequest(BaseModel):
    baseUrl: str = ""
    apiKey: str = ""
    model: str = ""
    messages: list[Message]
    session_id: Optional[str] = None
    work_dir: Optional[str] = None
    tools: Optional[list[Tool]] = None
    tool_choice: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = True
    public_url: Optional[str] = None


class VisionRequest(BaseModel):
    baseUrl: str = ""
    apiKey: str = ""
    model: str = ""
    text: str
    images: list[str]
    session_id: Optional[str] = None
    work_dir: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = True


class StopChatRequest(BaseModel):
    session_id: str


class ConfirmToolRequest(BaseModel):
    tool_call_id: str
    confirmed: bool = True


class ClearTodosRequest(BaseModel):
    session_id: str


class TempChatRequest(BaseModel):
    messages: list[Message]  # 临时对话的全部消息（含本轮 user）
    session_id: Optional[str] = None  # 用于加载上下文记忆
    work_dir: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None