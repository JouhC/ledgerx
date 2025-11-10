import logging
from time import time
from datetime import datetime
from fastapi import FastAPI, Request
from core.dependencies import get_task_manager
from routers import health, bills

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("request_logger")

app = FastAPI(
    title="Bills API",
    description="API for bills",
    version="1.0.0")

# Include routers
app.include_router(health.router)
app.include_router(bills.router)
