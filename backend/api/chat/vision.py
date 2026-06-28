"""多模态处理模块"""
from .models import VisionRequest, ChatRequest
from .utils import load_file_as_base64_url
from .chat import chat_completions


async def chat_vision(request: VisionRequest):
    """处理多模态请求（图片+文本）"""
    content = []

    for image in request.images:
        if image.startswith("data:"):
            image_url = image
        elif image.startswith("http"):
            image_url = image
        else:
            image_url = load_file_as_base64_url(image)

        content.append({
            "type": "image_url",
            "image_url": {"url": image_url}
        })

    content.append({
        "type": "text",
        "text": request.text
    })

    messages = [{"role": "user", "content": content}]

    chat_req = ChatRequest(
        baseUrl=request.baseUrl,
        apiKey=request.apiKey,
        model=request.model,
        messages=messages,
        session_id=request.session_id,
        work_dir=request.work_dir,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        stream=request.stream,
    )

    return await chat_completions(chat_req)