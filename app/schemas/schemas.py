from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from uuid import UUID

class UserCreate(BaseModel):
    username: str = Field(..., example="johndoe88")
    password: str = Field(..., example="securepassword123")

class UserResponse(BaseModel):
    user_id: UUID
    username: str
    message: str

class EventCreate(BaseModel):
    event_name: str = Field(..., example="Global AI Summit 2026")
    total_capacity: int = Field(..., gt=0, example=500)
    ticket_price: float = Field(..., ge=0, example=150.00)

class EventResponse(BaseModel):
    event_id: UUID
    event_name: str
    total_capacity: int
    available_seats: int
    ticket_price: float
    status: str

class BookingCreate(BaseModel):
    event_name: str = Field(..., example="Global AI Summit 2026")
    username: str = Field(..., example="johndoe88")
    password: str = Field(..., example="securepassword123")
    quantity: int = Field(..., gt=0, example=2)

class BookingResponse(BaseModel):
    booking_id: UUID
    event_name: str
    username: str
    quantity: int
    total_cost: float
    status: str
    expires_at: datetime

class PaymentWebhook(BaseModel):
    booking_id: UUID
    transaction_reference: str = Field(..., example="tx_chg_8891002a")
    amount_paid: float = Field(..., ge=0, example=300.00)
    status: str = Field(..., example="SUCCESS")

class PaymentResponse(BaseModel):
    booking_id: UUID
    status: str
    message: str
