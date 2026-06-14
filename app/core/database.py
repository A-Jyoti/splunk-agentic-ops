import asyncio
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime, timezone

DB_PREFIX = os.getenv("TICKETING_DB_PREFIX", "db_")

def get_db_path(name: str) -> str:
    filename = f"{DB_PREFIX}{name}.json"
    # Vercel Serverless Functions have read-only filesystems except for /tmp
    if os.environ.get("VERCEL"):
        return os.path.join("/tmp", filename)
    return filename

class InMemoryDB:
    def __init__(self):
        self.lock = asyncio.Lock()
        
        # Core dictionaries
        self.users: Dict[str, Dict[str, Any]] = {}
        self.events: Dict[str, Dict[str, Any]] = {}
        self.bookings: Dict[str, Dict[str, Any]] = {}
        
        # Reverse lookups
        self.username_to_id: Dict[str, str] = {}
        self.event_name_to_id: Dict[str, str] = {}

        self.load_from_disk()

    def _load_file(self, name: str, default: Dict) -> Dict:
        path = get_db_path(name)
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading {path}: {e}")
                return default
        return default

    def _save_file(self, name: str, data: Dict):
        path = get_db_path(name)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load_from_disk(self):
        # Users
        self.users = self._load_file("users", {})
        self.username_to_id = self._load_file("username_to_id", {})
        
        # Events
        self.events = self._load_file("events", {})
        self.event_name_to_id = self._load_file("event_name_to_id", {})
        
        # Bookings
        self.bookings = self._load_file("bookings", {})
        
        # Force initial save to create files if they don't exist
        self.save_to_disk_sync()

    def save_to_disk_sync(self):
        self._save_file("users", self.users)
        self._save_file("username_to_id", self.username_to_id)
        self._save_file("events", self.events)
        self._save_file("event_name_to_id", self.event_name_to_id)
        self._save_file("bookings", self.bookings)

    async def save_to_disk(self):
        # Offload file I/O to a thread to avoid blocking the event loop
        await asyncio.to_thread(self.save_to_disk_sync)

    async def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        async with self.lock:
            return self.events.get(event_id)

    async def get_booking(self, booking_id: str) -> Optional[Dict[str, Any]]:
        async with self.lock:
            booking = self.bookings.get(booking_id)
            if not booking:
                return None
            
            # Passive expiration check
            if booking["status"] == "PENDING_PAYMENT":
                expires_at = datetime.fromisoformat(booking["expires_at"].replace('Z', '+00:00'))
                if datetime.now(timezone.utc) > expires_at:
                    booking["status"] = "EXPIRED"
                    
                    # Release seats back to event
                    event_id = booking["event_id"]
                    if event_id in self.events:
                        self.events[event_id]["available_seats"] += booking["quantity"]
                    
                    await self.save_to_disk()
            return booking

db = InMemoryDB()
