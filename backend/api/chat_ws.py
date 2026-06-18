"""Chat WebSocket 端点 - 推送平台消息通知到前端。"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.chat_ws import get_chat_ws_manager

router = APIRouter(tags=["chat_ws"])


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket, session_id: str = "") -> None:
    """前端连接此端点，接收指定 session 的新消息通知。

    查询参数:
        session_id: 要监听的会话 ID
    """
    if not session_id:
        await websocket.close(code=1008, reason="缺少 session_id 参数")
        return

    manager = get_chat_ws_manager()
    await manager.connect(websocket, session_id)

    try:
        # 前端不需要发送消息，只需保持连接接收通知
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket, session_id)
