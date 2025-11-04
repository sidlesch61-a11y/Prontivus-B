"""
Socket.io manager for real-time patient calling notifications
"""
from typing import Dict, Set
import asyncio
from datetime import datetime, timedelta

# In-memory store for active calls (in production, use Redis)
active_calls: Dict[int, Dict] = {}
connected_clients: Set[str] = set()


class SocketManager:
    """Manages Socket.io connections and broadcasting"""
    
    def __init__(self):
        self.sio = None
        self.cleanup_task = None
    
    def initialize(self, sio):
        """Initialize with Socket.io instance"""
        self.sio = sio
        self._setup_handlers()
        # Start cleanup task for expired calls
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_calls())
    
    def _setup_handlers(self):
        """Setup Socket.io event handlers"""
        
        @self.sio.on('connect')
        async def on_connect(sid, environ):
            connected_clients.add(sid)
            print(f"Client connected: {sid}")
            # Send current active calls to new client
            if active_calls:
                await self.sio.emit('active_calls', list(active_calls.values()), room=sid)
        
        @self.sio.on('disconnect')
        async def on_disconnect(sid):
            connected_clients.discard(sid)
            print(f"Client disconnected: {sid}")
        
        @self.sio.on('join_clinic')
        async def on_join_clinic(sid, data):
            clinic_id = data.get('clinic_id')
            if clinic_id:
                await self.sio.enter_room(sid, f"clinic_{clinic_id}")
                print(f"Client {sid} joined clinic {clinic_id}")
        
        @self.sio.on('leave_clinic')
        async def on_leave_clinic(sid, data):
            clinic_id = data.get('clinic_id')
            if clinic_id:
                await self.sio.leave_room(sid, f"clinic_{clinic_id}")
                print(f"Client {sid} left clinic {clinic_id}")
    
    async def broadcast_call(self, clinic_id: int, call_data: Dict):
        """Broadcast patient call to all clinic clients"""
        if self.sio:
            call_data['timestamp'] = datetime.now().isoformat()
            active_calls[call_data['appointment_id']] = call_data
            await self.sio.emit('patient_called', call_data, room=f"clinic_{clinic_id}")
            print(f"Broadcasted call for appointment {call_data['appointment_id']} to clinic {clinic_id}")
    
    async def update_call_status(self, clinic_id: int, appointment_id: int, status: str):
        """Update call status and broadcast"""
        if appointment_id in active_calls:
            active_calls[appointment_id]['status'] = status
            if self.sio:
                await self.sio.emit('call_status_updated', {
                    'appointment_id': appointment_id,
                    'status': status,
                    'timestamp': datetime.now().isoformat()
                }, room=f"clinic_{clinic_id}")
    
    async def remove_call(self, clinic_id: int, appointment_id: int):
        """Remove call from active list and notify clients"""
        if appointment_id in active_calls:
            del active_calls[appointment_id]
            if self.sio:
                await self.sio.emit('call_removed', {
                    'appointment_id': appointment_id,
                    'timestamp': datetime.now().isoformat()
                }, room=f"clinic_{clinic_id}")
    
    async def _cleanup_expired_calls(self):
        """Remove calls older than 5 minutes"""
        while True:
            try:
                now = datetime.now()
                expired = []
                for appt_id, call_data in active_calls.items():
                    called_at_str = call_data.get('called_at')
                    if called_at_str:
                        if isinstance(called_at_str, str):
                            called_at = datetime.fromisoformat(called_at_str.replace('Z', '+00:00'))
                        else:
                            called_at = called_at_str
                        if now - called_at > timedelta(minutes=5):
                            expired.append(appt_id)
                
                for appt_id in expired:
                    if appt_id in active_calls:
                        clinic_id = active_calls[appt_id].get('clinic_id')
                        if clinic_id:
                            await self.remove_call(clinic_id, appt_id)
                
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                print(f"Error in cleanup task: {e}")
                await asyncio.sleep(60)


# Global instance
socket_manager = SocketManager()

