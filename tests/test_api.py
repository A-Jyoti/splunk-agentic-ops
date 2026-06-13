import os
os.environ["TICKETING_DB_PREFIX"] = "test_db_"

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import db

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_db():
    # Reset DB state before each test
    db.users.clear()
    db.events.clear()
    db.bookings.clear()
    db.payments.clear()
    db.username_to_id.clear()
    db.event_name_to_id.clear()

def test_create_event():
    response = client.post("/api/v1/events", json={
        "event_name": "Test Event",
        "total_capacity": 100,
        "ticket_price": 50.0
    })
    assert response.status_code == 201
    data = response.json()
    assert data["event_name"] == "Test Event"
    assert data["available_seats"] == 100

def test_book_tickets():
    # Setup Event
    client.post("/api/v1/events", json={
        "event_name": "Book Event",
        "total_capacity": 10,
        "ticket_price": 50.0
    })

    # Register User
    client.post("/api/v1/users/register", json={
        "username": "testuser",
        "password": "password123"
    })
    
    # Book Ticket
    response = client.post("/api/v1/tickets/book", json={
        "event_name": "Book Event",
        "username": "testuser",
        "password": "password123",
        "quantity": 2
    })
    assert response.status_code == 201
    data = response.json()
    assert data["quantity"] == 2
    assert data["status"] == "PENDING_PAYMENT"
    
    # Verify seat decrement
    event_res = client.get("/api/v1/events/Book Event")
    assert event_res.json()["available_seats"] == 8

def test_payment_webhook():
    # Setup
    client.post("/api/v1/events", json={
        "event_name": "Pay Event",
        "total_capacity": 10,
        "ticket_price": 100.0
    })
    client.post("/api/v1/users/register", json={
        "username": "testuser",
        "password": "password123"
    })
    book_res = client.post("/api/v1/tickets/book", json={
        "event_name": "Pay Event",
        "username": "testuser",
        "password": "password123",
        "quantity": 1
    })
    booking_id = book_res.json()["booking_id"]
    
    # Process Payment
    response = client.post("/api/v1/tickets/payment", json={
        "booking_id": booking_id,
        "transaction_reference": "tx_123",
        "amount_paid": 100.0,
        "status": "SUCCESS"
    })
    assert response.status_code == 200
    assert response.json()["status"] == "CONFIRMED"
