from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import time
import uuid
import logging
from app.core.config import settings
from app.core.logger import logger, correlation_id, setup_logging
from app.routers import events, tickets, debug, users

# Initialize Splunk Logger and Handlers
setup_logging()

app = FastAPI(
    title=settings.APP_NAME,
    description="Asynchronous Real-Time Event Ticketing Engine",
    version="1.0.0"
)

# Start/Stop background worker for Splunk Logger
@app.on_event("startup")
async def startup_event():
    # Find SplunkHECHandler and start worker
    for handler in logger.handlers:
        if hasattr(handler, 'start_worker'):
            handler.start_worker()
            logger.info("Splunk HEC background worker started.")

@app.on_event("shutdown")
async def shutdown_event():
    for handler in logger.handlers:
        if hasattr(handler, 'stop_worker'):
            await handler.stop_worker()
            logger.info("Splunk HEC background worker stopped.")

@app.middleware("http")
async def telemetry_middleware(request: Request, call_next):
    # Instantiate a persistent unique correlation_id
    req_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    token = correlation_id.set(req_id)
    
    start_time = time.perf_counter()
    
    try:
        response = await call_next(request)
        process_time = (time.perf_counter() - start_time) * 1000  # ms
        
        logger.info(
            "HTTP Request Completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": round(process_time, 3)
            }
        )
        return response
    except Exception as e:
        process_time = (time.perf_counter() - start_time) * 1000
        logger.error(
            "HTTP Request Failed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "latency_ms": round(process_time, 3),
                "error": str(e)
            },
            exc_info=True
        )
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
    finally:
        correlation_id.reset(token)

app.include_router(events.router, prefix="/api/v1", tags=["Events"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(tickets.router, prefix="/api/v1/tickets", tags=["Tickets"])
app.include_router(debug.router, prefix="/api/v1/debug", tags=["Debug"])
