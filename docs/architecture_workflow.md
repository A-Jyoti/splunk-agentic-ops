# Architecture Workflow

This document explains the end-to-end workflow of the Real-Time Event Ticketing Engine.

## 1. System Components
* **FastAPI Application:** Serves as the primary entrypoint for all HTTP requests, providing automatic Pydantic validation via strictly typed schemas.
* **InMemoryDB:** Acts as the central data store. Uses `asyncio.Lock()` to ensure that when a booking occurs, seat availability is decremented atomically, preventing race conditions (overbooking). It periodically flushes to distinct local JSON files (`db_users.json`, `db_events.json`, `db_bookings.json`) to persist data across local development restarts.
* **Splunk HEC Logger:** A custom asynchronous logging handler running in a background task. It accepts structured JSON logs generated via `python-json-logger` and streams them directly to Splunk without blocking the event loop.

## 2. Request Lifecycle (Example: Booking a Ticket)
1. **Middleware Intercept:** The request hits the `telemetry_middleware`. A unique `correlation_id` is assigned to track the transaction context natively.
2. **Endpoint Execution:** The `POST /api/v1/tickets/book` route is invoked.
3. **Database Lock Acquisition:** The router calls `async with db.lock:` guaranteeing exclusive access to the memory pool.
4. **Validation & State Change:** The user is explicitly verified to exist in the `users` database. Seat capacity is checked, and seats are decremented. A booking is generated with the status `PENDING_PAYMENT` and an `expires_at` timestamp.
5. **Database Release:** The lock is released, and the background task saves the updated state back to the dedicated JSON files on disk.
6. **Middleware Exit:** The `telemetry_middleware` logs the success, latency, and standard HTTP metrics (with `correlation_id` injected) directly to the custom logger.

## 3. Passive Expiration Mechanism
Instead of running a heavy `apscheduler` daemon to check for expired bookings constantly, the application implements a "passive check". When an entity (like a booking or payment) is requested (e.g., during the webhook payment resolution), the database intercepts the retrieval. If the booking is `PENDING_PAYMENT` and `datetime.now()` exceeds `expires_at`, it instantly updates the status to `EXPIRED` and adds the seats back to the event pool.

## 4. Telemetry Strategy
No sidecars or intermediate agents (like Filebeat) are required. The Python app natively queues log payloads into `asyncio.Queue`. A worker task asynchronously batches and ships them via `httpx.AsyncClient` to the configured `SPLUNK_HEC_URI`.

## 5. CI/CD DevOps Pipeline
The `.github/workflows/main.yml` manages continuous integration in three distinct sequential stages: **Lint**, **Test**, and **Deploy**. 
Every single stage automatically parses its own `stdout` and `stderr` logs, injecting them into a JSON payload, and `curl`s it directly to the Splunk HEC. If the Lint and Test stages pass on the `main` branch, the Deploy stage initiates. The pipeline utilizes the official `vercel` CLI to pull, build, and deploy the FastAPI application natively as a Vercel Serverless Function, pushing the final deployment logs straight to Splunk.

## 6. Visualizing Data & Logs in your Editor
* **Database JSON (`db_users.json`, etc):** The `InMemoryDB` is configured to physically dump its exact schema to dedicated files like `db_users.json`, `db_events.json`, and `db_bookings.json` right in the root of your project immediately upon server startup. You can open these files directly in your code editor to see data locally. 
* **Live JSON Logs (`server_logs.json`):** A custom Python `FileHandler` captures every single telemetry event and writes it to `server_logs.json` in your root directory. This provides an indented, highly readable JSON format of all logs, identical to what is being shipped to Splunk. Open this file in your editor to read logs comfortably.
* **Database API Visualization:** You can also dynamically fetch the combined database state by accessing the `GET /api/v1/debug/data` endpoint via Swagger (`http://127.0.0.1:8000/docs`).
