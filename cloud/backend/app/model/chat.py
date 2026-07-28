from typing import Optional, Union
from pydantic import BaseModel


class Message(BaseModel):
    role: str
    content: Optional[Union[str, list]] = None


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    stream: bool = True


class ChatResponse(BaseModel):
    reply: str
    session_id: str
