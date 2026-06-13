from fastapi import APIRouter, HTTPException, status
import uuid
from app.schemas.schemas import EventCreate, EventResponse
from app.core.database import db
from app.core.logger import logger

router = APIRouter()

@router.post("/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(event: EventCreate):
    logger.info("Received request to create event", extra={"event_name": event.event_name})
    async with db.lock:
        if event.event_name in db.event_name_to_id:
            logger.warning("Event already exists", extra={"event_name": event.event_name})
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Event name already exists.")
        
        event_id = str(uuid.uuid4())
        new_event = {
            "event_id": event_id,
            "event_name": event.event_name,
            "total_capacity": event.total_capacity,
            "available_seats": event.total_capacity,
            "ticket_price": event.ticket_price,
            "status": "ACTIVE"
        }
        db.events[event_id] = new_event
        db.event_name_to_id[event.event_name] = event_id
        await db.save_to_disk()
        
    logger.info("Event created successfully", extra={"event_id": event_id})
    return new_event

@router.get("/events/{event_name}", response_model=EventResponse)
async def get_event(event_name: str):
    logger.info("Received request to get event details", extra={"event_name": event_name})
    async with db.lock:
        event_id = db.event_name_to_id.get(event_name)
        if not event_id:
            logger.error("Event not found", extra={"event_name": event_name})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
        
        event = db.events.get(event_id)
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
            
    logger.info("Event details retrieved", extra={"event_id": event_id})
    return event
