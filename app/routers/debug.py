from fastapi import APIRouter
from app.core.database import db
from app.core.logger import logger

router = APIRouter()

@router.get("/data")
async def get_all_data():
    logger.info("Debug data requested", extra={"action": "export_all_db_json"})
    async with db.lock:
        return {
            "users": db.users,
            "events": db.events,
            "bookings": db.bookings
        }
