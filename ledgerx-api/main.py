from core.logging_config import setup_logging
import logging
from fastapi import FastAPI
from routers import health, bills
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Bills API",
    description="API for bills",
    version="1.0.0")


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(bills.router)
