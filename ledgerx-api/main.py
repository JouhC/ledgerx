import logging
from time import time
from datetime import datetime
from fastapi import FastAPI, Request
from app.core.lifespan import lifespan
from app.api.routers import health, players, giftcodes, redemptions, tasks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("request_logger")

app = FastAPI(
    title="Gift Code Redemption API",
    description="API for managing players, fetching gift codes, and redeeming them.",
    version="2.2.0",
    lifespan=lifespan
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time()
    try:
        body = (await request.body())[:1024]
        logger.info(f"{request.client.host} {request.method} {request.url} body={body!r}")
    except Exception:
        logger.info(f"{request.client.host} {request.method} {request.url} body=<unavailable>")
    response = await call_next(request)
    logger.info(f"Status {response.status_code} in {time()-start:.2f}s @ {datetime.now():%m/%d/%Y %H:%M:%S}")
    return response

# Include routers
app.include_router(health.router)
app.include_router(players.router)
app.include_router(giftcodes.router)
app.include_router(redemptions.router)
app.include_router(tasks.router)
