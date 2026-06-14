import logging
import asyncio
import httpx
from contextvars import ContextVar
from pythonjsonlogger import jsonlogger
from datetime import datetime, timezone
from app.core.config import settings
from typing import List, Dict, Any

# Context variable to hold the correlation ID for the current request
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        if not log_record.get('timestamp'):
            now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            log_record['timestamp'] = now
        if log_record.get('level'):
            log_record['level'] = log_record['level'].upper()
        else:
            log_record['level'] = record.levelname
            
        log_record['logger_name'] = record.name
        log_record['filename'] = record.filename
        
        # Inject context variables
        log_record['correlation_id'] = correlation_id.get()
        log_record['app_name'] = settings.APP_NAME

class SplunkHECHandler(logging.Handler):
    def __init__(self, uri: str, token: str, batch_size: int = 1, batch_interval: float = 1.0):
        super().__init__()
        self.uri = uri
        self.token = token
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        self.queue: asyncio.Queue = asyncio.Queue()
        # We disable SSL verification (verify=False) as Splunk often uses self-signed certs for HEC
        self.client = httpx.AsyncClient(timeout=5.0, verify=False)
        
        # We will start the worker task from the main FastAPI app event loop
        self.worker_task = None

    def start_worker(self):
        if self.worker_task is None:
            self.worker_task = asyncio.create_task(self._flush_queue())

    async def stop_worker(self):
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        await self.client.aclose()

    def emit(self, record):
        try:
            msg = self.format(record)
            # Use background task to put in queue to not block synchronous logger calls
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.queue.put(msg))
            except RuntimeError:
                # Event loop not running (e.g., during tests or shutdown)
                pass
        except Exception:
            self.handleError(record)

    async def _flush_queue(self):
        batch: List[str] = []
        while True:
            try:
                # Wait for messages with a timeout to allow for batching interval
                msg = await asyncio.wait_for(self.queue.get(), timeout=self.batch_interval)
                batch.append(msg)
                self.queue.task_done()
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break

            if len(batch) >= self.batch_size or (batch and self.queue.empty()):
                await self._send_to_splunk(batch)
                batch.clear()

    async def _send_to_splunk(self, batch: List[str]):
        headers = {"Authorization": f"Splunk {self.token}"}
        
        payload = ""
        for msg in batch:
            # Splunk HEC accepts multiple events by simply concatenating JSON objects
            payload += f'{{"event": {msg}}}\n'

        try:
            response = await self.client.post(self.uri, headers=headers, content=payload)
            response.raise_for_status()
        except Exception as e:
            # Fallback to standard stdout logging
            print(f"Failed to send logs to Splunk HEC: {e}")
            for msg in batch:
                print(msg)

def setup_logging():
    logger = logging.getLogger("ticketing_engine")
    logger.setLevel(logging.INFO)
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    # Console Handler for Fallback/Local Dev (Readable JSON)
    console_handler = logging.StreamHandler()
    console_formatter = CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s', json_indent=4)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File Handler for Editor Viewing (Readable JSON)
    file_handler = logging.FileHandler("server_logs.json", mode="a")
    file_handler.setFormatter(console_formatter)
    logger.addHandler(file_handler)

    # Splunk HEC Handler (Real-time by default, batching config available)
    # This maintains the strict JSON formatting for Splunk
    json_formatter = CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s')
    # batch_size=1 enforces real-time as requested
    splunk_handler = SplunkHECHandler(
        uri=settings.SPLUNK_HEC_URI,
        token=settings.SPLUNK_HEC_TOKEN,
        batch_size=1
    )
    splunk_handler.setFormatter(json_formatter)
    logger.addHandler(splunk_handler)
    
    return logger

logger = setup_logging()
