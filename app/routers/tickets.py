from fastapi import APIRouter, HTTPException, status
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from app.schemas.schemas import BookingCreate, BookingResponse, PaymentWebhook, PaymentResponse
from app.core.database import db
from app.core.logger import logger

router = APIRouter()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

@router.post("/book", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def book_tickets(booking_req: BookingCreate):
    logger.info("Received booking request", extra={"event_name": booking_req.event_name, "username": booking_req.username})
    
    async with db.lock:
        # User handling
        user_id = db.username_to_id.get(booking_req.username)
        pwd_hash = hash_password(booking_req.password)
        
        if not user_id:
            logger.warning("User does not exist", extra={"username": booking_req.username})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found. Please register first.")
            
        user = db.users[user_id]
        if user["password_hash"] != pwd_hash:
            logger.warning("Invalid password for existing user", extra={"username": booking_req.username})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password.")

        # Event handling
        event_id = db.event_name_to_id.get(booking_req.event_name)
        if not event_id:
            logger.error("Target event not found", extra={"event_name": booking_req.event_name})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target event not found or inactive.")
            
        event = db.events[event_id]
        if event["status"] != "ACTIVE":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target event not found or inactive.")

        if event["available_seats"] < booking_req.quantity:
            logger.warning("Requested quantity exceeds available seat capacity", extra={"available_seats": event["available_seats"], "requested": booking_req.quantity})
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requested quantity exceeds available seat capacity.")
            
        # Passive check trigger across all bookings could happen here, but we'll do it specifically on individual access
        # Decrement seats
        event["available_seats"] -= booking_req.quantity
        
        # Create booking
        booking_id = str(uuid.uuid4())
        total_cost = event["ticket_price"] * booking_req.quantity
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        
        new_booking = {
            "booking_id": booking_id,
            "event_id": event_id,
            "user_id": user_id,
            "quantity": booking_req.quantity,
            "total_cost": total_cost,
            "status": "PENDING_PAYMENT",
            "expires_at": expires_at.isoformat().replace('+00:00', 'Z')
        }
        db.bookings[booking_id] = new_booking
        
        await db.save_to_disk()
    
    logger.info("Tickets booked successfully", extra={"booking_id": booking_id, "status": "PENDING_PAYMENT"})
    
    return {
        "booking_id": booking_id,
        "event_name": booking_req.event_name,
        "username": booking_req.username,
        "quantity": booking_req.quantity,
        "total_cost": total_cost,
        "status": "PENDING_PAYMENT",
        "expires_at": new_booking["expires_at"]
    }

@router.post("/payment", response_model=PaymentResponse, status_code=status.HTTP_200_OK)
async def process_payment(payment_webhook: PaymentWebhook):
    logger.info("Received payment webhook", extra={"booking_id": str(payment_webhook.booking_id), "tx_ref": payment_webhook.transaction_reference})
    
    async with db.lock:
        booking_id_str = str(payment_webhook.booking_id)
        booking = db.bookings.get(booking_id_str)
        
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")

        # Expiration Check
        if booking["status"] == "PENDING_PAYMENT":
            expires_at = datetime.fromisoformat(booking["expires_at"].replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > expires_at:
                booking["status"] = "EXPIRED"
                event = db.events[booking["event_id"]]
                event["available_seats"] += booking["quantity"]
                await db.save_to_disk()

        if booking["status"] == "EXPIRED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking has expired.")
            
        if booking["status"] == "CANCELLED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking was cancelled.")

        # Deep strict validation mapping
        if booking["user_id"] not in db.users:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Corrupted mapping: Attached user no longer exists.")
        if booking["event_id"] not in db.events:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Corrupted mapping: Attached event no longer exists.")

        if booking["status"] == "CONFIRMED":
            # Idempotency check: if already confirmed, we might just return success
            if booking.get("payment_reference") == payment_webhook.transaction_reference:
                logger.info("Payment webhook idempotent hit", extra={"tx_ref": payment_webhook.transaction_reference})
                return {"booking_id": booking_id_str, "status": "CONFIRMED", "message": "Payment already processed."}

        # Verify amount
        if payment_webhook.amount_paid != booking["total_cost"]:
            logger.error("Payment amount mismatch", extra={"expected": booking["total_cost"], "received": payment_webhook.amount_paid})
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment amount does not match booking total cost.")
            
        if payment_webhook.status != "SUCCESS":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment status must be SUCCESS.")
        
        booking["status"] = "CONFIRMED"
        booking["payment_reference"] = payment_webhook.transaction_reference
        await db.save_to_disk()
        
    logger.info("Payment processed successfully", extra={"booking_id": booking_id_str})
    return {"booking_id": booking_id_str, "status": "CONFIRMED", "message": "Payment successful."}

@router.post("/cancel/{booking_id}", status_code=status.HTTP_200_OK)
async def cancel_booking(booking_id: str):
    logger.info("Received request to cancel booking", extra={"booking_id": booking_id})
    async with db.lock:
        booking = db.bookings.get(booking_id)
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
            
        if booking["status"] in ["CONFIRMED", "CANCELLED", "EXPIRED"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot cancel booking with status {booking['status']}.")
            
        booking["status"] = "CANCELLED"
        event = db.events[booking["event_id"]]
        event["available_seats"] += booking["quantity"]
        
        await db.save_to_disk()
        
    logger.info("Booking cancelled successfully", extra={"booking_id": booking_id})
    return {"message": "Booking cancelled successfully.", "booking_id": booking_id}
