"""
WebSocket endpoint for real-time patient calling
Using FastAPI native WebSocket support
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import List, Dict
import json
from datetime import datetime, timedelta

from app.services.socket_manager import socket_manager

router = APIRouter(prefix="/ws", tags=["WebSocket"])


class ConnectionManager:
    """Manages WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}  # clinic_id -> connections
    
    async def connect(self, websocket: WebSocket, clinic_id: int):
        await websocket.accept()
        if clinic_id not in self.active_connections:
            self.active_connections[clinic_id] = []
        self.active_connections[clinic_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, clinic_id: int):
        if clinic_id in self.active_connections:
            self.active_connections[clinic_id] = [
                conn for conn in self.active_connections[clinic_id] if conn != websocket
            ]
    
    async def broadcast_to_clinic(self, clinic_id: int, message: dict):
        if clinic_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[clinic_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    print(f"Error sending to connection: {e}")
                    disconnected.append(connection)
            
            # Remove disconnected connections
            for conn in disconnected:
                self.disconnect(conn, clinic_id)


manager = ConnectionManager()


@router.websocket("/patient-calling/{clinic_id}")
async def websocket_endpoint(websocket: WebSocket, clinic_id: int):
    """WebSocket endpoint for patient calling notifications"""
    await manager.connect(websocket, clinic_id)
    try:
        # Send current active calls
        from app.services.socket_manager import active_calls
        current_calls = [
            call for call in active_calls.values()
            if call.get('clinic_id') == clinic_id
        ]
        await websocket.send_json({
            "type": "active_calls",
            "data": current_calls
        })
        
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages if needed
            message = json.loads(data)
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, clinic_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket, clinic_id)


# Update socket_manager to use ConnectionManager
async def broadcast_call_to_clinic(clinic_id: int, call_data: dict):
    """Broadcast call using WebSocket manager"""
    await manager.broadcast_to_clinic(clinic_id, {
        "type": "patient_called",
        "data": call_data
    })


async def broadcast_status_update(clinic_id: int, appointment_id: int, status: str):
    """Broadcast status update"""
    await manager.broadcast_to_clinic(clinic_id, {
        "type": "call_status_updated",
        "data": {
            "appointment_id": appointment_id,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
    })


async def broadcast_call_removed(clinic_id: int, appointment_id: int):
    """Broadcast call removal"""
    await manager.broadcast_to_clinic(clinic_id, {
        "type": "call_removed",
        "data": {
            "appointment_id": appointment_id,
            "timestamp": datetime.now().isoformat()
        }
    })

