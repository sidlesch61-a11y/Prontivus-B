import asyncio
import json
from typing import Dict, Set

from starlette.websockets import WebSocket


class AppointmentRealtimeManager:
    """In-memory WebSocket manager segregated by clinic (tenant)."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._clinic_id_to_clients: Dict[int, Set[WebSocket]] = {}

    async def connect(self, clinic_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clinic_id_to_clients.setdefault(clinic_id, set()).add(websocket)

    async def disconnect(self, clinic_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            clients = self._clinic_id_to_clients.get(clinic_id)
            if clients and websocket in clients:
                clients.remove(websocket)
            if clients is not None and len(clients) == 0:
                self._clinic_id_to_clients.pop(clinic_id, None)

    async def broadcast(self, clinic_id: int, payload: dict) -> None:
        message = json.dumps(payload, default=str)
        async with self._lock:
            clients = list(self._clinic_id_to_clients.get(clinic_id, set()))
        to_remove: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_text(message)
            except Exception:
                to_remove.append(ws)
        if to_remove:
            async with self._lock:
                for ws in to_remove:
                    try:
                        self._clinic_id_to_clients.get(clinic_id, set()).discard(ws)
                    except Exception:
                        pass


appointment_realtime_manager = AppointmentRealtimeManager()


