from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ....dependencies import nds

websocket_router = r = APIRouter(prefix="/ws")


@r.websocket("/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await nds.on_connect_client(client_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await nds.message_queue.put((client_id, data))
    except WebSocketDisconnect:
        await nds.on_disconnect_client(client_id)
