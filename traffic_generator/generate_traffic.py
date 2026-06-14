import time
import random
import string
import uuid
import httpx
import logging
from typing import List, Dict

# Configure basic logging for the generator itself
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_URL = "http://127.0.0.1:8000/api/v1"

class TrafficGenerator:
    def __init__(self):
        self.client = httpx.Client(timeout=5.0)
        # Keep track of created entities to generate both successful and failing requests
        self.users: List[Dict[str, str]] = []
        self.events: List[Dict[str, str]] = []
        self.bookings: List[Dict[str, str]] = []

    def random_string(self, length=8):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

    def run_action_register_user(self):
        username = self.random_string()
        password = "Password123!"
        
        # 80% chance of successful registration, 20% chance of collision (failure)
        if self.users and random.random() < 0.2:
            username = random.choice(self.users)["username"]
            
        payload = {"username": username, "password": password}
        response = self.client.post(f"{BASE_URL}/users/register", json=payload)
        
        if response.status_code == 201:
            self.users.append({"username": username, "password": password, "user_id": response.json()["user_id"]})
            logging.info(f"[201] User registered: {username}")
        else:
            logging.warning(f"[{response.status_code}] Failed to register user {username}: {response.text}")

    def run_action_create_event(self):
        event_name = f"Event-{self.random_string(5)}"
        capacity = random.randint(5, 100)
        price = round(random.uniform(10.0, 500.0), 2)
        
        # 10% chance of generating a bad request (negative capacity)
        if random.random() < 0.1:
            capacity = -10
            
        payload = {"event_name": event_name, "total_capacity": capacity, "ticket_price": price}
        response = self.client.post(f"{BASE_URL}/events", json=payload)
        
        if response.status_code == 201:
            self.events.append({"event_name": event_name, "event_id": response.json()["event_id"], "price": price})
            logging.info(f"[201] Event created: {event_name}")
        else:
            logging.warning(f"[{response.status_code}] Failed to create event {event_name}: {response.text}")

    def run_action_get_event(self):
        if not self.events or random.random() < 0.2:
            # Try to fetch a non-existent event (404 expected)
            event_id = str(uuid.uuid4())
        else:
            # Fetch a valid event (200 expected)
            event_id = random.choice(self.events)["event_id"]
            
        response = self.client.get(f"{BASE_URL}/events/{event_id}")
        if response.status_code == 200:
            logging.info(f"[200] Fetched event: {event_id}")
        else:
            logging.warning(f"[{response.status_code}] Failed to fetch event {event_id}: {response.text}")

    def run_action_book_ticket(self):
        if not self.users or not self.events:
            return # Need entities to book

        user = random.choice(self.users)
        event = random.choice(self.events)
        
        payload = {
            "event_name": event["event_name"],
            "username": user["username"],
            "password": user["password"],
            "quantity": random.randint(1, 3)
        }
        
        # Introduce Chaos (Failures)
        chaos_roll = random.random()
        if chaos_roll < 0.1:
            payload["password"] = "WrongPassword!" # 401 Unauthorized
        elif chaos_roll < 0.2:
            payload["username"] = "nonexistent_user" # 404 Not Found
        elif chaos_roll < 0.3:
            payload["event_name"] = "Ghost Event" # 404 Event Not Found
            
        response = self.client.post(f"{BASE_URL}/tickets/book", json=payload)
        
        if response.status_code == 201:
            booking = response.json()
            self.bookings.append({
                "booking_id": booking["booking_id"],
                "total_cost": booking["total_cost"],
                "status": "PENDING_PAYMENT"
            })
            logging.info(f"[201] Ticket booked successfully: {booking['booking_id']}")
        else:
            logging.warning(f"[{response.status_code}] Failed to book ticket: {response.text}")

    def run_action_pay_ticket(self):
        if not self.bookings:
            return
            
        # Get a pending booking
        pending_bookings = [b for b in self.bookings if b["status"] == "PENDING_PAYMENT"]
        if not pending_bookings:
            return
            
        booking = random.choice(pending_bookings)
        amount = booking["total_cost"]
        status = "SUCCESS"
        tx_ref = f"TXN-{self.random_string(10)}"
        
        # Introduce Chaos
        chaos_roll = random.random()
        if chaos_roll < 0.1:
            amount -= 10.0 # 400 Bad Request (Wrong amount)
        elif chaos_roll < 0.2:
            status = "FAILED" # 400 Bad Request (Payment status failed)
        elif chaos_roll < 0.3:
            booking["booking_id"] = str(uuid.uuid4()) # 404 Not Found (Fake booking id)
            
        payload = {
            "transaction_reference": tx_ref,
            "amount_paid": amount,
            "status": status
        }
        
        response = self.client.post(f"{BASE_URL}/tickets/payment/{booking['booking_id']}", json=payload)
        
        if response.status_code == 200:
            booking["status"] = "CONFIRMED"
            logging.info(f"[200] Payment successful for booking: {booking['booking_id']}")
        else:
            logging.warning(f"[{response.status_code}] Payment failed for booking {booking['booking_id']}: {response.text}")

    def run_forever(self):
        logging.info("Starting AI Traffic Generator. Press CTRL+C to stop.")
        actions = [
            self.run_action_register_user,
            self.run_action_create_event,
            self.run_action_get_event,
            self.run_action_book_ticket,
            self.run_action_pay_ticket
        ]
        
        # Pre-seed the database so actions don't fail immediately
        for _ in range(3):
            self.run_action_register_user()
            self.run_action_create_event()
            
        while True:
            try:
                # Randomly pick an action
                action = random.choice(actions)
                action()
                
                # Sleep between 0.1 and 2 seconds
                time.sleep(random.uniform(0.1, 2.0))
            except httpx.RequestError as e:
                logging.error(f"Connection error (Is the server running?): {e}")
                time.sleep(5)
            except KeyboardInterrupt:
                logging.info("Traffic Generator stopped by user.")
                break
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                time.sleep(1)

if __name__ == "__main__":
    generator = TrafficGenerator()
    generator.run_forever()
