"""
WEBSOCKET STATUS ROUTER — Crime AI Live Timeline Streaming
===========================================================
WS /ws/agent-status/{session_id} — pushes live progress events while queries run.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from core.session_store import ACTIVE_CONNECTIONS

router = APIRouter(tags=["WebSocket"])

@router.websocket("/ws/agent-status/{session_id}")
async def websocket_status_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    if session_id not in ACTIVE_CONNECTIONS:
        ACTIVE_CONNECTIONS[session_id] = []
    ACTIVE_CONNECTIONS[session_id].append(websocket)
    
    try:
        # Send initial greeting/status connection event
        await websocket.send_json({"event": "connected", "session_id": session_id, "status": "listening"})
        while True:
            # Keep alive and listen for client pings or control messages
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"event": "pong"})
    except WebSocketDisconnect:
        if session_id in ACTIVE_CONNECTIONS and websocket in ACTIVE_CONNECTIONS[session_id]:
            ACTIVE_CONNECTIONS[session_id].remove(websocket)
    except Exception:
        if session_id in ACTIVE_CONNECTIONS and websocket in ACTIVE_CONNECTIONS[session_id]:
            ACTIVE_CONNECTIONS[session_id].remove(websocket)
