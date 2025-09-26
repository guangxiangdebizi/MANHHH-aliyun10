import json
from typing import List, Dict
from fastapi import WebSocket


class ConnectionManager:
    """WebSocket连接管理器（从 main.py 抽离）"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_sessions: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_sessions[websocket] = session_id
        return session_id

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.connection_sessions:
            self.connection_sessions.pop(websocket, None)

    def get_session_id(self, websocket: WebSocket) -> str:
        return self.connection_sessions.get(websocket, "default")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_text(json.dumps(message, ensure_ascii=False))
        except Exception as _:
            pass


